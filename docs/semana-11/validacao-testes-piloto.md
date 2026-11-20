# Semana 11 — Atividade 11: dados fictícios, validação da instalação e testes-piloto

Registro técnico da preparação para a demonstração do **Sistema de Pedidos Online para
Supermercado com Entrega**. Este documento separa três tipos de verificação:

- **testes automatizados**: suíte do Django, executada no banco de testes;
- **inspeção automatizada**: telas e fluxos percorridos por scripts, inclusive por HTTP real em
  uma cópia isolada;
- **demonstração manual**: navegação feita por uma pessoa no navegador.

> **Demonstração manual: realizada pelo usuário, conforme relato dele (seção 8.4).** Data,
> horário, navegador e capturas não foram fornecidos e, por isso, não estão registrados.

### Resumo por tipo de verificação

| Tipo | Situação | Onde |
|---|---|---|
| Testes automatizados | Executados: 418 testes, aprovados, sem avisos | Seções 5 e 7 |
| Inspeção automatizada (telas e HTTP real) | Executada: fluxo completo do cliente e da equipe, até Entregue | Seção 6 |
| Demonstração manual | Executada pelo usuário no fluxo do cliente, até o pedido Recebido; etapas da equipe não executadas manualmente, por decisão do usuário | Seção 8.4 |

## 1. Objetivo

Verificar, sem desenvolver funcionalidades novas, que:

- a instalação do projeto pode ser reproduzida em um ambiente limpo;
- dados demonstrativos podem ser preparados de forma segura e repetível;
- visitante, cliente e equipe interna percorrem os fluxos previstos;
- os valores financeiros e as permissões continuam protegidos pelo servidor.

## 2. Ambiente

| Item | Valor |
|---|---|
| Sistema | Windows 11, PowerShell |
| Python | 3.14.7 |
| Django | 5.2.19 (`requirements.txt`) |
| Banco | SQLite (`db.sqlite3`, fora do controle de versão) |
| Ambiente Django | `DJANGO_ENV=development` (obrigatório e explícito) |
| Entrega (somente `development`) | bairro demonstrativo "Bairro Ficticio de Teste" e taxa de R$ 5,00 (seção 3.4) |
| Base do código | commit `a164f96` + alterações locais das Semanas 10 e 11 (não publicadas) |

O banco persistente não foi usado pelos testes automatizados: eles rodam no banco de testes
em memória do Django.

## 3. Dados fictícios

### 3.1. Estratégia

Foi criado o comando `python manage.py preparar_dados_demonstracao`, em vez de uma fixture.
Uma fixture (`loaddata`) grava pela chave primária e **sobrescreve** a linha com o mesmo `pk`.
Como `Produto` não tem chave natural, ela não seria idempotente nem segura para um banco que
já tenha dados.

O comando:

- identifica categorias pelo nome (campo único) e produtos pela combinação categoria + nome;
- cria somente o que falta, nunca altera nem apaga registros existentes, e uma segunda
  execução não cria nada;
- executa `full_clean()` antes de cada gravação e trabalha em uma única transação (`atomic`);
- recusa qualquer ambiente diferente de `development`;
- não cria usuários, senhas, superusuários nem pedidos;
- informa o que foi criado e o que já existia.

### 3.2. Conteúdo

Quatro categorias e 18 produtos, com nomes genéricos (sem marcas), preços de R$ 2,49 a R$ 49,90,
sem promoções, descontos, estoque, descrições ou imagens (o modelo não tem esses campos).

| Categoria | Produtos (preço — unidade) |
|---|---|
| Mercearia | Arroz branco tipo 1 (24,90 — pacote 5 kg); Feijão carioca (8,49 — pacote 1 kg); Macarrão espaguete (4,79 — pacote 500 g); Açúcar cristal (5,29 — pacote 1 kg); Óleo de soja (7,99 — garrafa 900 mL); Café em grãos torra média para preparo em cafeteira ou moedor (49,90 — pacote 1 kg) |
| Bebidas | Água mineral sem gás (2,49 — garrafa 1,5 L); Suco de uva integral (12,90 — garrafa 1 L); Leite integral UHT (5,49 — caixa 1 L); Refrigerante sabor cola (8,99 — garrafa 2 L) |
| Limpeza | Detergente líquido neutro (2,99 — frasco 500 mL); Água sanitária (4,49 — frasco 1 L); Esponja dupla face (3,99 — pacote 3 unidades); Sabão em pó para roupas brancas e coloridas em embalagem econômica (32,90 — pacote 2 kg) |
| Hortifrúti | Banana prata (6,99 — kg); Tomate italiano (9,90 — kg); Batata inglesa (5,49 — kg); Alface crespa (3,49 — unidade) |

### 3.3. Carga no banco local de desenvolvimento

1. Cópia de segurança do banco feita fora do repositório; cópia idêntica ao original
   (SHA-256 `5d60bece…12024b`).
2. Ambiente confirmado (`development`, `DEBUG=True`) e caminho do banco confirmado
   (`db.sqlite3` na raiz do projeto).
3. Recusas confirmadas antes da carga: sem `DJANGO_ENV` (erro de configuração) e com
   `DJANGO_ENV=production` (comando recusado); o hash do banco não mudou.
4. Primeira execução: 4 categorias e 18 produtos criados.
5. Segunda execução: nada criado; hash inalterado.

Comparação tabela a tabela com a cópia de segurança: só mudaram `principal_categoria` (+4)
e `principal_produto` (+18); as outras 12 tabelas, incluindo a conta já existente, estão
idênticas. Novo SHA-256 do banco: `8e79c0cb…b7b79415b`.

### 3.4. Configuração demonstrativa de entrega (D-001/D-002)

Para a demonstração acadêmica foram aprovados valores **fictícios**, que não representam
condições comerciais reais:

| Parâmetro | Valor | Origem |
|---|---|---|
| Bairro atendido | Bairro Ficticio de Teste | Mesmo bairro fictício já usado nos testes de checkout |
| Taxa de entrega | R$ 5,00 | Valor aprovado para a demonstração (igual à taxa dos testes) |

Os valores ficam centralizados em `supermercado/settings.py`
(`CHECKOUT_DEMONSTRACAO_BAIRROS` e `CHECKOUT_DEMONSTRACAO_TAXA_ENTREGA`) e são aplicados
**somente** quando `DJANGO_ENV=development`. Com `DJANGO_ENV=production`, os bairros ficam vazios
e a taxa fica `None`, então o checkout permanece bloqueado (`CheckoutIndisponivel`) até que
valores reais sejam definidos. A validação, o cálculo dos valores e a recusa de valores
enviados pelo navegador continuam em `principal/checkout.py`, sem alterações.

## 4. Validação da instalação em ambiente limpo

Executada duas vezes, em cópias temporárias fora do repositório. O ambiente virtual e o banco
originais foram preservados nas duas.

| Etapa | 1ª validação (antes de F-01/F-02) | 2ª validação (código atual) |
|---|---|---|
| Arquivos copiados (versionados e novos não ignorados) | 71 | 75 |
| Banco, chave local, `.venv`, `.git` e caches na cópia | ausentes | ausentes |
| Novo ambiente virtual (Python 3.14.7) e `pip install -r requirements.txt` | Django 5.2.19, asgiref 3.12.1, sqlparse 0.6.0, tzdata 2026.5 | idem |
| `pip check` | sem problemas | sem problemas |
| `manage.py check` sem `DJANGO_ENV` | recusado (`ImproperlyConfigured`) | recusado (`ImproperlyConfigured`) |
| `manage.py check` com `DJANGO_ENV=development` | sem problemas | sem problemas |
| `migrate` (banco novo, só na cópia) | aplicado | aplicado |
| `makemigrations --check --dry-run` | nenhuma alteração | nenhuma alteração |
| `python -W default manage.py test` | 396 testes, OK (1 falha esperada), 0 warnings | **418 testes, OK, 0 warnings** |
| `preparar_dados_demonstracao` | 4 categorias e 18 produtos | 4 e 18; a 2ª execução não criou nada |
| `runserver` | 200 nas páginas principais; 18 produtos | 200 em 10 rotas; 18 produtos; "agua" encontra os dois produtos com "Água" |

**Resultado: aprovada nas duas validações.**

## 5. Testes-piloto automatizados

Arquivos `principal/test_piloto.py` (11 testes), `principal/test_dados_demonstracao.py`
(7 testes) e `principal/test_entrega_demonstrativa.py` (6 testes). Eles rodam no banco de testes,
com o catálogo criado pelo próprio comando. Os valores esperados são calculados no próprio teste,
a partir dos preços do banco.

| Cenário | Resultado esperado | Resultado observado | Situação |
|---|---|---|---|
| 1. Visitante | Consulta início, catálogo, categorias, busca, filtro e detalhes; áreas protegidas redirecionam ao login | Como esperado. Busca "arroz" → 1 produto; filtro Limpeza → 4; busca + filtro → 1; minha conta, pedidos, checkout, acompanhamento e equipe → login | **Aprovado** |
| 1. Busca com acentos | "agua", "ÁGUA", "oleo" e "FEIJAO" encontram os produtos | Na primeira execução **não encontrava** (F-01); após a correção (seção 9.1), encontra | **Aprovado após a correção** |
| 2. Cadastro e autenticação | Senha de 11 caracteres recusada; cadastro, login, conta e logout funcionando | Como esperado; conta criada sem privilégios | **Aprovado** |
| 3. Carrinho | Adicionar, alterar, remover e recalcular; quantidades inválidas recusadas; carrinho limpo no logout | Como esperado; `0`, `-1`, `1.5`, `abc` e vazio recusados sem alterar o carrinho | **Aprovado** |
| 4. Checkout sem bairros e taxa | Bloqueado | Bloqueado, sem formulário de revisão | **Aprovado** |
| 4. Checkout com a configuração demonstrativa (sem sobrescrever settings) | Bairro demonstrativo como opção; taxa R$ 5,00; total = subtotal + taxa calculado no servidor | Como esperado; `taxa_entrega=0.00`, `total=0.01` e `subtotal=0.01` enviados pelo navegador ignorados | **Aprovado** |
| 4. Bairro fora da lista | Recusado, sem pedido | Erro no campo bairro; 0 pedidos | **Aprovado** |
| 4. Compra completa (2 produtos) | Pedido e itens persistidos; estado Recebido; vínculo ao cliente; reenvio não duplica | Como esperado; carrinho esvaziado; reenvio devolve o mesmo pedido | **Aprovado** |
| 4. Endereço inválido | Nenhum pedido criado | Erros em número e bairro; 0 pedidos | **Aprovado** |
| 5. Acompanhamento | Cliente vê o próprio pedido; pedido alheio e inexistente → 404 | Como esperado; o endereço não aparece nas respostas 404 | **Aprovado** |
| 6. Equipe interna | Transições Recebido → Confirmado → Em preparo → Saiu para entrega → Entregue; transição inválida recusada | Como esperado; Entregue → Cancelado recusado; valores inalterados | **Aprovado** |
| 6. Bloqueios | Cliente e equipe só de consulta não alteram estado | 403 nos dois casos; estado inalterado | **Aprovado** |
| Produção | Não herda bairro nem taxa demonstrativos | Em outro processo, com `DJANGO_ENV=production`: bairros vazios, taxa `None`, checkout bloqueado | **Aprovado** |
| Comando de dados | Idempotente, não destrutivo, transacional, somente `development` | Como esperado, inclusive desfazendo tudo após uma falha simulada | **Aprovado** |

### Cenário 7 — Regressões de segurança

Coberto pelos testes já existentes, executados na suíte completa:

| Tema | Arquivos |
|---|---|
| CSRF | `test_auth.py`, `test_carrinho.py`, `test_checkout.py`, `test_pedidos.py`, `test_limite_login.py` |
| Separação de permissões | `test_pedidos.py`, `test_seguranca.py`, `test_admin.py` |
| Integridade financeira e idempotência | `test_checkout.py`, `test_models.py`, `test_entrega_demonstrativa.py` |
| Limitação de tentativas | `test_limite_login.py` |
| Proteção de pedidos | `test_pedidos.py`, `test_seguranca.py` |
| Logout | `test_auth.py` |
| Configuração, chave secreta e ambientes | `test_configuracao.py`, `test_entrega_demonstrativa.py` |

**Resultado: aprovado** (suíte completa sem falhas; ver seção 7).

## 6. Inspeção automatizada (não substitui a demonstração manual)

### 6.1. Telas do fluxo, a partir do banco de testes

Foram renderizadas 16 telas do fluxo, com os dados de demonstração, e capturadas no Chrome
headless com emulação real de viewport (360, 390, 768, 1024 e 1440 px):

- visitante: início, catálogo, busca, filtro e detalhe de produto com nome longo;
- cadastro com senha curta;
- carrinho, checkout, confirmação, meus pedidos e acompanhamento;
- equipe: lista, pedido confirmado e pedido entregue;
- cliente bloqueado na área da equipe.

Nas 80 medições: viewport igual à largura, nenhuma rolagem horizontal, nenhum valor monetário
quebrado e nenhum alvo menor que 44 px. Após a correção de F-02, o catálogo começa com
"Açúcar cristal", "Água mineral sem gás" e "Água sanitária", e "Óleo de soja" fica entre
"Macarrão espaguete" e "Refrigerante sabor cola".

### 6.2. Fluxo completo por HTTP real (cópia isolada da 2ª validação)

Um script percorreu, contra o `runserver` da cópia limpa e com a configuração demonstrativa real
(sem sobrescrever settings), o mesmo caminho do roteiro manual. As senhas foram geradas na hora
e não foram registradas.

| Etapa | Observado |
|---|---|
| Cadastro e login do cliente | concluídos |
| Carrinho: Arroz × 1 e Óleo × 2, depois Arroz alterado para 3 | subtotal R$ 90,68 |
| Checkout | bairro demonstrativo como opção; taxa R$ 5,00; total R$ 95,68 |
| Confirmação (com `taxa_entrega=0.00` e `total=0.01` enviados) | subtotal R$ 90,68, taxa R$ 5,00, total R$ 95,68; estado Recebido |
| Reenvio do mesmo formulário | devolveu o mesmo pedido |
| Meus pedidos | pedido listado |
| Cliente tentando alterar estado | HTTP 403 |
| Equipe (somente `view_pedido` e `change_pedido`) | Recebido → Confirmado → Em preparo → Saiu para entrega → Entregue |
| Transição inválida (Entregue → Cancelado) | recusada |
| Acompanhamento do cliente ao final | estado Entregue |

Foram feitas 8 capturas desse fluxo (busca, confirmação, acompanhamento e detalhe da equipe,
em 390 e 1280 px). As capturas são arquivos locais temporários, fora do repositório.

## 7. Resultado da suíte completa

| Comando (`DJANGO_ENV=development`) | Resultado |
|---|---|
| `python -W default manage.py test` | **418 testes, OK, 0 warnings**, sem falhas esperadas nem testes ignorados |
| `python manage.py check` | sem problemas |
| `python manage.py makemigrations --check --dry-run` | nenhuma alteração |
| `pip check` | sem problemas |

Evolução nesta atividade:

1. Antes havia 378 testes.
2. A primeira execução acrescentou 18 (396, com 1 falha esperada).
3. A correção de F-01/F-02 acrescentou 16 e converteu a falha esperada em teste normal (412).
4. A configuração demonstrativa acrescentou 6 (418).

Dois testes antigos que exigiam "desenvolvimento sem bairros e sem taxa" foram ajustados para
verificar o bloqueio sem bairros e sem taxa de forma explícita.

## 8. Roteiro para a demonstração manual no navegador

**Situação:** roteiro preparado; demonstração realizada pelo usuário, conforme registrado na
seção 8.4.

### 8.1. Preparação (PowerShell)

```powershell
cd "D:\Projeto Estágio P5"
.\.venv\Scripts\Activate.ps1
$env:DJANGO_ENV = "development"
python manage.py preparar_dados_demonstracao   # cria só o que faltar; pode ser repetido
python manage.py runserver
```

`$env:DJANGO_ENV` vale apenas para a janela atual do PowerShell; em um terminal novo,
defina-a de novo.

### 8.2. Conta da equipe (sem senha padrão)

Em outro PowerShell, ative o ambiente virtual e defina `DJANGO_ENV` como acima. Depois abra o
shell com `python manage.py shell` e cole o bloco abaixo.

A senha é digitada no terminal, sem aparecer na tela, e passa pelos mesmos validadores do
cadastro (mínimo de 12 caracteres). A conta recebe somente o necessário para gerenciar pedidos:
`is_staff` (exigido pela área interna) e as permissões `principal.view_pedido` e
`principal.change_pedido`. Não é superusuário e não tem permissões de produtos, categorias ou
usuários.

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

Se `validate_password` recusar a senha, a mensagem explica o motivo e nada é gravado. Nesse
caso, repita a partir da linha `senha = getpass(...)`. Saia do shell com `exit()`.

A conta do cliente é criada pela própria tela de cadastro, com uma senha de pelo menos 12
caracteres escolhida na hora. **Nenhuma senha deve ser anotada neste documento.**

### 8.3. Passos

| # | Ação | Resultado esperado |
|---|---|---|
| 1 | Abrir `http://127.0.0.1:8000/` | Página inicial com o botão "Ver catálogo de produtos" |
| 2 | Abrir o catálogo sem login | 18 produtos em 4 categorias, em ordem alfabética ("Açúcar", "Água…" no início) |
| 3 | Pesquisar "arroz"; depois "agua"; depois "OLEO"; filtrar por "Limpeza"; combinar "agua" + "Limpeza" | 1; 2 ("Água mineral sem gás", "Água sanitária"); 1 ("Óleo de soja"); 4; 1 ("Água sanitária") |
| 4 | Abrir um produto | Nome, categoria, unidade, preço e botão "Adicionar ao carrinho" |
| 5 | Cadastrar um cliente (senha com 12 ou mais caracteres) | Mensagem de sucesso e tela de login |
| 6 | Entrar com o cliente | "Minha conta" com o nome do usuário |
| 7 | Adicionar pelo menos dois produtos ao carrinho | Itens, valores e subtotal exibidos |
| 8 | Alterar a quantidade de um item | Subtotal recalculado |
| 9 | "Finalizar compra": informar um endereço fictício e escolher "Bairro Ficticio de Teste" | Bairro disponível na lista |
| 10 | Conferir a revisão | Taxa de entrega R$ 5,00 e total = subtotal + R$ 5,00 |
| 11 | "Confirmar pedido" | Tela "Pedido registrado", estado Recebido |
| 12 | Abrir "Meus pedidos" e o pedido | Itens, totais e estado |
| 13 | Sair e entrar com a conta da equipe | Link "Gerenciamento de pedidos" |
| 14 | Abrir o pedido e usar, em sequência, "Confirmar pedido", "Iniciar preparo", "Registrar saída para entrega" e "Concluir entrega" | Mensagem a cada etapa; ao final, "Entregue" e "Estado terminal" |

Registrar para cada passo: data, navegador, resultado observado e, se possível, uma captura de
tela.

### 8.4. Demonstração manual realizada pelo usuário

**Fonte.** O usuário, que é o estudante responsável pelo projeto, informou que navegou pelas
interfaces e executou manualmente os testes listados no roteiro acima. Ele não forneceu data,
horário, navegador, resultados por passo nem capturas de tela, e por isso esses dados não estão
registrados.

**Observação registrada pelo usuário.** O pedido nasce com o estado **Recebido**. Os estados
seguintes (**Confirmado**, **Em preparo**, **Saiu para entrega**, **Entregue** ou
**Cancelado**) são transições registradas pela equipe interna no **Gerenciamento de pedidos**.
Por se tratar de um projeto acadêmico, o usuário decidiu não exigir a simulação da operação
logística física. **Não houve entrega física real**: os estados só registram etapas do
atendimento.

**Evidência no banco local de desenvolvimento.** Foi feita uma leitura apenas de contagens,
sem consultar nomes, endereços ou senhas:

- uma conta de cliente nova, além da conta que já existia;
- um pedido no estado **Recebido**, com um item, no bairro "Bairro Ficticio de Teste" e com taxa
  de entrega de R$ 5,00;
- nenhuma conta da equipe interna.

A demonstração alterou o banco local de desenvolvimento, cujo SHA-256 passou de
`8e79c0cb…b7b79415b` para `62911a04…`.

**Situação de cada passo:**

| Passos do roteiro (8.3) | Situação registrada |
|---|---|
| 1 a 10 (navegação, pesquisa, cadastro, login, carrinho, endereço, bairro e conferência da taxa) | Execução informada pelo usuário; os resultados de cada passo não foram documentados |
| 11 (confirmar o pedido) | Executado: o banco local contém um pedido **Recebido**, com o bairro e a taxa demonstrativos |
| 12 (consultar o pedido) | Execução informada pelo usuário; resultado não documentado |
| 13 e 14 (conta da equipe e transições até Entregue) | Não executados manualmente: não há conta da equipe no banco local, de acordo com a decisão do usuário de não simular a operação. Esses passos estão cobertos pelos testes automatizados (seção 5) e pela inspeção por HTTP real (seção 6.2) |

O roteiro sugeria pelo menos dois produtos no carrinho. O pedido registrado contém um item. Como
itens removidos do carrinho não ficam gravados, o banco não permite confirmar quantos produtos
passaram pelo carrinho durante a navegação.

## 9. Falhas encontradas

| ID | Falha | Gravidade | Situação |
|---|---|---|---|
| F-01 | A busca não encontrava nomes quando a letra acentuada estava em caixa diferente, nem termos digitados sem acento: "água", "agua", "óleo", "FEIJÃO", "SANITÁRIA" e "CAFÉ" retornavam vazio | Média (usabilidade; não é falha de segurança) | **Corrigida** (seção 9.1) |
| F-02 | A ordenação alfabética colocava "Água…" e "Óleo…" depois de "Z" | Baixa (usabilidade) | **Corrigida** (seção 9.1) |
| F-03 | O checkout ficava bloqueado na configuração de desenvolvimento, sem bairros nem taxa (D-001/D-002) | Esperado pelas regras (não é defeito) | **Resolvida para a demonstração** com valores fictícios aprovados, somente em `development` (seção 3.4). A produção continua sem valores e com o checkout bloqueado |

Nenhuma falha de segurança, de cálculo financeiro ou de permissão foi encontrada.

### 9.1. Correção de F-01 e F-02

**Causa.** No SQLite, a busca `nome__icontains` vira `LIKE`, que só ignora maiúsculas e
minúsculas em letras ASCII e não ignora acentos; já `ORDER BY nome` compara códigos de
caractere, o que coloca "Á" e "Ó" depois de "Z".

**Solução.** `principal/busca.py` define `normalizar_texto`, que decompõe o texto (NFKD), remove
as marcas diacríticas e aplica `casefold` ("Água SANITÁRIA" → "agua sanitaria"). Essa função
é registrada em cada conexão SQLite como a função SQL determinística `principal_normalizar`
(`principal/apps.py`).

O catálogo passou a:

- filtrar pelo nome normalizado contendo o termo normalizado (busca parcial preservada);
- ordenar pelo nome normalizado, com desempate por nome e identificador, o que mantém a ordem
  estável;
- usar a mesma ordem nas categorias do filtro.

A comparação é feita pelo próprio banco, sem carregar o catálogo em memória. Os nomes
armazenados e exibidos não mudam. Não há campos novos, migrations nem dependências.

**Limite da solução.** A função existe somente no SQLite, que é o banco do projeto. Uma busca
por trecho percorre a tabela inteira, como já acontecia com o `LIKE`. Para um catálogo grande,
a evolução seria guardar o nome normalizado em uma coluna com índice, o que exige migration.

| | Antes da correção | Depois da correção |
|---|---|---|
| "agua", "água", "ÁGUA", "sanitaria" | só "Água" e "ÁGUA" encontravam "Água sanitária" | todos encontram |
| "oleo", "óleo", "FEIJAO", "FEIJÃO", "cafe", "CAFÉ" | vazio | encontram o produto |
| Ordem do catálogo | "Água…" e "Óleo…" depois de "Z" | "Água" entre os nomes com A, "Óleo" entre os nomes com O |
| Teste do piloto | `expectedFailure` | teste normal aprovado |

**Testes que comprovam a correção:**

- `principal/test_busca_acentos.py` (16 testes): normalização; busca sem acento, com acento,
  em maiúsculas e em minúsculas; busca parcial; vários termos; busca combinada com categoria;
  parâmetros GET preenchidos e nomes exibidos com acento; ausência de resultado (inclusive "%"
  e "_" tratados literalmente); produtos inativos excluídos; ordenação por letra-base; ordem dos
  nomes sem acento preservada; desempate estável; ordem das categorias; função SQL registrada.
- `principal/test_piloto.py::Cenario1VisitanteTests::test_busca_ignora_caixa_e_acentos` e
  `principal/test_entrega_demonstrativa.py`, sobre os dados de demonstração.
- Mutações em memória (sem alterar arquivos) confirmaram que os testes falham se a correção for
  removida. Voltar à comparação antiga do SQLite derruba 22 testes.

## 10. Limitações

- A demonstração manual foi relatada pelo usuário sem data, navegador, resultados por passo ou
  capturas; ela cobriu o fluxo do cliente até o pedido **Recebido**. As etapas da equipe interna
  não foram executadas manualmente.
- Os estados posteriores a **Recebido** representam registros administrativos da equipe; não
  houve simulação nem execução de entrega física.
- Bairro e taxa são valores fictícios aprovados apenas para a demonstração acadêmica. A produção
  continua sem valores comerciais reais e, portanto, com o checkout bloqueado.
- As inspeções automatizadas (seção 6) usaram scripts e um navegador headless, não uma pessoa
  interagindo com a interface.
- A instalação limpa foi validada no mesmo computador, com o mesmo Python 3.14.7 e acesso ao
  PyPI; outros sistemas operacionais ou versões do Python não foram testados.
- A validação não cobre a implantação em produção (HTTPS, domínio, cache compartilhado e proxy).
