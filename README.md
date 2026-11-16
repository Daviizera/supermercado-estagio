# Sistema de Pedidos Online — Supermercado

Projeto acadêmico de estágio em desenvolvimento web: um sistema de pedidos online para supermercado com entrega. A aplicação contém a fundação local em Django e a página inicial mínima da **Semana 1**. A **Semana 2** acrescenta a documentação de escopo, requisitos, fluxos e protótipos. A **Semana 3** implementa a modelagem de dados e o cadastro interno de categorias e produtos pelo Django Admin. A **Semana 4** acrescenta cadastro, login, logout e uma área autenticada mínima para clientes. A **Semana 5** oferece o catálogo público de produtos ativos, com pesquisa, filtro por categoria e detalhes. A **Semana 6** acrescenta o carrinho de compras da sessão, com quantidades, remoção de itens e subtotal calculado no servidor. A **Semana 7** implementa a finalização da compra: endereço, bairro atendido, taxa fixa, limite de valor, revisão dos valores e registro atômico e idempotente do pedido, com pagamento na entrega. A **Semana 8** oferece o painel próprio de gerenciamento de pedidos para a equipe autorizada, com as transições de estado documentadas, e a consulta e o acompanhamento dos próprios pedidos pelos clientes.

As etapas seguintes do plano de estágio continuam previstas para as próximas semanas.

## Pré-requisitos

- Windows com PowerShell.
- Python 3.14 instalado e disponível pelo comando `python` (ambiente inicial validado com Python 3.14.7).
- Git instalado e disponível pelo comando `git`.

O projeto utiliza Django 5.2 LTS; as versões instaladas estão fixadas em `requirements.txt`.

## Instalação e execução

Clone o repositório do projeto e prepare o ambiente local:

```powershell
git clone https://github.com/Daviizera/supermercado-estagio.git
cd supermercado-estagio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Abra <http://127.0.0.1:8000/>. A página deve exibir “Sistema de Pedidos Online”, “Supermercado” e “Projeto de estágio em desenvolvimento web”. Encerre o servidor com `Ctrl+C`.

Se o PowerShell bloquear a ativação, use diretamente o Python do ambiente virtual, sem alterar a política de execução:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

## Verificação

Com o ambiente virtual ativado, execute:

```powershell
python manage.py check
python manage.py migrate
python manage.py test
```

Sem ativação, substitua `python` por `.\.venv\Scripts\python.exe` nesses comandos.

## Estrutura e configuração

```text
manage.py
supermercado/                 # Configuração do projeto Django
principal/                   # Página inicial, autenticação, catálogo, carrinho, checkout, modelos e Admin
    carrinho.py              # Carrinho da sessão e cálculo dos valores
    checkout.py              # Finalização da compra e registro atômico dos pedidos
    pedidos.py               # Permissões e transições de estado dos pedidos
    forms.py                 # Filtros do catálogo, quantidades e dados de entrega
    migrations/0001_initial.py
    migrations/0002_pedido_chave_idempotencia.py
    migrations/0003_preencher_chave_idempotencia.py
    migrations/0004_alter_pedido_chave_idempotencia.py
    test_auth.py
    test_catalogo.py
    test_carrinho.py
    test_checkout.py
    test_pedidos.py
docs/semana-02/               # Requisitos, regras, fluxos e protótipos
docs/semana-03/               # Documentação da modelagem de dados
docs/semana-04/               # Documentação da autenticação de clientes
docs/semana-05/               # Documentação do catálogo público
docs/semana-06/               # Documentação do carrinho de compras
docs/semana-07/               # Documentação da finalização da compra
docs/semana-08/               # Documentação do gerenciamento de pedidos
templates/
    base.html
    principal/inicio.html
    principal/minha_conta.html
    principal/catalogo.html
    principal/detalhe_produto.html
    principal/carrinho.html
    principal/checkout.html
    principal/confirmacao_pedido.html
    principal/meus_pedidos.html
    principal/equipe_pedidos.html
    principal/equipe_pedido_detalhe.html
    principal/acesso_negado.html
    registration/cadastro.html
    registration/login.html
static/css/estilos.css
requirements.txt
.gitignore
README.md
```

A rota `/` renderiza um template Django, com CSS mínimo servido pelos arquivos estáticos em desenvolvimento.

O banco SQLite fica em `db.sqlite3`, na raiz, e é criado pelas migrations. Não exige instalação de servidor de banco. Esse arquivo, o ambiente `.venv` e os caches locais são ignorados pelo Git.

A infraestrutura padrão do Django fornece a autenticação e as permissões do cadastro interno em `/admin/`. A página pública continua mínima. A configuração é exclusivamente de desenvolvimento local, com `DEBUG = True` e chave de desenvolvimento definida no projeto; nenhum arquivo `.env` é necessário nesta etapa.

## Semana 2 — Escopo, requisitos e protótipos

A Semana 2 documenta o comportamento esperado da primeira versão antes da modelagem do banco. Os artefatos estão em `docs/semana-02/`:

- [Requisitos, critérios de aceite, semanas futuras e decisões pendentes](docs/semana-02/requisitos.md).
- [Regras de negócio](docs/semana-02/regras-negocio.md).
- [Fluxo de compra do cliente](docs/semana-02/fluxo-compra.md).
- [Fluxo operacional dos pedidos](docs/semana-02/fluxo-pedidos.md).
- [Protótipos textuais das interfaces](docs/semana-02/prototipos.md).

Os documentos estão disponíveis para revisão; bairros, frete e demais decisões indicadas ainda dependem de validação. Na entrega da Semana 2, todas as funcionalidades descritas eram futuras. A seção seguinte registra o que foi implementado na Semana 3. A página inicial e as instruções de instalação e execução da Semana 1 permanecem preservadas.

## Semana 3 — Modelagem de dados e Django Admin

Os modelos `Categoria`, `Produto`, `Pedido` e `ItemPedido` estão em `principal/models.py`, com relacionamentos obrigatórios, restrições de integridade e migration inicial. Pedidos e itens possuem somente estrutura de persistência; o preenchimento automático dos dados históricos e os cálculos pertencem ao checkout futuro. A [documentação da modelagem](docs/semana-03/modelagem-dados.md) apresenta campos, diagrama, exclusões protegidas, limites das validações e decisões pendentes.

O Django Admin permite cadastrar, editar, listar e pesquisar categorias e produtos. Produtos têm filtros por categoria e atividade, além de preço e unidade na listagem. `Pedido` e `ItemPedido` não estão registrados no Admin. O acesso exige usuário ativo com acesso à equipe (`is_staff`) e as permissões da operação; um superusuário ativo possui todas essas permissões.

Após atualizar os arquivos, aplique as migrations existentes e execute as verificações usando o ambiente virtual:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py showmigrations principal
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe -m pip check
```

Os testes usam um banco temporário do Django, incluindo os usuários necessários às verificações. Não é necessário criar um usuário no banco local para executá-los.

Para utilizar o cadastro interno manualmente, crie seu próprio superusuário local pelo comando interativo padrão e inicie o servidor:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Acesse <http://127.0.0.1:8000/admin/> e entre com as credenciais que você definiu. Nenhuma credencial fixa é fornecida pelo projeto. A rota <http://127.0.0.1:8000/> continua exibindo a página inicial da Semana 1.

As decisões D-001 a D-007 da Semana 2 continuam sujeitas à validação registrada nos documentos. O uso do Admin foi solicitado para esta implementação; isso não representa aprovação do supervisor nem definição dos dados comerciais. Na entrega da Semana 3, ainda não havia catálogo público, autenticação pública de clientes, carrinho, checkout ou gerenciamento operacional de pedidos.

## Semana 4 — Conta do cliente e autenticação

O cadastro utiliza `UserCreationForm` e o usuário padrão do Django. São solicitados apenas nome de usuário, senha e confirmação. Um cadastro válido cria uma conta comum, sem acesso administrativo, informa o sucesso e redireciona para o login; não autentica automaticamente. Senhas passam pelos validadores e pelo armazenamento de hashes nativos do Django.

| Rota | Comportamento |
| --- | --- |
| `/` | Página inicial com navegação conforme a sessão. |
| `/cadastro/` | Exibe o formulário e recebe o cadastro por POST. |
| `/login/` | Exibe o formulário e autentica por POST; o destino padrão é `/minha-conta/`. |
| `/minha-conta/` | Exibe somente a identificação do usuário da sessão; visitantes são encaminhados ao login. |
| `/logout/` | Encerra a sessão exclusivamente por POST com CSRF e retorna à página inicial. GET não encerra a sessão. |
| `/admin/` | Cadastro interno existente, com autenticação e permissões administrativas preservadas. |

Para demonstrar o fluxo, inicie o servidor, abra `/cadastro/`, defina suas próprias credenciais e conclua o cadastro. Entre em `/login/`, confira a identificação em `/minha-conta/` e utilize o botão **Sair**. Depois do logout, acessar a área privada exige novo login. O cadastro manual cria um usuário no seu banco local; os testes automatizados usam exclusivamente o banco temporário do Django.

Execute a suíte específica e, para verificar as semanas anteriores, a suíte completa:

```powershell
.\.venv\Scripts\python.exe manage.py test principal.test_auth
.\.venv\Scripts\python.exe manage.py test
```

A [documentação da autenticação](docs/semana-04/autenticacao-clientes.md) descreve formulários, sessões, validações, segurança, critérios de aceite e limites. A integração da autorização com checkout e pedidos depende das Semanas 7 e 8; essas rotas ainda não existem. Não foram adicionados modelos, migrations ou dependências nesta etapa.

Na validação da Semana 4, os 61 testes passaram: 37 das etapas anteriores e 24 novos de autenticação. Os testes verificam também CSRF, isolamento entre sessões, redirecionamentos seguros e preservação das permissões administrativas.

## Semana 5 — Catálogo de produtos

Visitantes e clientes autenticados podem abrir <http://127.0.0.1:8000/catalogo/> pelo link **Catálogo** da navegação. A lista mostra somente produtos ativos, com nome, categoria, preço em reais, unidade e acesso aos detalhes em `/produtos/<id>/`. Produtos inativos ou inexistentes retornam HTTP 404 na consulta de detalhes.

Use o campo de pesquisa para buscar parte do nome e selecione uma categoria para combinar os filtros. Limpar apenas o texto mantém a categoria; selecionar **Todas as categorias** remove apenas esse filtro. O link **Limpar filtros** retorna ao catálogo completo. As consultas usam GET e não alteram os produtos.

A busca usa `icontains` do Django: ignora diferenças entre maiúsculas e minúsculas em caracteres ASCII, mas o SQLite possui limitações para caracteres fora desse conjunto e não há remoção de acentos. Categoria inexistente ou inválida e pesquisa com mais de 150 caracteres mostram erro de validação, sem listar produtos. Os detalhes dessas decisões estão na [documentação do catálogo](docs/semana-05/catalogo-produtos.md).

Os produtos são os mesmos mantidos pelo Django Admin da Semana 3. Alterações de nome, preço, unidade, categoria e disponibilidade aparecem nas consultas seguintes. Nenhum dado comercial de demonstração é criado automaticamente; se não houver produtos ativos, a página informa **“Nenhum produto disponível no momento.”**.

Para verificar o catálogo e a regressão das semanas anteriores, execute:

```powershell
.\.venv\Scripts\python.exe manage.py test principal.test_catalogo
.\.venv\Scripts\python.exe manage.py test
```

Os testes utilizam exclusivamente o banco temporário do Django. Não foram adicionados modelos, migrations ou dependências. Autenticação e permissões administrativas permanecem preservadas; carrinho, checkout e pedidos públicos não fazem parte desta entrega.

Na validação final da retomada em 28/10/2026, os **86 testes passaram**: 61 das semanas anteriores e 25 de catálogo. `check`, `makemigrations --check --dry-run`, `migrate` e `pip check` passaram, sem migrations pendentes ou alterações no SQLite local. O relatório e a correção do dado fictício de unidade usado no teste do Admin estão na [documentação da Semana 5](docs/semana-05/catalogo-produtos.md#validação-final-da-retomada--28102026).

## Semana 6 — Carrinho de compras

Visitantes e clientes autenticados podem adicionar produtos ativos pelo catálogo ou pelos detalhes do produto, informando a quantidade (inicialmente 1), e consultar o carrinho em <http://127.0.0.1:8000/carrinho/> pelo link **Carrinho** da navegação. O carrinho mostra produto, unidade, preço unitário, quantidade, valor de cada item e subtotal, e permite atualizar a quantidade ou remover cada item.

O carrinho pertence à sessão do Django: guarda somente identificadores de produtos e quantidades, sem preços. Nome, preço e disponibilidade são lidos do banco a cada visualização; por isso, alterações feitas no Django Admin aparecem na próxima consulta. Os valores são calculados no servidor com `Decimal`, e valores enviados pelo navegador são ignorados. O login preserva o carrinho; o logout limpa a sessão e, com ela, o carrinho.

A quantidade deve ser um inteiro positivo escrito somente com dígitos: zero, negativos, frações, `2.0`, texto e campo vazio são rejeitados, mantendo a quantidade anterior. Zero não remove itens; a remoção é uma ação própria. Adicionar novamente um produto soma a quantidade na mesma linha. Produto desativado ou excluído depois da inclusão permanece identificado como indisponível até ser removido, com a mensagem **“Há produto indisponível no carrinho. Remova o item para continuar.”**. Adicionar, atualizar e remover usam POST com proteção CSRF.

Checkout, taxa de entrega, total, pagamento e criação de pedidos não fazem parte desta entrega. Não foram adicionados modelos, migrations ou dependências. As decisões técnicas provisórias, os pontos que dependem do supervisor e o risco de capacidade dos campos de valor do pedido para a Semana 7 estão na [documentação do carrinho](docs/semana-06/carrinho-compras.md).

Para verificar o carrinho e a regressão das semanas anteriores, execute:

```powershell
.\.venv\Scripts\python.exe manage.py test principal.test_carrinho
.\.venv\Scripts\python.exe manage.py test
```

Após a auditoria técnica da Semana 6, o serviço do carrinho passou a validar as próprias entradas, quantidades com qualquer número de dígitos resultam em erro de validação e dados de sessão malformados são exibidos com aviso, sem erro interno e sem que a visualização reescreva a sessão. A documentação registra também a limitação de concorrência de requisições simultâneas na mesma sessão.

Na validação final da Semana 6, os **145 testes passaram**: 86 das semanas anteriores e 59 do carrinho. `check`, `makemigrations --check --dry-run`, `pip check` e `git diff --check` não apontaram problemas, e o SQLite local permaneceu inalterado.

## Semana 7 — Finalização da compra

Após aplicar as migrations da semana, clientes autenticados podem abrir **Finalizar compra** no carrinho (<http://127.0.0.1:8000/checkout/>). Visitantes são encaminhados ao login e retornam ao checkout com o carrinho preservado. A página apresenta itens, quantidades, preços, valores, subtotal, taxa de entrega e total calculados no servidor, o formulário de endereço (logradouro, número, complemento opcional, bairro e telefone) e o pagamento exclusivamente na entrega. A confirmação cria o pedido em **Recebido** e exibe a página `/pedidos/<id>/confirmacao/`, acessível somente ao próprio cliente.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

A entrega é configurada somente em `supermercado/settings.py`:

| Configuração | Valor atual |
| --- | --- |
| `CHECKOUT_BAIRROS_ATENDIDOS` | `()` — nenhum bairro real definido (D-001). |
| `CHECKOUT_TAXA_ENTREGA` | `None` — taxa não definida (D-002); `Decimal('0.00')` representaria entrega gratuita. |
| `CHECKOUT_VALOR_MAXIMO_PEDIDO` | `Decimal('5000.00')` — limite provisório do total, incluindo a taxa, pendente de validação do supervisor. |

**Com essa configuração, o checkout permanece bloqueado** com a mensagem “A entrega ainda não está disponível.” até que bairros e taxa sejam fornecidos. Nenhum bairro ou valor fictício foi definido; os testes usam valores próprios apenas durante a execução.

O pedido é criado em uma única transação, com `full_clean()` antes de salvar `Pedido` e cada `ItemPedido`, que guarda nome, unidade e preço do produto no momento da compra. Produtos inativos ou excluídos, entradas inconsistentes no carrinho, bairro não atendido, endereço incompleto e total acima do limite impedem o pedido e preservam o carrinho. Se nome, unidade, preço, itens, valores, taxa ou bairros configurados mudarem desde a revisão, os dados atualizados são apresentados e uma nova confirmação é exigida. Uma chave de idempotência UUID derivada no servidor do usuário e do último pedido, única no banco, impede pedidos duplicados em reenvios e em páginas de checkout abertas em paralelo; uma base que não gerou pedido só é aceita se for o último pedido atual do usuário, mesmo em token assinado; compras simultâneas do mesmo usuário iniciadas antes de qualquer conclusão contam como uma única tentativa. A `SECRET_KEY` do repositório é pública e de desenvolvimento; em produção, deve ser privada e fornecida por variável de ambiente. Após o sucesso, somente o carrinho é removido da sessão; a autenticação é mantida. O carrinho também oferece a remoção explícita dos registros não identificados.

Foram acrescentadas as migrations `0002` a `0004`, que adicionam e preenchem `Pedido.chave_idempotencia` em etapas seguras para pedidos preexistentes. Detalhes, decisões provisórias e pendências estão na [documentação da finalização](docs/semana-07/finalizacao-compra.md).

```powershell
.\.venv\Scripts\python.exe manage.py test principal.test_checkout
.\.venv\Scripts\python.exe manage.py test
```

Na validação da Semana 7, os **233 testes passaram**: 145 das semanas anteriores e 88 da finalização. `check`, `makemigrations --check --dry-run`, `pip check` e `git diff --check` não apontaram problemas. Consulta de pedidos, acompanhamento e operação pela equipe não fazem parte desta entrega.

## Semana 8 — Gerenciamento de pedidos e acompanhamento

Clientes autenticados acessam **Meus pedidos** (<http://127.0.0.1:8000/pedidos/>), com identificador, data, total e estado atual somente dos próprios pedidos, e o acompanhamento de cada pedido em `/pedidos/<id>/`, com itens, valores, endereço e estado. O novo estado aparece ao abrir ou recarregar a página; não há notificações nem atualização em tempo real. A confirmação da Semana 7, em `/pedidos/<id>/confirmacao/`, continua disponível.

A equipe usa o painel próprio **Gerenciamento de pedidos** (<http://127.0.0.1:8000/equipe/pedidos/>), com a lista dos pedidos e o detalhe completo, em modo somente leitura, de cada um. O Django Admin não lista nem altera pedidos. O acesso exige usuário com `is_staff` e as permissões nativas do Django:

| Operação | Permissão |
| --- | --- |
| Consultar lista e detalhes | `principal.view_pedido` (“Can view pedido”) |
| Alterar o estado | `principal.change_pedido` (“Can change pedido”) |

As permissões são atribuídas manualmente no Admin, em **Usuários** ou **Grupos**; nenhum usuário, grupo ou permissão é criado automaticamente. Visitantes são encaminhados ao login, e usuários autenticados sem os requisitos recebem “Você não tem permissão para acessar esta área.”.

Os estados seguem a tabela documentada: Recebido → Confirmado → Em preparo → Saiu para entrega → Entregue, com cancelamento pela equipe somente em Recebido, Confirmado ou Em preparo. Entregue e Cancelado são terminais. Cada alteração é enviada por POST com CSRF e aplicada por uma única atualização condicional ao estado exibido na página: ações repetidas, páginas antigas e requisições simultâneas efetivam no máximo uma transição e recebem “O estado do pedido mudou. Atualize a consulta.”. Somente o estado é alterado; itens, valores e dados de entrega permanecem como registrados. Não há histórico de alterações de estado nem novas migrations. Detalhes, decisões e limitações estão na [documentação do gerenciamento](docs/semana-08/gerenciamento-pedidos.md).

```powershell
.\.venv\Scripts\python.exe manage.py test principal.test_pedidos
.\.venv\Scripts\python.exe manage.py test
```

Na validação da Semana 8, os **273 testes passaram**: 233 das semanas anteriores e 40 do gerenciamento de pedidos. `check`, `makemigrations --check --dry-run`, `pip check` e `git diff --check` não apontaram problemas.
