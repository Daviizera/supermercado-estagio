# Sistema de Pedidos Online — Supermercado

Projeto acadêmico de estágio em desenvolvimento web: um sistema de pedidos online para supermercado com entrega. Esta entrega corresponde somente à **Semana 1**, com a fundação local em Django e uma página inicial mínima.

Produtos, categorias, carrinho, pedidos, checkout e autenticação serão tratados nas próximas etapas.

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
principal/                   # Aplicação principal e página inicial
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

A infraestrutura padrão do Django permanece instalada, sem rotas de administração ou login, personalizações do Admin ou modelos do domínio do supermercado. A configuração é exclusivamente de desenvolvimento local, com `DEBUG = True` e chave de desenvolvimento definida no projeto; nenhum arquivo `.env` é necessário nesta etapa.
