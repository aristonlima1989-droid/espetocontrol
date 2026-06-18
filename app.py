from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "troque_essa_chave_em_producao"
DB = "database.db"

def conectar():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        login TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        perfil TEXT NOT NULL,
        ativo INTEGER DEFAULT 1
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao TEXT NOT NULL,
        categoria TEXT NOT NULL,
        valor REAL NOT NULL,
        usa_ponto_carne INTEGER DEFAULT 0,
        setor_preparo TEXT DEFAULT 'COZINHA',
        tipo_produto TEXT DEFAULT 'SIMPLES',
        ativo INTEGER DEFAULT 1
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS comandas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT NOT NULL UNIQUE,
        mesa TEXT NOT NULL,
        cliente TEXT,
        qtd_pessoas INTEGER DEFAULT 1,
        garcom_id INTEGER,
        status TEXT DEFAULT 'ABERTA',
        data_abertura TEXT NOT NULL,
        data_fechamento TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comanda_id INTEGER NOT NULL,
        produto_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        valor_unitario REAL NOT NULL,
        ponto_carne TEXT,
        observacao TEXT,
        status TEXT DEFAULT 'PENDENTE',
        data_hora TEXT NOT NULL
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS combo_itens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        combo_id INTEGER NOT NULL,
        produto_id INTEGER NOT NULL,
        quantidade INTEGER DEFAULT 1,
        cobrar_item INTEGER DEFAULT 0
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comanda_id INTEGER NOT NULL,
        valor REAL NOT NULL,
        forma_pagamento TEXT NOT NULL,
        data_pagamento TEXT NOT NULL
    )""")

    colunas_produtos = [c[1] for c in cur.execute("PRAGMA table_info(produtos)").fetchall()]
    if "tipo_produto" not in colunas_produtos:
        cur.execute("ALTER TABLE produtos ADD COLUMN tipo_produto TEXT DEFAULT 'SIMPLES'")

    if not cur.execute("SELECT id FROM usuarios WHERE login='admin'").fetchone():
        cur.execute("INSERT INTO usuarios (nome,login,senha,perfil) VALUES (?,?,?,?)",
                    ("Administrador","admin",generate_password_hash("admin123"),"ADMIN"))

    if cur.execute("SELECT COUNT(*) total FROM produtos").fetchone()["total"] == 0:
        produtos = [
            ("Picanha","Espeto",18,1,"CHURRASQUEIRA"),("Alcatra","Espeto",14,1,"CHURRASQUEIRA"),
            ("Frango","Espeto",10,1,"CHURRASQUEIRA"),("Kafta","Espeto",12,1,"CHURRASQUEIRA"),
            ("Coração","Espeto",12,1,"CHURRASQUEIRA"),("Queijo Coalho","Espeto",10,0,"CHURRASQUEIRA"),
            ("Mandioca","Acompanhamento",8,0,"COZINHA"),("Batata Frita","Acompanhamento",18,0,"COZINHA"),
            ("Arroz","Acompanhamento",7,0,"COZINHA"),("Vinagrete","Acompanhamento",5,0,"COZINHA"),
            ("Coca-Cola Lata","Bebida",6,0,"BAR"),("Água","Bebida",4,0,"BAR")
        ]
        cur.executemany("""INSERT INTO produtos (descricao,categoria,valor,usa_ponto_carne,setor_preparo,tipo_produto)
                           VALUES (?,?,?,?,?,'SIMPLES')""", produtos)
        cur.execute("""INSERT INTO produtos (descricao,categoria,valor,usa_ponto_carne,setor_preparo,tipo_produto)
                       VALUES ('Farofa','Acompanhamento',0,0,'COZINHA','SIMPLES')""")
        combos = [
            ('Espeto Completo Picanha','Combo',25.00,1,'CHURRASQUEIRA','COMBO','Picanha'),
            ('Espeto Completo Alcatra','Combo',22.00,1,'CHURRASQUEIRA','COMBO','Alcatra'),
            ('Espeto Completo Frango','Combo',18.00,1,'CHURRASQUEIRA','COMBO','Frango')
        ]
        for desc, cat, val, usa, setor, tipo, carne in combos:
            cur.execute("""INSERT INTO produtos (descricao,categoria,valor,usa_ponto_carne,setor_preparo,tipo_produto)
                           VALUES (?,?,?,?,?,?)""", (desc, cat, val, usa, setor, tipo))
            combo_id = cur.lastrowid
            ids=[]
            for nome in [carne,'Arroz','Farofa','Vinagrete']:
                r=cur.execute("SELECT id FROM produtos WHERE descricao=?", (nome,)).fetchone()
                if r: ids.append(r[0])
            for item_id in ids:
                cur.execute("INSERT INTO combo_itens (combo_id, produto_id, quantidade, cobrar_item) VALUES (?,?,1,0)", (combo_id, item_id))

    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def perfil_required(*perfis):
    def decorator(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "perfil" not in session:
                return redirect(url_for("login"))
            if session["perfil"] not in perfis and session["perfil"] != "ADMIN":
                flash("Acesso não permitido.", "danger")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return wrapper
    return decorator

def lancar_item_pedido(conn, comanda_id, produto, quantidade, ponto_carne, observacao, valor_unitario=None):
    if not produto["usa_ponto_carne"]:
        ponto_carne = ""
    if valor_unitario is None:
        valor_unitario = produto["valor"]
    conn.execute("""
        INSERT INTO pedidos (comanda_id,produto_id,quantidade,valor_unitario,ponto_carne,observacao,data_hora)
        VALUES (?,?,?,?,?,?,?)
    """, (comanda_id, produto["id"], quantidade, valor_unitario, ponto_carne, observacao, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def lancar_produto_ou_combo(conn, comanda_id, produto_id, quantidade, ponto_carne, observacao):
    produto = conn.execute("SELECT * FROM produtos WHERE id=? AND ativo=1", (produto_id,)).fetchone()
    if not produto:
        raise ValueError("Produto não encontrado")
    if produto["tipo_produto"] == "COMBO":
        lancar_item_pedido(conn, comanda_id, produto, quantidade, ponto_carne, observacao, valor_unitario=produto["valor"])
        itens = conn.execute("""
            SELECT ci.quantidade AS qtd_combo, pr.*
            FROM combo_itens ci JOIN produtos pr ON pr.id = ci.produto_id
            WHERE ci.combo_id=? ORDER BY pr.setor_preparo, pr.descricao
        """, (produto_id,)).fetchall()
        for item in itens:
            obs = f"Item do combo: {produto['descricao']}"
            if observacao:
                obs += f" | Obs combo: {observacao}"
            lancar_item_pedido(conn, comanda_id, item, quantidade*int(item["qtd_combo"] or 1), ponto_carne if item["usa_ponto_carne"] else "", obs, valor_unitario=0)
    else:
        lancar_item_pedido(conn, comanda_id, produto, quantidade, ponto_carne, observacao)


@app.route("/")
def index():
    return redirect(url_for("dashboard") if "usuario_id" in session else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        conn = conectar()
        u = conn.execute("SELECT * FROM usuarios WHERE login=? AND ativo=1", (request.form["login"],)).fetchone()
        conn.close()
        if u and check_password_hash(u["senha"], request.form["senha"]):
            session["usuario_id"] = u["id"]
            session["nome"] = u["nome"]
            session["perfil"] = u["perfil"]
            return redirect(url_for("dashboard"))
        flash("Login ou senha inválidos.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = conectar()
    comandas_abertas = conn.execute("SELECT COUNT(*) total FROM comandas WHERE status='ABERTA'").fetchone()["total"]
    pedidos_pendentes = conn.execute("""
        SELECT COUNT(*) AS total
        FROM (
            SELECT DISTINCT p.comanda_id, pr.setor_preparo
            FROM pedidos p
            JOIN produtos pr ON pr.id = p.produto_id
            JOIN comandas c ON c.id = p.comanda_id
            WHERE p.status IN ('PENDENTE','EM PREPARO')
              AND c.status = 'ABERTA'
              AND COALESCE(pr.tipo_produto, 'SIMPLES') <> 'COMBO'
        ) x
    """).fetchone()["total"]
    vendas_dia = conn.execute("SELECT COALESCE(SUM(valor),0) total FROM pagamentos WHERE substr(data_pagamento,1,10)=?",
                              (datetime.now().strftime("%Y-%m-%d"),)).fetchone()["total"]
    conn.close()
    return render_template("dashboard.html", comandas_abertas=comandas_abertas, pedidos_pendentes=pedidos_pendentes, vendas_dia=vendas_dia)

@app.route("/usuarios", methods=["GET","POST"])
@login_required
@perfil_required("ADMIN")
def usuarios():
    conn = conectar()
    if request.method == "POST":
        try:
            conn.execute("INSERT INTO usuarios (nome,login,senha,perfil) VALUES (?,?,?,?)",
                         (request.form["nome"], request.form["login"], generate_password_hash(request.form["senha"]), request.form["perfil"]))
            conn.commit()
            flash("Usuário cadastrado.", "success")
        except sqlite3.IntegrityError:
            flash("Login já existe.", "danger")
    lista = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=lista)

@app.route("/produtos", methods=["GET","POST"])
@login_required
@perfil_required("ADMIN")
def produtos():
    conn = conectar()
    if request.method == "POST":
        valor = float(request.form.get("valor","0").replace(",","."))
        usa = 1 if request.form.get("usa_ponto_carne") == "on" else 0
        conn.execute("""INSERT INTO produtos (descricao,categoria,valor,usa_ponto_carne,setor_preparo,tipo_produto,ativo)
                        VALUES (?,?,?,?,?,?,1)""",
                     (request.form["descricao"], request.form["categoria"], valor, usa, request.form["setor_preparo"], request.form.get("tipo_produto","SIMPLES")))
        conn.commit()
        flash("Produto cadastrado.", "success")
    mostrar = request.args.get("inativos") == "1"
    if mostrar:
        lista = conn.execute("SELECT * FROM produtos ORDER BY ativo DESC,setor_preparo,categoria,descricao").fetchall()
    else:
        lista = conn.execute("SELECT * FROM produtos WHERE ativo=1 ORDER BY setor_preparo,categoria,descricao").fetchall()
    conn.close()
    return render_template("produtos.html", produtos=lista, mostrar_inativos=mostrar)

@app.route("/produto/editar/<int:produto_id>", methods=["GET","POST"])
@login_required
@perfil_required("ADMIN")
def editar_produto(produto_id):
    conn = conectar()
    produto = conn.execute("SELECT * FROM produtos WHERE id=?", (produto_id,)).fetchone()
    if not produto:
        conn.close(); flash("Produto não encontrado.", "danger"); return redirect(url_for("produtos"))
    if request.method == "POST":
        valor = float(request.form.get("valor","0").replace(",","."))
        usa = 1 if request.form.get("usa_ponto_carne") == "on" else 0
        ativo = 1 if request.form.get("ativo") == "on" else 0
        conn.execute("""UPDATE produtos SET descricao=?,categoria=?,valor=?,usa_ponto_carne=?,setor_preparo=?,tipo_produto=?,ativo=? WHERE id=?""",
                     (request.form["descricao"], request.form["categoria"], valor, usa, request.form["setor_preparo"], request.form.get("tipo_produto","SIMPLES"), ativo, produto_id))
        conn.commit(); conn.close(); flash("Produto atualizado.", "success"); return redirect(url_for("produtos", inativos=1))
    conn.close()
    return render_template("editar_produto.html", produto=produto)

@app.route("/produto/inativar/<int:produto_id>")
@login_required
@perfil_required("ADMIN")
def inativar_produto(produto_id):
    conn=conectar(); conn.execute("UPDATE produtos SET ativo=0 WHERE id=?", (produto_id,)); conn.commit(); conn.close()
    flash("Produto inativado.", "success"); return redirect(url_for("produtos"))

@app.route("/produto/reativar/<int:produto_id>")
@login_required
@perfil_required("ADMIN")
def reativar_produto(produto_id):
    conn=conectar(); conn.execute("UPDATE produtos SET ativo=1 WHERE id=?", (produto_id,)); conn.commit(); conn.close()
    flash("Produto reativado.", "success"); return redirect(url_for("produtos", inativos=1))

@app.route("/comandas")
@login_required
def comandas():
    conn = conectar()
    lista = conn.execute("""SELECT c.*, u.nome garcom FROM comandas c LEFT JOIN usuarios u ON u.id=c.garcom_id
                            WHERE c.status='ABERTA' ORDER BY c.data_abertura DESC""").fetchall()
    conn.close()
    return render_template("comandas.html", comandas=lista)

@app.route("/nova_comanda", methods=["GET","POST"])
@login_required
@perfil_required("GARCOM","ADMIN")
def nova_comanda():
    if request.method == "POST":
        conn = conectar()
        ultimo = conn.execute("SELECT MAX(id) id FROM comandas").fetchone()["id"] or 0
        numero = f"COM{ultimo+1:06d}"
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""INSERT INTO comandas (numero,mesa,cliente,qtd_pessoas,garcom_id,data_abertura)
                        VALUES (?,?,?,?,?,?)""",
                     (numero, request.form["mesa"], request.form.get("cliente") or "Cliente", int(request.form.get("qtd_pessoas") or 1), session["usuario_id"], agora))
        conn.commit()
        cid = conn.execute("SELECT id FROM comandas WHERE numero=?", (numero,)).fetchone()["id"]
        conn.close()
        return redirect(url_for("lancar_pedido", comanda_id=cid))
    return render_template("nova_comanda.html")

@app.route("/lancar_pedido/<int:comanda_id>", methods=["GET","POST"])
@login_required
@perfil_required("GARCOM","ADMIN")
def lancar_pedido(comanda_id):
    conn = conectar()
    comanda = conn.execute("SELECT * FROM comandas WHERE id=?", (comanda_id,)).fetchone()
    if not comanda or comanda["status"] != "ABERTA":
        conn.close(); flash("Comanda não encontrada ou fechada.", "danger"); return redirect(url_for("comandas"))
    if request.method == "POST":
        try:
            lancar_produto_ou_combo(conn, comanda_id, int(request.form["produto_id"]), int(request.form["quantidade"]), request.form.get("ponto_carne") or "", request.form.get("observacao") or "")
            conn.commit()
            flash("Pedido enviado para o setor de preparo.", "success")
        except ValueError as e:
            flash(str(e), "danger")
    produtos = conn.execute("SELECT * FROM produtos WHERE ativo=1 ORDER BY categoria,descricao").fetchall()
    pedidos = conn.execute("""SELECT p.*, pr.descricao, pr.categoria, pr.setor_preparo FROM pedidos p JOIN produtos pr ON pr.id=p.produto_id
                              WHERE p.comanda_id=? ORDER BY p.data_hora ASC,p.id ASC""", (comanda_id,)).fetchall()
    total = sum([p["quantidade"]*p["valor_unitario"] for p in pedidos])
    conn.close()
    return render_template("lancar_pedido.html", comanda=comanda, produtos=produtos, pedidos=pedidos, total=total)

@app.route("/comanda_historico/<int:comanda_id>")
@login_required
def comanda_historico(comanda_id):
    conn = conectar()
    comanda = conn.execute("""SELECT c.*, u.nome garcom FROM comandas c LEFT JOIN usuarios u ON u.id=c.garcom_id WHERE c.id=?""", (comanda_id,)).fetchone()
    if not comanda:
        conn.close(); flash("Comanda não encontrada.", "danger"); return redirect(url_for("comandas"))
    pedidos = conn.execute("""SELECT p.*, pr.descricao, pr.categoria, pr.setor_preparo FROM pedidos p JOIN produtos pr ON pr.id=p.produto_id
                              WHERE p.comanda_id=? ORDER BY p.data_hora ASC,p.id ASC""", (comanda_id,)).fetchall()
    total = sum([p["quantidade"]*p["valor_unitario"] for p in pedidos])
    conn.close()
    return render_template("comanda_historico.html", comanda=comanda, pedidos=pedidos, total=total)

@app.route("/pedido/editar/<int:pedido_id>", methods=["GET","POST"])
@login_required
@perfil_required("GARCOM","ADMIN")
def editar_pedido(pedido_id):
    conn = conectar()
    pedido = conn.execute("""SELECT p.*, pr.descricao, pr.usa_ponto_carne, pr.setor_preparo, c.numero, c.mesa, c.cliente
                             FROM pedidos p JOIN produtos pr ON pr.id=p.produto_id JOIN comandas c ON c.id=p.comanda_id WHERE p.id=?""", (pedido_id,)).fetchone()
    if not pedido:
        conn.close(); flash("Pedido não encontrado.", "danger"); return redirect(url_for("comandas"))
    if pedido["status"] not in ("PENDENTE","EM PREPARO"):
        conn.close(); flash("Pedido pronto/entregue não pode ser editado.", "danger"); return redirect(url_for("comanda_historico", comanda_id=pedido["comanda_id"]))
    if request.method == "POST":
        ponto = request.form.get("ponto_carne") if pedido["usa_ponto_carne"] else ""
        conn.execute("UPDATE pedidos SET quantidade=?, ponto_carne=?, observacao=? WHERE id=?",
                     (int(request.form["quantidade"]), ponto, request.form.get("observacao"), pedido_id))
        conn.commit(); conn.close(); flash("Pedido atualizado.", "success"); return redirect(url_for("comanda_historico", comanda_id=pedido["comanda_id"]))
    conn.close()
    return render_template("editar_pedido.html", pedido=pedido)

@app.route("/pedido/excluir/<int:pedido_id>")
@login_required
@perfil_required("GARCOM","ADMIN")
def excluir_pedido(pedido_id):
    conn = conectar()
    p = conn.execute("SELECT * FROM pedidos WHERE id=?", (pedido_id,)).fetchone()
    if not p:
        conn.close(); flash("Pedido não encontrado.", "danger"); return redirect(url_for("comandas"))
    if p["status"] not in ("PENDENTE","EM PREPARO"):
        conn.close(); flash("Pedido pronto/entregue não pode ser excluído.", "danger"); return redirect(url_for("comanda_historico", comanda_id=p["comanda_id"]))
    cid = p["comanda_id"]
    conn.execute("DELETE FROM pedidos WHERE id=?", (pedido_id,))
    conn.commit(); conn.close()
    flash("Pedido excluído.", "success")
    return redirect(url_for("comanda_historico", comanda_id=cid))

@app.route("/produto/combo/<int:combo_id>", methods=["GET","POST"])
@login_required
@perfil_required("ADMIN")
def combo_config(combo_id):
    conn = conectar()
    combo = conn.execute("SELECT * FROM produtos WHERE id=? AND tipo_produto='COMBO'", (combo_id,)).fetchone()
    if not combo:
        conn.close(); flash("Combo não encontrado.", "danger"); return redirect(url_for("produtos"))
    if request.method == "POST":
        conn.execute("INSERT INTO combo_itens (combo_id,produto_id,quantidade,cobrar_item) VALUES (?,?,?,0)", (combo_id, int(request.form["produto_id"]), int(request.form.get("quantidade") or 1)))
        conn.commit(); flash("Item adicionado ao combo.", "success")
    itens = conn.execute("""
        SELECT ci.id, ci.quantidade, pr.descricao, pr.setor_preparo, pr.usa_ponto_carne
        FROM combo_itens ci JOIN produtos pr ON pr.id=ci.produto_id
        WHERE ci.combo_id=? ORDER BY pr.setor_preparo, pr.descricao
    """, (combo_id,)).fetchall()
    produtos = conn.execute("SELECT * FROM produtos WHERE ativo=1 AND tipo_produto='SIMPLES' AND id<>? ORDER BY setor_preparo,descricao", (combo_id,)).fetchall()
    conn.close()
    return render_template("combo_config.html", combo=combo, itens=itens, produtos=produtos)

@app.route("/produto/combo/remover/<int:item_id>")
@login_required
@perfil_required("ADMIN")
def combo_remover_item(item_id):
    conn = conectar()
    item = conn.execute("SELECT * FROM combo_itens WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close(); flash("Item não encontrado.", "danger"); return redirect(url_for("produtos"))
    combo_id = item["combo_id"]
    conn.execute("DELETE FROM combo_itens WHERE id=?", (item_id,))
    conn.commit(); conn.close(); flash("Item removido do combo.", "success")
    return redirect(url_for("combo_config", combo_id=combo_id))

@app.route("/cozinha")
@login_required
@perfil_required("COZINHA","ADMIN")
def cozinha():
    setor = request.args.get("setor","COZINHA")
    titulo = {"CHURRASQUEIRA":"Churrasqueira","COZINHA":"Cozinha","BAR":"Bar/Bebidas"}.get(setor,"Cozinha")
    return render_template("cozinha.html", setor=setor, titulo=titulo)

@app.route("/churrasqueira")
@login_required
@perfil_required("COZINHA","ADMIN")
def churrasqueira():
    return redirect(url_for("cozinha", setor="CHURRASQUEIRA"))

@app.route("/bar")
@login_required
@perfil_required("COZINHA","ADMIN")
def bar():
    return redirect(url_for("cozinha", setor="BAR"))

@app.route("/api/pedidos_cozinha")
@login_required
def api_pedidos_cozinha():
    setor = request.args.get("setor","COZINHA")
    conn = conectar()
    pedidos = conn.execute("""SELECT p.id,p.quantidade,p.ponto_carne,p.observacao,p.status,p.data_hora,pr.descricao produto,pr.setor_preparo,c.numero comanda,c.mesa,c.cliente
                              FROM pedidos p JOIN produtos pr ON pr.id=p.produto_id JOIN comandas c ON c.id=p.comanda_id
                              WHERE p.status IN ('PENDENTE','EM PREPARO')
                                AND c.status='ABERTA'
                                AND pr.setor_preparo=?
                                AND COALESCE(pr.tipo_produto, 'SIMPLES') <> 'COMBO'
                              ORDER BY p.data_hora ASC,p.id ASC""", (setor,)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in pedidos])


@app.route("/api/pedidos_setor_agrupado")
@login_required
def api_pedidos_setor_agrupado():
    setor = request.args.get("setor", "COZINHA")
    conn = conectar()

    pedidos = conn.execute("""
        SELECT
            p.id,
            p.quantidade,
            p.ponto_carne,
            p.observacao,
            p.status,
            p.data_hora,
            pr.descricao AS produto,
            pr.setor_preparo,
            c.id AS comanda_id,
            c.numero AS comanda,
            c.mesa,
            c.cliente
        FROM pedidos p
        JOIN produtos pr ON pr.id = p.produto_id
        JOIN comandas c ON c.id = p.comanda_id
        WHERE p.status IN ('PENDENTE','EM PREPARO')
          AND c.status = 'ABERTA'
          AND pr.setor_preparo = ?
          AND COALESCE(pr.tipo_produto, 'SIMPLES') <> 'COMBO'
        ORDER BY p.data_hora ASC, p.id ASC
    """, (setor,)).fetchall()

    grupos = {}
    ordem = []

    for p in pedidos:
        chave = f"{p['comanda_id']}_{setor}"
        if chave not in grupos:
            grupos[chave] = {
                "chave": chave,
                "comanda_id": p["comanda_id"],
                "comanda": p["comanda"],
                "mesa": p["mesa"],
                "cliente": p["cliente"],
                "setor": setor,
                "primeiro_horario": p["data_hora"],
                "status_geral": "PENDENTE",
                "itens": []
            }
            ordem.append(chave)

        if p["status"] == "EM PREPARO":
            grupos[chave]["status_geral"] = "EM PREPARO"

        grupos[chave]["itens"].append({
            "id": p["id"],
            "quantidade": p["quantidade"],
            "produto": p["produto"],
            "ponto_carne": p["ponto_carne"],
            "observacao": p["observacao"],
            "status": p["status"],
            "data_hora": p["data_hora"]
        })

    resultado = [grupos[k] for k in ordem]
    conn.close()
    return jsonify(resultado)


@app.route("/pedido_status_comanda_setor/<int:comanda_id>/<setor>/<status>")
@login_required
@perfil_required("COZINHA","GARCOM","ADMIN")
def pedido_status_comanda_setor(comanda_id, setor, status):
    mapa = {
        "preparo": "EM PREPARO",
        "pronto": "PRONTO"
    }

    if status not in mapa:
        flash("Status inválido.", "danger")
        return redirect(url_for("cozinha", setor=setor))

    novo_status = mapa[status]
    conn = conectar()

    conn.execute("""
        UPDATE pedidos
        SET status = ?
        WHERE comanda_id = ?
          AND status IN ('PENDENTE','EM PREPARO')
          AND produto_id IN (
              SELECT id FROM produtos
              WHERE setor_preparo = ?
                AND COALESCE(tipo_produto, 'SIMPLES') <> 'COMBO'
          )
    """, (novo_status, comanda_id, setor))

    conn.commit()
    conn.close()

    return redirect(url_for("cozinha", setor=setor))



@app.route("/pedido_status/<int:pedido_id>/<status>")
@login_required
@perfil_required("COZINHA","GARCOM","ADMIN")
def pedido_status(pedido_id, status):
    mapa = {"pendente":"PENDENTE","preparo":"EM PREPARO","pronto":"PRONTO","entregue":"ENTREGUE"}
    if status not in mapa:
        flash("Status inválido.", "danger"); return redirect(url_for("cozinha"))
    conn = conectar(); conn.execute("UPDATE pedidos SET status=? WHERE id=?", (mapa[status], pedido_id)); conn.commit(); conn.close()
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/caixa")
@login_required
@perfil_required("CAIXA","ADMIN")
def caixa():
    conn = conectar()
    lista = conn.execute("""SELECT c.*, COALESCE(SUM(p.quantidade*p.valor_unitario),0) total FROM comandas c
                            LEFT JOIN pedidos p ON p.comanda_id=c.id WHERE c.status='ABERTA'
                            GROUP BY c.id ORDER BY c.data_abertura DESC""").fetchall()
    conn.close()
    return render_template("caixa.html", comandas=lista)

@app.route("/fechar_comanda/<int:comanda_id>", methods=["GET","POST"])
@login_required
@perfil_required("CAIXA","ADMIN")
def fechar_comanda(comanda_id):
    conn = conectar()
    comanda = conn.execute("SELECT * FROM comandas WHERE id=?", (comanda_id,)).fetchone()
    pedidos = conn.execute("""SELECT p.*, pr.descricao FROM pedidos p JOIN produtos pr ON pr.id=p.produto_id WHERE p.comanda_id=? ORDER BY p.data_hora ASC""", (comanda_id,)).fetchall()
    total = sum([p["quantidade"]*p["valor_unitario"] for p in pedidos])
    if request.method == "POST":
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO pagamentos (comanda_id,valor,forma_pagamento,data_pagamento) VALUES (?,?,?,?)", (comanda_id,total,request.form["forma_pagamento"],agora))
        conn.execute("UPDATE comandas SET status='FECHADA', data_fechamento=? WHERE id=?", (agora,comanda_id))
        conn.commit(); conn.close(); flash("Comanda fechada.", "success"); return redirect(url_for("caixa"))
    conn.close()
    return render_template("fechar_comanda.html", comanda=comanda, pedidos=pedidos, total=total)

# APIs do app garçom
@app.route("/api/app/health")
def api_app_health():
    return jsonify({"status":"ok","sistema":"EspetoControl","versao":"2.0","mensagem":"API disponível"})

@app.route("/api/app/login", methods=["POST"])
def api_app_login():
    d = request.get_json() or {}
    conn = conectar()
    u = conn.execute("SELECT id,nome,login,senha,perfil FROM usuarios WHERE login=? AND ativo=1", (d.get("login"),)).fetchone()
    conn.close()
    if not u or not check_password_hash(u["senha"], d.get("senha","")):
        return jsonify({"status":"erro","mensagem":"Login ou senha inválidos"}), 401
    if u["perfil"] not in ("GARCOM","ADMIN"):
        return jsonify({"status":"erro","mensagem":"Usuário sem permissão de garçom"}), 403
    return jsonify({"status":"ok","usuario":{"id":u["id"],"nome":u["nome"],"login":u["login"],"perfil":u["perfil"]}})

@app.route("/api/app/produtos")
def api_app_produtos():
    conn=conectar(); prods=conn.execute("SELECT id,descricao,categoria,valor,usa_ponto_carne,setor_preparo,tipo_produto FROM produtos WHERE ativo=1 ORDER BY categoria,descricao").fetchall(); conn.close()
    return jsonify({"status":"ok","produtos":[dict(p) for p in prods]})

@app.route("/api/app/comandas_abertas")
def api_app_comandas():
    conn=conectar(); lista=conn.execute("""SELECT c.id,c.numero,c.mesa,c.cliente,c.qtd_pessoas,c.status,c.data_abertura,u.nome garcom
                                           FROM comandas c LEFT JOIN usuarios u ON u.id=c.garcom_id WHERE c.status='ABERTA' ORDER BY c.data_abertura DESC""").fetchall(); conn.close()
    return jsonify({"status":"ok","comandas":[dict(c) for c in lista]})

@app.route("/api/app/nova_comanda", methods=["POST"])
def api_app_nova_comanda():
    d=request.get_json() or {}
    if not d.get("mesa") or not d.get("garcom_id"):
        return jsonify({"status":"erro","mensagem":"Mesa e garçom são obrigatórios"}),400
    conn=conectar(); ultimo=conn.execute("SELECT MAX(id) id FROM comandas").fetchone()["id"] or 0; numero=f"COM{ultimo+1:06d}"
    agora=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO comandas (numero,mesa,cliente,qtd_pessoas,garcom_id,data_abertura) VALUES (?,?,?,?,?,?)",
                 (numero,d.get("mesa"),d.get("cliente") or "Cliente",int(d.get("qtd_pessoas") or 1),d.get("garcom_id"),agora))
    conn.commit(); c=conn.execute("SELECT * FROM comandas WHERE numero=?", (numero,)).fetchone(); conn.close()
    return jsonify({"status":"ok","mensagem":"Comanda aberta","comanda":dict(c)})

@app.route("/api/app/comanda/<int:comanda_id>")
def api_app_comanda(comanda_id):
    conn=conectar(); c=conn.execute("SELECT * FROM comandas WHERE id=?", (comanda_id,)).fetchone()
    if not c: conn.close(); return jsonify({"status":"erro","mensagem":"Comanda não encontrada"}),404
    pedidos=conn.execute("""SELECT p.id,p.quantidade,p.valor_unitario,p.ponto_carne,p.observacao,p.status,p.data_hora,pr.descricao produto,pr.categoria,pr.setor_preparo
                            FROM pedidos p JOIN produtos pr ON pr.id=p.produto_id WHERE p.comanda_id=? ORDER BY p.data_hora ASC,p.id ASC""", (comanda_id,)).fetchall()
    total=sum([p["quantidade"]*p["valor_unitario"] for p in pedidos]); conn.close()
    return jsonify({"status":"ok","comanda":dict(c),"pedidos":[dict(p) for p in pedidos],"total":total})

@app.route("/api/app/lancar_pedido", methods=["POST"])
def api_app_lancar():
    d=request.get_json() or {}
    conn=conectar()
    c=conn.execute("SELECT * FROM comandas WHERE id=? AND status='ABERTA'", (d.get("comanda_id"),)).fetchone()
    if not c: conn.close(); return jsonify({"status":"erro","mensagem":"Comanda não encontrada ou fechada"}),404
    try:
        lancar_produto_ou_combo(conn, d.get("comanda_id"), d.get("produto_id"), int(d.get("quantidade") or 1), d.get("ponto_carne") or "", d.get("observacao") or "")
        conn.commit()
    except ValueError as e:
        conn.close()
        return jsonify({"status":"erro","mensagem":str(e)}),404
    conn.close()
    return jsonify({"status":"ok","mensagem":"Pedido enviado"})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
