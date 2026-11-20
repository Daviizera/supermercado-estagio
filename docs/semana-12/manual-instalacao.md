# Manual de instalação e execução (desenvolvimento)

**Sistema de Pedidos Online para Supermercado com Entrega**

Este manual descreve como instalar e executar o projeto em um computador com Windows, no
**ambiente de desenvolvimento**, para estudo e demonstração. Ele **não** é um procedimento de
implantação em produção; a [seção 14](#14-segurança-desenvolvimento-e-produção) resume o que uma
implantação real exige.

Os comandos foram executados no Windows PowerShell em uma cópia limpa do projeto, com
Python 3.14.7, e produziram os resultados descritos.

## Sumário

1. [Pré-requisitos](#1-pré-requisitos)
2. [Instalar o Python](#2-instalar-o-python)
3. [Obter o projeto](#3-obter-o-projeto)
4. [Criar e ativar o ambiente virtual](#4-criar-e-ativar-o-ambiente-virtual)
5. [Instalar as dependências](#5-instalar-as-dependências)
6. [Definir o ambiente de desenvolvimento](#6-definir-o-ambiente-de-desenvolvimento)
7. [Chave secreta local](#7-chave-secreta-local)
8. [Criar o banco e os dados demonstrativos](#8-criar-o-banco-e-os-dados-demonstrativos)
9. [Conta da equipe](#9-conta-da-equipe)
10. [Iniciar o servidor](#10-iniciar-o-servidor)
11. [Acessar pelo navegador](#11-acessar-pelo-navegador)
12. [Executar os testes automatizados](#12-executar-os-testes-automatizados)
13. [Encerrar o servidor](#13-encerrar-o-servidor)
14. [Segurança: desenvolvimento e produção](#14-segurança-desenvolvimento-e-produção)
15. [Problemas comuns](#15-problemas-comuns)

## 1. Pré-requisitos

- Windows 10 ou 11, com Windows PowerShell.
- Python 3.14; o projeto foi validado com 3.14.7.
- Git.
- Acesso à internet para instalar as dependências do Python Package Index (PyPI).
- Um navegador web.

O banco de dados é um arquivo SQLite criado automaticamente. Não é preciso instalar um servidor
de banco de dados.

## 2. Instalar o Python

1. Baixe o instalador do Python 3.14 em <https://www.python.org/downloads/windows/>.
2. Na primeira tela do instalador, marque **Add python.exe to PATH** e conclua a instalação.
3. Abra um novo PowerShell e confira:

```powershell
python --version
git --version
```

O primeiro comando deve mostrar `Python 3.14.x`.

## 3. Obter o projeto

```powershell
git clone https://github.com/Daviizera/supermercado-estagio.git
cd supermercado-estagio
```

> **Atenção:** este manual descreve a versão com as alterações das Semanas 10 a 12. Elas só
> estarão no repositório depois de publicadas. Uma versão anterior (por exemplo, o commit
> `a164f96`) segue as instruções do README daquela versão.

Todos os comandos seguintes são executados na pasta do projeto, onde fica o arquivo
`manage.py`.

## 4. Criar e ativar o ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Com o ambiente ativo, o início da linha do PowerShell mostra `(.venv)`.

Se o PowerShell bloquear `Activate.ps1` por causa da política de execução de scripts, há duas
alternativas.

**Liberar os scripts somente nesta janela** (a configuração não fica gravada):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**Não ativar o ambiente** e chamar o Python dele diretamente, substituindo `python` por
`.\.venv\Scripts\python.exe` em todos os comandos deste manual:

```powershell
.\.venv\Scripts\python.exe --version
```

## 5. Instalar as dependências

```powershell
python -m pip install -r requirements.txt
python -m pip check
```

As dependências e suas versões estão fixadas em `requirements.txt`:

- Django 5.2.19;
- asgiref 3.12.1;
- sqlparse 0.6.0;
- tzdata 2026.5.

`pip check` deve informar `No broken requirements found.`.

## 6. Definir o ambiente de desenvolvimento

O projeto exige que o ambiente seja declarado explicitamente. Sem essa declaração, os comandos são
interrompidos com `ImproperlyConfigured: DJANGO_ENV não está definida.`

```powershell
$env:DJANGO_ENV = "development"
python manage.py check
```

O resultado esperado é `System check identified no issues (0 silenced).`

A variável vale somente para a janela atual do PowerShell. Em uma janela nova, defina-a de novo.
Para gravá-la para o seu usuário do Windows, valendo para as janelas abertas depois, use:

```powershell
[Environment]::SetEnvironmentVariable("DJANGO_ENV", "development", "User")
```

Os únicos valores aceitos são exatamente `development` e `production` (seção 14).

## 7. Chave secreta local

O Django precisa de uma chave secreta. **Nenhuma chave fica no código do projeto**, e a chave
antiga, publicada no histórico do repositório, é recusada pelo sistema.

**Comportamento padrão.** No primeiro comando executado com `DJANGO_ENV=development` (por
exemplo, o `check` da seção anterior), o projeto cria o arquivo `.chave-secreta-local`, com uma
chave aleatória própria deste computador.

- O arquivo é ignorado pelo Git. Não o compartilhe nem o envie ao repositório.
- Para gerar uma chave nova, apague o arquivo: ele será recriado no próximo comando. As sessões
  abertas no navegador deixam de valer.

**Alternativa: variável de ambiente.** Se a variável `DJANGO_SECRET_KEY` estiver definida, ela
tem prioridade sobre o arquivo. Para gerar uma chave adequada:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copie o valor gerado para a variável:

```powershell
$env:DJANGO_SECRET_KEY = "<valor gerado>"
```

Não grave esse valor em arquivos do projeto. Chaves curtas, repetitivas ou com o prefixo
`django-insecure` são recusadas.

## 8. Criar o banco e os dados demonstrativos

```powershell
python manage.py migrate
python manage.py preparar_dados_demonstracao
```

- **`migrate`** cria o arquivo `db.sqlite3`, que também é ignorado pelo Git.
- **`preparar_dados_demonstracao`** cria 4 categorias e 18 produtos fictícios:
  - só cria o que falta e nunca altera nem apaga registros existentes;
  - pode ser executado de novo sem duplicar nada;
  - funciona somente com `DJANGO_ENV=development`;
  - não cria contas nem pedidos.

Também em desenvolvimento, a finalização da compra usa valores **demonstrativos**: o bairro
**Bairro Ficticio de Teste** e a taxa de entrega de **R$ 5,00**. Eles servem apenas à
demonstração acadêmica.

## 9. Conta da equipe

A conta da equipe precisa ser marcada como integrante da equipe (`is_staff`) e receber as
permissões `principal.view_pedido` (consultar pedidos) e `principal.change_pedido` (alterar o
estado). Ela não precisa ser superusuário.

Com o ambiente ativo e `DJANGO_ENV` definido, abra o shell do Django:

```powershell
python manage.py shell
```

Cole o bloco abaixo. Se quiser, troque `equipe_demonstracao` pelo nome desejado.

```python
from getpass import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password

usuario = get_user_model()(username='equipe_demonstracao', is_staff=True)
senha = getpass('Senha da conta da equipe: ')
validate_password(senha, usuario)
usuario.set_password(senha)
usuario.save()
usuario.user_permissions.add(*Permission.objects.filter(
    content_type__app_label='principal', codename__in=['view_pedido', 'change_pedido']))
```

A senha é digitada sem aparecer na tela e passa pelas mesmas regras do cadastro de clientes:

- pelo menos 12 caracteres;
- não parecida com o nome de usuário;
- não comum;
- não somente numérica.

Se ela for recusada, o shell mostra `ValidationError` com o motivo e nada é gravado. Nesse caso,
repita a partir da linha `senha = getpass(...)`. Ao terminar, saia com `exit()`.

Não use senhas padrão nem as registre em documentos. As contas de clientes são criadas pela
página **Cadastro** do próprio sistema.

## 10. Iniciar o servidor

```powershell
python manage.py runserver
```

O servidor fica em execução nessa janela e mostra o endereço
`http://127.0.0.1:8000/`.

## 11. Acessar pelo navegador

| Endereço | Conteúdo |
|---|---|
| <http://127.0.0.1:8000/> | Página inicial |
| <http://127.0.0.1:8000/catalogo/> | Catálogo de produtos |
| <http://127.0.0.1:8000/cadastro/> | Criação de conta de cliente |
| <http://127.0.0.1:8000/login/> | Login de clientes e da equipe |
| <http://127.0.0.1:8000/equipe/pedidos/> | Gerenciamento de pedidos (equipe autorizada) |

O uso do sistema está descrito no [manual do cliente](manual-cliente.md) e no
[manual da equipe](manual-equipe.md).

## 12. Executar os testes automatizados

Em outra janela do PowerShell, ative o ambiente, defina `DJANGO_ENV` e execute:

```powershell
python -W default manage.py test
```

Resultado esperado nesta versão: `Ran 418 tests` e `OK`, sem avisos. Os testes usam um banco
temporário em memória e não alteram o `db.sqlite3`.

Verificações complementares:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python -m pip check
```

Resultados esperados:

- `check`: nenhum problema;
- `makemigrations --check --dry-run`: `No changes detected`;
- `pip check`: nenhum conflito de dependências.

## 13. Encerrar o servidor

Na janela em que o servidor está em execução, pressione `Ctrl+C`. Para sair do ambiente virtual,
use `deactivate`.

## 14. Segurança: desenvolvimento e produção

Este manual configura somente o **desenvolvimento**.

| Aspecto | Desenvolvimento (`DJANGO_ENV=development`) | Produção (`DJANGO_ENV=production`) |
|---|---|---|
| `DEBUG` | Ativado | Desativado |
| Chave secreta | `DJANGO_SECRET_KEY` ou arquivo local gerado automaticamente | `DJANGO_SECRET_KEY` obrigatória; sem ela o sistema não inicia |
| Hosts | Somente locais (`127.0.0.1`, `localhost`) | `DJANGO_ALLOWED_HOSTS` obrigatória, sem curingas |
| Origens confiáveis para CSRF | Não se aplica | `DJANGO_CSRF_TRUSTED_ORIGINS`, somente `https://` |
| HTTPS, cookies seguros e HSTS | Desativados (HTTP local) | Ativados; `DJANGO_SECURE_HSTS_SECONDS` começa em 3600 s |
| Bairros e taxa de entrega | Valores fictícios de demonstração | **Nunca** usa os valores fictícios. Sem valores reais, a finalização da compra fica bloqueada |
| Cache da limitação de tentativas de login | Memória local do processo | Cache compartilhado obrigatório (Redis ou Memcached): `DJANGO_LIMITE_LOGIN_CACHE_BACKEND` e `DJANGO_LIMITE_LOGIN_CACHE_LOCATION`. Cache local é recusado |

Antes de uma publicação real, ainda são necessários:

- **Infraestrutura:** domínio e certificado HTTPS válidos.
- **Proxy:** definir o tratamento de um proxy reverso confiável. Sem isso, o limite de
  tentativas por endereço IP veria apenas o IP do proxy.
- **Cache:** um servidor de cache compartilhado e o pacote Python correspondente, que não fazem
  parte das dependências atuais.
- **Dados reais de entrega:** os bairros atendidos e a taxa de entrega, decididos pelo
  responsável pelo negócio.
- **Arquivos estáticos:** executar `collectstatic` para a pasta `staticfiles/` e configurar um
  servidor de aplicação adequado, em vez do `runserver`.
- **Verificação final:** `python manage.py check --deploy` com as variáveis de produção.

O `runserver` e o SQLite local deste manual servem apenas ao desenvolvimento e à demonstração.

## 15. Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `ImproperlyConfigured: DJANGO_ENV não está definida.` | A janela atual não tem a variável. Execute `$env:DJANGO_ENV = "development"`. |
| `DJANGO_ENV deve ser exatamente "development" ou "production"` | O valor tem erro de digitação, maiúsculas ou espaços. |
| `O arquivo .chave-secreta-local contém uma chave inválida` | O arquivo foi alterado. Apague-o; ele será recriado. |
| `Activate.ps1 não pode ser carregado` | Política de execução do PowerShell. Veja a seção 4. |
| `Error: That port is already in use.` | Outro servidor está usando a porta 8000. Encerre-o ou use `python manage.py runserver 8001`. |
| A finalização da compra informa que a entrega não está disponível | O projeto não está em `development`, ou os valores de entrega foram removidos da configuração. |
