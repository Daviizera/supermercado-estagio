# Sistema de Pedidos Online — Supermercado

Projeto acadêmico de estágio em desenvolvimento web: um sistema de pedidos online para supermercado com entrega. A aplicação contém a fundação local em Django e a página inicial mínima da **Semana 1**. A **Semana 2** acrescenta a documentação de escopo, requisitos, fluxos e protótipos. A **Semana 3** implementa a modelagem de dados e o cadastro interno de categorias e produtos pelo Django Admin.

Catálogo público, contas de clientes, carrinho, checkout e operação de pedidos continuam previstos para as próximas etapas.

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
principal/                   # Página inicial, modelos, Admin, migrations e testes
docs/semana-02/               # Requisitos, regras, fluxos e protótipos
docs/semana-03/               # Documentação da modelagem de dados
templates/
    base.html
    principal/inicio.html
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

As decisões D-001 a D-007 da Semana 2 continuam sujeitas à validação registrada nos documentos. O uso do Admin foi solicitado para esta implementação; isso não representa aprovação do supervisor nem definição dos dados comerciais. Não há catálogo público, autenticação pública de clientes, carrinho, checkout ou gerenciamento operacional de pedidos nesta entrega.
