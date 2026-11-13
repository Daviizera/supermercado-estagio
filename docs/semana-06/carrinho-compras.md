# Semana 6 — Carrinho de compras

## Objetivo e requisitos

Permitir que visitantes e clientes autenticados montem um carrinho vinculado à sessão do Django: adicionar produtos ativos, alterar quantidades, remover itens e consultar os valores das linhas e o subtotal calculados no servidor. A implementação permanece no monólito Django, na aplicação `principal`, com Django Templates, SQLite e sem JavaScript.

As referências são os [requisitos](../semana-02/requisitos.md), as [regras de negócio](../semana-02/regras-negocio.md), o [fluxo de compra](../semana-02/fluxo-compra.md), a Tela 2 dos [protótipos](../semana-02/prototipos.md), a [modelagem da Semana 3](../semana-03/modelagem-dados.md), a [autenticação da Semana 4](../semana-04/autenticacao-clientes.md) e o [catálogo da Semana 5](../semana-05/catalogo-produtos.md).

| Referência | Alcance nesta entrega |
| --- | --- |
| RF-009 | Adição de produto ativo ao carrinho da sessão; repetir o produto soma a quantidade na mesma linha. |
| RF-010 | Alteração da quantidade com inteiro positivo; entradas inválidas são rejeitadas sem perder a quantidade anterior. |
| RF-011 | Remoção explícita de um item, com recálculo e mensagem de carrinho vazio após o último item. |
| RF-012 | Quantidade, preço unitário, valor da linha e subtotal calculados no servidor com `Decimal`. |
| RF-021 e RN-003 | Produto inativo não é adicionado; se já estiver no carrinho, permanece identificado como indisponível até a remoção. O bloqueio da compra pertence à Semana 7. |
| RN-005 | Carrinho somente na sessão, inclusive para visitante, preservado no login. |
| RN-006 e RN-007 | Quantidade inteira positiva, remoção como ação própria e cálculos exclusivamente no servidor. |
| RNF-003 e RNF-005 | Alterações somente por POST com CSRF; formulários com rótulos e mensagens de erro. |

RF-013 (revalidação antes de concluir), RF-016 (taxa e total), RN-008 e a criação de pedidos pertencem à Semana 7 e não foram implementados.

## Arquitetura

| Arquivo | Responsabilidade |
| --- | --- |
| `principal/carrinho.py` | Serviço `Carrinho`: valida as próprias entradas, lê e grava a estrutura da sessão, monta as linhas com os dados atuais do banco, tolera entradas malformadas e calcula os valores. Define as exceções `ErroCarrinho`, `QuantidadeInvalida`, `QuantidadeAcimaDoLimite`, `ProdutoIndisponivel`, `ItemAusente` e `ItemInconsistente`. |
| `principal/forms.py` | `QuantidadeCarrinhoForm` e `QuantidadeInteiraField`, com validação rigorosa da quantidade. |
| `principal/views.py` | Views `carrinho`, `adicionar_ao_carrinho`, `atualizar_item_carrinho` e `remover_item_carrinho`; o detalhe do produto passou a fornecer o formulário de adição. |
| `principal/urls.py` | Rotas do carrinho. |
| `templates/principal/carrinho.html` | Tabela de itens, mensagens, subtotal e ações. |
| `templates/principal/catalogo.html` e `detalhe_produto.html` | Formulário POST de adição com quantidade inicial 1. |
| `templates/base.html` | Link **Carrinho** na navegação. |
| `static/css/estilos.css` | Regras mínimas para os formulários de quantidade, a tabela e o aviso de indisponibilidade. |
| `principal/test_carrinho.py` | Testes automatizados da semana. |

Não foram criados modelos, migrations, dependências ou permissões. `ItemPedido` não é usado para o carrinho: ele continua reservado ao histórico de pedidos.

| Rota | Nome Django | Métodos | Resultado |
| --- | --- | --- | --- |
| `/carrinho/` | `principal:carrinho` | GET, HEAD | Exibe itens, valores e subtotal; nunca altera a sessão. |
| `/carrinho/adicionar/<id>/` | `principal:adicionar_ao_carrinho` | POST | Adiciona produto ativo e redireciona ao carrinho. |
| `/carrinho/atualizar/<id>/` | `principal:atualizar_item_carrinho` | POST | Define a nova quantidade de um item disponível. |
| `/carrinho/remover/<id>/` | `principal:remover_item_carrinho` | POST | Remove somente o item indicado. |

## Armazenamento na sessão

O carrinho usa o `SessionMiddleware` e o backend de sessões em banco já configurados. A chave `carrinho` da sessão guarda um dicionário com o identificador do produto, como texto, e a quantidade, como inteiro:

```json
{"carrinho": {"12": 3, "7": 1}}
```

Não são gravados preços, nomes, unidades, valores de linha ou subtotal. Nome, unidade, preço e disponibilidade são lidos do banco a cada visualização, em uma única consulta `in_bulk` para todos os itens, sem consulta por linha. A ordem das linhas é a ordem de inclusão.

Cada sessão tem seu próprio carrinho; não há carrinho por conta nem sincronização entre dispositivos. A visualização apenas lê a sessão: um visitante que abre o carrinho vazio não recebe cookie de sessão, e entradas de produtos indisponíveis ou excluídos não são removidas durante GET. Somente adicionar, atualizar e remover gravam uma nova versão do dicionário.

O login nativo renova a chave da sessão anônima e preserva seus dados, portanto o carrinho continua disponível após a autenticação. O logout limpa os dados da sessão, conforme documentado na Semana 4, e o carrinho é esvaziado junto com ela.

### Leitura tolerante de dados malformados

Somente o servidor grava a sessão, e o serviço só grava identificadores e quantidades válidos. Ainda assim, a leitura não depende dessa garantia: o resumo classifica cada entrada sem provocar erro interno.

| Entrada armazenada | Apresentação | Subtotal |
| --- | --- | --- |
| Identificador válido e quantidade inteira positiva dentro do limite | Linha normal. | Entra, se o produto existir. |
| Identificador válido e quantidade em texto, `float`, `None`, zero, negativa, booleana ou acima do limite | Linha do produto marcada como **Quantidade inválida**, sem quantidade e sem valor; permite atualizar (se o produto estiver ativo) ou remover. | Não entra. |
| Identificador que não segue o formato gravado pelo serviço (texto não numérico, zeros à esquerda, negativo, fora da faixa da chave primária) | Não vira linha; é contado como registro não identificado. | Não entra. |
| Valor da chave `carrinho` que não é dicionário | Carrinho apresentado como vazio; conta como um registro não identificado. | Não entra. |

Havendo qualquer inconsistência, o carrinho exibe um aviso genérico: “Alguns dados do carrinho estão inconsistentes e não entram no subtotal.”, acompanhado da quantidade de registros não identificados, quando houver. Nenhum detalhe técnico é apresentado. O GET e o HEAD **não corrigem, não apagam e não reescrevem** a sessão; os testes comparam a estrutura armazenada antes e depois da visualização.

Operações válidas por POST preservam as entradas malformadas dos demais produtos. Uma quantidade inconsistente pode ser substituída por uma válida na atualização ou eliminada pela remoção; a adição não soma sobre ela e informa “A quantidade registrada para este item é inválida. Atualize a quantidade ou remova o item.”. Quando a estrutura inteira não é um dicionário, uma adição válida a substitui por um novo dicionário.

### Limitação de concorrência

A sessão é lida no início da requisição e gravada inteira no final. Duas requisições simultâneas com a mesma sessão — por exemplo, duplo clique em “Adicionar” ou duas abas enviando alterações ao mesmo tempo — podem produzir uma condição de corrida do tipo **last-write-wins**: a gravação da segunda requisição sobrescreve a da primeira, e uma das alterações se perde. O carrinho permanece válido e o usuário vê o resultado final ao abrir a página, mas a quantidade pode não refletir todas as ações enviadas. O backend de sessões do Django não oferece bloqueio; não foram implementados locks nem mecanismos externos nesta semana.

## Adição, atualização e remoção

| Ação | Comportamento |
| --- | --- |
| Adicionar produto ativo | Soma a quantidade à linha existente ou cria a linha; redireciona ao carrinho com “*Produto* adicionado ao carrinho.”. |
| Adicionar produto inativo ou inexistente | Não altera a sessão; redireciona ao catálogo com “Este produto não está disponível.”. |
| Adicionar com quantidade inválida | Não altera a sessão; reapresenta o detalhe do produto com o erro no campo. |
| Atualizar com inteiro positivo | Substitui a quantidade do item e redireciona com “Quantidade atualizada.”. |
| Atualizar com valor inválido | Mantém a quantidade anterior; reapresenta o carrinho com o erro e “Quantidade mantida: N” somente na linha enviada. |
| Atualizar item indisponível ou excluído | Não altera a quantidade; informa “Este produto não está disponível. Remova o item do carrinho.”. |
| Remover item | Remove somente o item indicado, sem consultar o banco, e informa “Item removido do carrinho.”. |
| Atualizar ou remover item ausente | Não altera a sessão; informa “Este item não está no carrinho.”. |
| Remover o último item | O carrinho apresenta “Seu carrinho está vazio.”. |

O formulário de quantidade aparece em cada produto do catálogo e no detalhe do produto, com valor inicial 1. Somente o identificador da rota e a quantidade são utilizados; outros campos enviados, como preço, valor ou subtotal, são ignorados.

### Validação da quantidade

`QuantidadeInteiraField` aceita somente texto composto por dígitos ASCII (`[0-9]+`), após remover espaços externos. O `IntegerField` nativo do Django converte representações como `2.0`, `2.00`, `+2`, `1_000` e dígitos não ASCII; essas formas são rejeitadas antes da conversão. Também são rejeitados zero, negativos, frações com ponto ou vírgula, notação científica, texto e campo vazio ou ausente. A mensagem é “Informe uma quantidade inteira maior que zero.”. Zero não remove itens.

Não foi definido limite comercial. O limite superior é o técnico de `ItemPedido.quantidade`, obtido dos validadores que o Django associa ao campo no banco configurado: no SQLite, `PositiveIntegerField` recebe `MaxValueValidator(9223372036854775807)`. O valor é lido do modelo, não fixado no código. Uma soma de inclusões que ultrapasse esse limite é rejeitada sem alterar a quantidade existente.

Desde o Python 3.11, converter para `int` um texto com mais de 4300 dígitos gera `ValueError`. Após a validação lexical, o campo remove zeros à esquerda e, se o texto tiver mais dígitos que o limite técnico, recusa-o com “Informe uma quantidade de no máximo …” antes de qualquer conversão. A conversão restante é a do `IntegerField` do Django, que transforma `ValueError` e `TypeError` em erro de validação. Assim, entradas de qualquer tamanho resultam em erro de formulário, nunca em HTTP 500, e a quantidade anterior permanece.

### Validação no serviço

O serviço não depende das views nem dos formulários. Antes de qualquer gravação, `adicionar` e `definir_quantidade`:

- exigem quantidade do tipo `int`, positiva e dentro do limite técnico; `bool` é recusado, embora seja subclasse de `int`, assim como `float`, `Decimal`, texto e `None` (`QuantidadeInvalida` ou `QuantidadeAcimaDoLimite`);
- exigem uma instância persistida de `Produto` e confirmam no banco que ela existe e continua ativa, mesmo que o objeto recebido esteja desatualizado (`ProdutoIndisponivel`);
- na adição, recusam somar sobre uma quantidade armazenada inconsistente (`ItemInconsistente`) e conferem o limite técnico sobre a soma;
- na atualização, exigem que o item já esteja no carrinho (`ItemAusente`).

`remover` e `contem` aceitam somente identificadores inteiros positivos (exceto `bool`) ou texto no formato gravado, dentro da faixa da chave primária de `Produto`; o comprimento é conferido antes de qualquer conversão. Uma operação recusada lança uma subclasse de `ErroCarrinho` e não modifica a sessão. As views convertem essas exceções em erros de formulário ou mensagens compreensíveis.

## Cálculos monetários

```text
Valor da linha = quantidade válida × preço unitário atual do produto
Subtotal = soma dos valores das linhas que possuem valor
```

Pela decisão técnica provisória **T-601**, ainda pendente de confirmação do supervisor:

| Situação da linha | Valor da linha | Entra no subtotal |
| --- | --- | --- |
| Produto ativo com preço cadastrado | Quantidade × preço atual | Sim |
| Produto inativo que continua cadastrado, com preço | Quantidade × preço atual, exibido com a marca **Indisponível** | Sim |
| Produto excluído do banco, sem preço disponível | Não há valor; a linha permanece identificada como **Indisponível** | Não |
| Quantidade armazenada inválida | Não há valor; a linha é marcada como **Quantidade inválida** | Não |

Assim, o subtotal é sempre igual à soma dos valores exibidos. Essa é uma interpretação técnica, não uma regra comercial aprovada; a compra com itens indisponíveis será bloqueada pela revalidação da Semana 7 (RF-013).

O preço unitário é o `Produto.preco` lido do banco, do tipo `Decimal` com duas casas. As quantidades são inteiras, portanto os valores mantêm duas casas decimais. Os cálculos são refeitos a cada visualização, o que reflete imediatamente adição, atualização, remoção e alterações de preço feitas no Django Admin.

O contexto padrão do `Decimal` usa 28 dígitos significativos. Com a quantidade máxima técnica e o maior preço permitido pelo modelo (`max_digits=10`), o valor de uma linha pode ter 29 dígitos e seria arredondado silenciosamente. Por isso o serviço calcula em um contexto local de 100 dígitos com a armadilha `Inexact` ativada: qualquer arredondamento geraria erro em vez de um valor incorreto. Um teste confirma o resultado exato nesse cenário, comparando os dígitos com um cálculo em centavos inteiros.

O carrinho informa que a taxa de entrega será apresentada na etapa de endereço; não calcula taxa nem total.

## Disponibilidade

| Situação | Comportamento |
| --- | --- |
| Produto ativo | Linha completa, com formulário de quantidade e ação de remover. |
| Produto desativado após a inclusão | Permanece na sessão e na tabela, identificado como **Indisponível**, com nome, unidade e preço atuais; não oferece atualização de quantidade e permite remoção. |
| Produto excluído do banco após a inclusão | Permanece na sessão até um POST de remoção. É exibido como “Produto não encontrado (código N)”, **Indisponível**, sem nome, unidade, preço ou valor inventados. |
| Produto reativado | Volta a ser tratado como disponível na próxima visualização. |

Se houver item indisponível, o carrinho exibe: **“Há produto indisponível no carrinho. Remova o item para continuar.”**. Nova adição de produto inativo é recusada. O bloqueio da finalização da compra com esses itens não foi implementado; pertence à Semana 7.

## Segurança e validação

- Adicionar, atualizar e remover usam `require_POST`; GET e HEAD nessas rotas retornam HTTP 405 sem alterar o carrinho.
- Os formulários incluem `{% csrf_token %}`; POST sem token válido retorna HTTP 403 e não altera a sessão.
- A visualização usa `require_safe` e `never_cache`, evitando reapresentação de um carrinho antigo pelo cache do navegador.
- Toda validação ocorre no servidor; os atributos `min` e `step` do campo HTML são apenas auxiliares.
- O navegador nunca envia nem determina preços: os valores vêm do banco.
- Identificadores inexistentes, inclusive acima da faixa de inteiros do SQLite, não causam erro interno.
- Quantidades com qualquer número de dígitos e dados de sessão malformados resultam em erro de validação ou aviso, nunca em HTTP 500.
- Nomes de produtos nas mensagens passam pelo escape automático dos templates.

## Testes e validação

A suíte `principal/test_carrinho.py` contém **59 testes**, que utilizam somente o banco temporário do Django. Os 41 testes da implementação inicial foram mantidos; 18 testes de regressão foram acrescentados após a auditoria técnica:

| Grupo | Cobertura |
| --- | --- |
| Formulário | Inteiros aceitos; `0`, `00`, `-1`, `1.5`, `1,5`, `2.0`, `2.00`, texto, vazio, espaços, `+2`, `1_000`, `1e3`, dígito não ASCII e `0x10` rejeitados; campo ausente; limite técnico derivado de `ItemPedido`. |
| Adição | Visitante e cliente autenticado; soma em uma linha; inativo, inexistente e identificador fora da faixa recusados; GET/HEAD com HTTP 405; CSRF obrigatório; formulários com quantidade inicial 1. |
| Quantidades | Atualização válida; inválidas preservam a quantidade anterior na adição e na atualização; zero não remove; soma acima do limite técnico recusada. |
| Remoção | Remove somente o item escolhido; último item leva ao carrinho vazio; item ausente; produto excluído do banco permanece até POST explícito. |
| Cálculos | Linhas e subtotal em `Decimal`; recálculo após adição, atualização e remoção; preço alterado no banco e pelo Admin; preços forjados ignorados; sessão somente com identificadores e quantidades; cálculo exato com 29 dígitos. |
| Disponibilidade e sessão | Inativo permanece, é identificado, não é readicionado nem atualizado e pode ser removido; reativação; duas sessões isoladas; login preserva; logout limpa. |
| Escopo e desempenho | Link na navegação; nenhum pedido criado e nenhuma ação de finalizar; labels únicos por linha; quantidade de consultas constante com mais itens; leitura sem gravação. |
| Muitos dígitos (M-1) | Adição e atualização com 4300, 4301 e 10000 dígitos retornam HTTP 200 com erro de validação e preservam a quantidade; zeros à esquerda não contam para o comprimento; campo sem limite também não propaga `ValueError`. |
| Serviço (M-2) | Chamadas diretas com zero, negativo, `float`, `Decimal`, texto, `None`, `True`, `False` e acima do limite; soma acima do limite; produto inativo, excluído, não persistido, desatualizado e objeto que não é `Produto`; item ausente; identificadores inválidos em `remover` e `contem`; quantidade inconsistente não somada, mas substituível e removível. A sessão é comparada e permanece sem modificação. |
| Sessão malformada (B-1) | Chaves e quantidades malformadas e estruturas que não são dicionário: HTTP 200, aviso, subtotal somente com entradas válidas, itens válidos exibidos, sessão inalterada após GET e HEAD, operações normais sobre os itens válidos e correção de item inconsistente por POST. |

| Verificação executada | Resultado |
| --- | --- |
| `manage.py check` | Nenhum problema identificado. |
| `manage.py test principal.test_carrinho` | 59 testes aprovados. |
| `manage.py test` | 145 testes aprovados, zero falhas: 86 anteriores e 59 do carrinho. |
| `manage.py makemigrations --check --dry-run` | Nenhuma alteração detectada. |
| `python -m pip check` | Nenhuma incompatibilidade de dependências. |
| `git diff --check` | Nenhum problema de espaços em branco. |

O SHA-256 do `db.sqlite3` permaneceu idêntico antes e depois dos comandos. Nenhum dado fictício foi criado permanentemente.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test principal.test_carrinho
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
```

## Decisões técnicas provisórias

As escolhas abaixo são interpretações técnicas adotadas para implementar a semana. **Não são regras de negócio aprovadas** e dependem de confirmação do supervisor.

| ID | Decisão adotada | Motivo |
| --- | --- | --- |
| T-601 | O subtotal soma as linhas de todos os produtos existentes no banco, inclusive inativos, pelo preço atual; produtos excluídos não têm valor e ficam fora da soma. | Mantém o subtotal igual à soma dos valores exibidos (RF-012) e não inventa preço de produto excluído. |
| T-602 | Item indisponível ou excluído não tem a quantidade alterada; somente a remoção é oferecida. | RN-003 restringe adição e compra a produtos ativos; a mensagem do protótipo orienta a remover o item. |
| T-603 | Limite superior da quantidade igual ao limite técnico de `ItemPedido.quantidade` (9.223.372.036.854.775.807 no SQLite), sem limite comercial. | Nenhum limite comercial está especificado. |
| T-604 | Após adição válida, redireciona ao carrinho. Produto indisponível volta ao catálogo; quantidade inválida reapresenta o detalhe do produto com o erro. | Destinos internos fixos, sem redirecionamento baseado em parâmetro do navegador. |
| T-605 | Espaços antes e depois da quantidade são removidos antes da validação. | Comportamento padrão dos campos de texto do Django; o valor continua restrito a dígitos. |
| T-606 | Produto excluído é identificado como “Produto não encontrado (código N)”. | Única informação disponível sem inventar dados. |
| T-607 | Não há botão de finalizar compra nem contador de itens na navegação. | A finalização pertence à Semana 7; o contador não está especificado. |
| T-608 | Entradas malformadas da sessão são apresentadas com aviso genérico e ficam fora do subtotal; quantidade inconsistente pode ser substituída ou removida por POST; registros não identificáveis apenas são contados. | Evita HTTP 500 sem corrigir a sessão automaticamente em GET e sem esconder o problema. |
| T-609 | Zeros à esquerda são aceitos na quantidade (`007` equivale a 7) e não contam para o limite de comprimento. | O texto continua restrito a dígitos ASCII e representa um inteiro sem ambiguidade. |

## Pontos pendentes de confirmação

1. **T-601:** se itens inativos devem compor o subtotal exibido no carrinho. A compra continuará bloqueada pela revalidação da Semana 7 (RF-013).
2. **T-602:** se a quantidade de item indisponível pode ser reduzida antes da remoção.
3. **Capacidade dos campos do pedido (risco para a Semana 7):** `Pedido.subtotal` e `Pedido.total` têm `max_digits=12` (máximo 9.999.999.999,99), enquanto o subtotal do carrinho, sem limite comercial, pode ser muito maior. A Semana 7 precisará decidir como tratar um subtotal que não cabe no pedido, sem truncamento ou arredondamento silencioso, e realizar os cálculos com contexto decimal suficiente.
4. **Logout:** confirmar que esvaziar o carrinho ao sair é o comportamento desejado. Ele decorre da limpeza da sessão documentada na Semana 4. Da mesma forma, o login nativo descarta a sessão quando outra conta já estava autenticada nela.
5. **D-005:** unidades e embalagens comerciais continuam pendentes; a quantidade representa uma unidade do produto conforme cadastrado.
6. **D-007:** aprovação do supervisor permanece externa à validação técnica.
7. **Concorrência:** aceitar a limitação last-write-wins descrita em “Limitação de concorrência” ou tratá-la em etapa futura.
8. **T-608:** registros com identificador não reconhecível não podem ser removidos individualmente pela interface, pois não correspondem a um produto; o aviso permanece até o logout ou até uma adição válida substituir uma estrutura que não é dicionário. Confirmar se deve existir uma ação explícita de limpeza.

## Critérios de aceite

| Critério | Implementação |
| --- | --- |
| Adição de produtos | POST com CSRF para produto ativo, quantidade validada no servidor e soma na mesma linha. |
| Gerenciamento de quantidades | Inteiro positivo obrigatório; inválido preserva a quantidade anterior; zero não remove. |
| Atualização de itens | Formulário por linha, com erro exibido no item correspondente. |
| Remoção de itens | Ação explícita por POST, inclusive para produtos inativos e excluídos. |
| Valores individuais | Quantidade × preço atual do banco, em `Decimal`. |
| Subtotal | Soma dos valores das linhas, recalculada a cada visualização. |
| Indisponibilidade | Item mantido, identificado e com mensagem; nova adição recusada. |
| Sessão | Carrinho por sessão, preservado no login e limpo no logout. |
| Testes | Suíte específica e regressão completa aprovadas. |

## Fora do escopo

Não foram implementados checkout, endereço, bairro, taxa de entrega, total, pagamento, criação ou consulta de pedidos, painel de pedidos, acompanhamento, estoque, carrinho persistente por conta, contador na navegação, JavaScript ou redesign das interfaces. Essas atividades pertencem às semanas seguintes.
