# Sistema de Pedidos Online — Supermercado

Projeto acadêmico de estágio em desenvolvimento web: um sistema de pedidos online para
supermercado com entrega, construído como monólito Django com renderização no servidor.

Funcionalidades implementadas:

- **Catálogo público:** produtos ativos, com pesquisa que ignora maiúsculas e acentos, filtro por
  categoria e página de detalhes.
- **Carrinho:** fica na sessão, com valores calculados no servidor.
- **Contas de cliente:** cadastro, login e logout; senha com no mínimo 12 caracteres e limitação
  de tentativas de login.
- **Finalização da compra:** endereço, bairro atendido, taxa fixa de entrega e pagamento
  exclusivamente na entrega; o pedido é registrado de forma atômica e sem duplicidade.
- **Acompanhamento:** consulta dos próprios pedidos pelo cliente.
- **Gerenciamento:** painel da equipe autorizada para atualizar os estados dos pedidos.

A interface é responsiva, com cuidados de acessibilidade. A suíte automatizada tem 418 testes.

O README registra abaixo o estado atual e, em seguida, o histórico de cada semana do plano de
estágio. **Neste ambiente acadêmico, o catálogo, o bairro e a taxa de entrega usados na
demonstração são fictícios.**

## Documentação de uso

| Documento | Conteúdo |
| --- | --- |
| [Manual do cliente](docs/semana-12/manual-cliente.md) | Catálogo, carrinho, compra e acompanhamento do pedido. |
| [Manual da equipe interna](docs/semana-12/manual-equipe.md) | Gerenciamento de pedidos, estados e permissões. |
| [Manual de instalação e execução](docs/semana-12/manual-instalacao.md) | Instalação em desenvolvimento, testes e diferenças para a produção. |
| [Apresentação do sistema](docs/semana-12/apresentacao-sistema.md) | Estrutura dos slides, com textos, imagens e notas. |
| [Revisão da documentação](docs/semana-12/revisao-documentacao.md) | Índice dos documentos e divergências entre os registros semanais e o estado atual. |
| [Validação e testes-piloto](docs/semana-11/validacao-testes-piloto.md) | Dados demonstrativos, instalação limpa, testes-piloto e demonstração manual. |

## Pré-requisitos

- Windows com PowerShell.
- Python 3.14, disponível pelo comando `python` (validado com Python 3.14.7).
- Git, disponível pelo comando `git`.

O projeto utiliza Django 5.2 LTS (5.2.19). As versões das dependências estão fixadas em
`requirements.txt`.

## Instalação e execução

O procedimento completo, com a criação da conta da equipe e a solução de problemas comuns, está
no [manual de instalação](docs/semana-12/manual-instalacao.md). Resumo:

```powershell
git clone https://github.com/Daviizera/supermercado-estagio.git
cd supermercado-estagio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DJANGO_ENV = "development"
python manage.py migrate
python manage.py preparar_dados_demonstracao
python manage.py runserver
```

Abra <http://127.0.0.1:8000/> e encerre o servidor com `Ctrl+C`.

- **Ambiente obrigatório:** `DJANGO_ENV` precisa estar definido como `development` em cada janela
  do PowerShell. Sem ele, os comandos são interrompidos com `ImproperlyConfigured`.
- **Política de execução:** se o PowerShell bloquear a ativação, use diretamente
  `.\.venv\Scripts\python.exe` no lugar de `python`.

## Verificação

Com o ambiente ativo e `DJANGO_ENV` definido:

```powershell
python -W default manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pip check
```

Resultado atual:

- `test`: 418 testes aprovados, sem avisos;
- `check`: nenhum problema;
- `makemigrations --check --dry-run`: nenhuma migration pendente;
- `pip check`: nenhum conflito de dependências.

Os testes usam um banco temporário e não alteram o `db.sqlite3`.

## Estrutura e configuração

```text
manage.py
supermercado/
    settings.py              # Configuração central (ambientes, segurança, entrega, limite de login)
    ambiente.py              # Leitura e validação das variáveis de ambiente
principal/
    models.py, views.py, forms.py, admin.py, urls.py, apps.py
    carrinho.py              # Carrinho da sessão e cálculo dos valores
    checkout.py              # Finalização da compra e registro atômico dos pedidos
    pedidos.py               # Permissões e transições de estado dos pedidos
    busca.py                 # Busca e ordenação sem diferenciar maiúsculas e acentos
    limite_login.py          # Limitação de tentativas de login (site e Django Admin)
    management/commands/preparar_dados_demonstracao.py
    migrations/0001 a 0004
    test_*.py, tests.py      # 418 testes automatizados
templates/                   # base.html, principal/*.html e registration/*.html
static/css/estilos.css
docs/semana-02/ a docs/semana-12/
requirements.txt
.gitignore
README.md
```

O banco SQLite fica em `db.sqlite3`, na raiz, e é criado pelas migrations. Esse arquivo, o
ambiente `.venv`, a chave local `.chave-secreta-local` e os caches são ignorados pelo Git.

**Ambientes.** A variável `DJANGO_ENV` é obrigatória e aceita somente `development` ou
`production`.

- **Desenvolvimento:**
  - `DEBUG` ativado e hosts locais;
  - chave secreta lida de `DJANGO_SECRET_KEY` ou de um arquivo local gerado automaticamente;
  - bairro "Bairro Ficticio de Teste" e taxa de R$ 5,00 apenas para demonstração.
- **Produção:** exige `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, HTTPS e um cache compartilhado
  para a limitação de login. Nunca usa os valores fictícios de entrega.

Nenhuma chave secreta fica no código. Os detalhes estão na seção 14 do
[manual de instalação](docs/semana-12/manual-instalacao.md#14-segurança-desenvolvimento-e-produção).

## Histórico por semana

As seções a seguir registram o que foi entregue e validado ao final de cada semana. Algumas
afirmações foram superadas pelas semanas seguintes, por exemplo:

- a configuração de entrega, a chave de desenvolvimento e a limitação da busca com acentos;
- as contagens de testes, que valem para a semana em que foram registradas.

Quando houver divergência, prevalecem as seções anteriores deste README e os documentos da
Semana 12. A [revisão da documentação](docs/semana-12/revisao-documentacao.md) lista as
divergências conhecidas.

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

> **Atualização (Semanas 11 e 12):** os comandos desta seção exigem `$env:DJANGO_ENV = "development"`. Para a operação de pedidos, use uma conta da equipe com as permissões específicas ([manual de instalação](docs/semana-12/manual-instalacao.md#9-conta-da-equipe)), não um superusuário.

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

> **Atualização (Semana 11):** a busca passou a ignorar acentos e maiúsculas também em letras acentuadas, e a ordenação agrupa "Água" com a letra A (F-01/F-02).

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

> **Atualização (Semana 11):** em `DJANGO_ENV=development`, o checkout usa o bairro demonstrativo "Bairro Ficticio de Teste" e a taxa de R$ 5,00; em produção, os valores continuam vazios e o checkout permanece bloqueado até a definição de valores reais. A `SECRET_KEY` deixou de ficar no código (ver [Estrutura e configuração](#estrutura-e-configuração)).

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

## Semana 9 — Testes automatizados e correção de falhas

A Semana 9 auditou a aplicação e a suíte de testes em relação aos requisitos, corrigiu as falhas encontradas e registrou os resultados exigidos por RNF-008 no [relatório da Semana 9](docs/semana-09/testes-correcao-falhas.md), com metodologia, inventário da suíte, matriz de cobertura, achados por severidade, testes antes e depois das correções, mutação e verificações de cálculos, permissões, segurança e concorrência.

Correções aplicadas, sempre com o teste de regressão escrito e executado antes:

- **Checkout:** com token de revisão inválido ou base desatualizada, o endereço digitado volta preenchido; a revisão continua recalculada no servidor.
- **Meus pedidos:** pedido inexistente ou de outro cliente responde 404 com “Pedido não encontrado ou acesso não permitido.”, de forma idêntica nos dois casos; o visitante encaminhado ao login a partir de Meus pedidos vê “Entre para consultar seus pedidos.”.
- **Suíte:** as conexões SQLite abertas pelas threads dos testes de concorrência são fechadas na própria thread (os 50 `ResourceWarning` deixaram de ocorrer), e os testes usam a API pública de mensagens do Django.

Foram acrescentados testes de escape de HTML, mascaramento de senhas em relatórios de erro, identificadores fora da faixa, perda de acesso durante a sessão e uma análise AST que impede o uso de `float` nos módulos que calculam valores. Não houve alteração de modelos, migrations, dependências ou regras comerciais.

```powershell
.\.venv\Scripts\python.exe -W default manage.py test
```

Na validação da Semana 9, os **293 testes passaram** sem avisos: 273 anteriores e 20 novos. `check`, `makemigrations --check --dry-run`, `pip check` e `git diff --check` não apontaram problemas. Continuam pendentes do supervisor D-001 a D-004, o limite provisório de R$ 5.000,00 e produtos com preço zero; os avisos de `check --deploy` ficam para a implantação.

## Semana 10 — Interface, responsividade e acessibilidade

A Semana 10 reorganizou a identidade visual com variáveis de CSS e pontos de quebra
mobile-first (40, 64 e 80 rem).

- **Tabelas:** viram cartões em telas estreitas, mantendo a semântica para leitores de tela.
- **Navegação móvel:** os itens da conta ficam no botão **Menu**.
- **Acessibilidade:**
  - link "Pular para o conteúdo" e indicação da página atual;
  - foco visível e áreas de toque de pelo menos 44 px;
  - mensagens diferenciadas por tipo;
  - nomes acessíveis nos botões repetidos.
- **Catálogo e detalhes do produto:** foram redesenhados.
- **Validação:** as medições foram feitas no Chrome com emulação real de viewport, em 360, 390,
  768, 1024 e 1440 px. Não se declara conformidade formal com a WCAG.

## Semana 11 — Segurança, dados demonstrativos e testes-piloto

**Segurança.**

- **Chave secreta:** a chave secreta exposta no histórico foi substituída e é recusada; nenhuma
  chave fica no código.
- **Ambientes:** a variável `DJANGO_ENV` passou a ser obrigatória e separa desenvolvimento de
  produção.
- **Login:** limitação de tentativas no site e no Django Admin; a produção exige cache
  compartilhado.
- **Senhas:** mínimo de 12 caracteres.
- **Dependências:** Django atualizado para 5.2.19.

**Dados e validação.** O comando `preparar_dados_demonstracao` cria 4 categorias e 18 produtos
fictícios, de forma idempotente e somente em desenvolvimento. A finalização da compra usa, apenas
em desenvolvimento, o bairro "Bairro Ficticio de Teste" e a taxa de R$ 5,00.

**Correções.** A busca e a ordenação com acentos foram corrigidas (falhas F-01 e F-02 do piloto).

**Registros.**

- A instalação limpa foi validada duas vezes.
- Os testes-piloto, a inspeção por HTTP real e a demonstração manual relatada pelo usuário estão
  em [validacao-testes-piloto.md](docs/semana-11/validacao-testes-piloto.md).

```powershell
$env:DJANGO_ENV = "development"
.\.venv\Scripts\python.exe -W default manage.py test
```

Na validação final da Semana 11, os **418 testes passaram** sem avisos.

## Semana 12 — Documentação, manuais e apresentação

A Semana 12 produziu os documentos listados em [Documentação de uso](#documentação-de-uso):

- os manuais do cliente, da equipe e de instalação, com capturas reais do sistema em
  `docs/semana-12/imagens/`;
- a estrutura da apresentação;
- a revisão da documentação existente.

Não houve alteração de código, modelos, migrations, configurações ou dependências.
