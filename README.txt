ESPETOCONTROL V1.6

Como rodar:
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py

Login:
admin
admin123

Novidades:
- Clique na linha da comanda para abrir histórico.
- Histórico da comanda no PC.
- Editar pedido.
- Excluir pedido.
- Pedidos PRONTO/ENTREGUE ficam bloqueados para edição/exclusão.
- API do app mantida.

VERSÃO 1.7
- Produto tipo SIMPLES ou COMBO.
- Cadastro de composição do combo.
- Espeto completo gera itens automáticos para Churrasqueira/Cozinha.
- Itens internos entram com valor R$ 0,00.
- API do app mantida.


VERSÃO 1.8

Correção:
- O painel da Churrasqueira/Cozinha/Bar não exibe mais o produto principal do tipo COMBO.
- O painel de produção exibe somente os itens reais de preparo.
- Exemplo:
  Histórico/Comanda:
    Espeto Completo Alcatra R$ 22,00
    Alcatra R$ 0,00
    Arroz R$ 0,00
    Farofa R$ 0,00
    Vinagrete R$ 0,00

  Churrasqueira:
    Alcatra

  Cozinha:
    Arroz
    Farofa
    Vinagrete


VERSÃO 1.9

Correção:
- Painel de produção agora agrupa por comanda/mesa e setor.
- A mesma mesa aparece uma única vez na fila da cozinha/churrasqueira/bar.
- Exemplo na cozinha:
  Mesa 03:
    1x Arroz
    1x Farofa
    1x Vinagrete
- Botões:
  Tudo em preparo
  Tudo pronto


VERSÃO 2.0

Correção do Dashboard:
- Pedidos Pendentes não conta mais cada item individual.
- Agora conta pedidos agrupados por comanda e setor.
- Exemplo:
  Mesa 03 / Cozinha = 1 pedido
  Mesa 03 / Churrasqueira = 1 pedido
- Itens internos de combo não inflacionam mais o painel.
