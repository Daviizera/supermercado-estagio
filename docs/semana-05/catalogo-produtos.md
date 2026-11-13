# Semana 5 — Catálogo de produtos

## Objetivo e requisitos

Disponibilizar consulta pública aos produtos ativos do supermercado, com pesquisa por nome, filtro por categoria e detalhes. Visitantes e clientes autenticados utilizam as mesmas consultas. A implementação permanece no monólito Django, na aplicação `principal`, com templates e SQLite.

As referências funcionais são os [requisitos](../semana-02/requisitos.md), as [regras de negócio](../semana-02/regras-negocio.md) e a Tela 1 dos [protótipos](../semana-02/prototipos.md). Os campos e relacionamentos seguem a [modelagem da Semana 3](../semana-03/modelagem-dados.md), e a [autenticação da Semana 4](../semana-04/autenticacao-clientes.md) permanece preservada.

| Referência | Alcance nesta entrega |
| --- | --- |
| RF-001 | Lista de produtos ativos com nome, preço e unidade. |
| RF-002 | Filtro por categoria existente, incluindo resultado vazio. |
| RF-003 | Busca parcial pelo nome, combinada com categoria, conforme os limites do SQLite descritos abaixo. |
| RF-004 | Detalhes de produto ativo; inativo ou inexistente retorna HTTP 404. |
| RF-021 e RN-003 | O campo `ativo` controla a visibilidade pública. A revalidação para carrinho e compra continua para as Semanas 6 e 7. |
| RN-001, RN-002 e RN-004 | Exibição dos dados cadastrados e do preço decimal, sem alteração da integridade ou do histórico comercial. |
| RNF-003, RNF-005 e RNF-007 | Consulta sem gravação, formulários com rótulos e erros, arquitetura e ambiente existentes preservados. |

## Rotas, views e formulário

| Rota | Nome Django | View | Resultado |
| --- | --- | --- | --- |
| `/catalogo/` | `principal:catalogo` | `catalogo` | HTTP 200 com produtos e formulário de filtros. |
| `/produtos/<int:pk>/` | `principal:detalhe_produto` | `detalhe_produto` | HTTP 200 para produto ativo; HTTP 404 para inativo ou inexistente. |

As views estão em `principal/views.py` e utilizam `require_safe`: aceitam GET e HEAD, sem operações de escrita. Não há exigência de login para consultar o catálogo ou um produto disponível. As rotas de autenticação, a área privada e o Admin não foram substituídos.

`FiltroCatalogoForm`, em `principal/forms.py`, valida os parâmetros GET:

- `q`: texto opcional, limitado a 150 caracteres, com remoção de espaços no início e no fim.
- `categoria`: seleção opcional de uma `Categoria` existente, por `ModelChoiceField`.

O seletor apresenta todas as categorias existentes, ordenadas por nome e identificador, inclusive categorias sem produtos ativos. A opção **Todas as categorias** corresponde à ausência desse filtro. O formulário não grava dados nem altera os formulários de autenticação.

## Listagem e consultas ORM

A consulta pública parte de `Produto.objects.filter(ativo=True)`. A categoria é carregada por `select_related('categoria')`, evitando uma consulta adicional por produto ao renderizar seu nome. A lista usa `order_by('nome', 'pk')`, com desempate estável pelo identificador.

Cada resultado apresenta nome, categoria, preço, unidade e link para detalhes. O preço é formatado com duas casas decimais, localização `pt-br` e indicação `R$`. Não há cálculo comercial novo nem conversão dos valores monetários para `float` no código da aplicação.

Os filtros são adicionados ao mesmo queryset pelo ORM. A seleção de categoria restringe a relação `Produto.categoria`; a pesquisa utiliza `nome__icontains`. Quando ambos estão presentes, as condições são combinadas por **E**: o produto precisa estar ativo, pertencer à categoria e conter o texto no nome. Não há SQL manual ou filtragem somente no navegador.

Nenhuma consulta modifica `ativo` ou qualquer outro campo do produto. A ausência de resultados é tratada como situação normal, sem erro interno.

## Pesquisa, combinação e tratamento de entradas

| Entrada ou ação | Comportamento |
| --- | --- |
| Sem filtros | Exibe todos os produtos ativos. |
| Categoria existente | Exibe somente os ativos dessa categoria. |
| Pesquisa parcial | Busca o trecho informado no nome dos produtos ativos. |
| Pesquisa e categoria | Aplica os dois critérios no servidor. |
| Pesquisa vazia ou composta de espaços | Remove somente o termo, mantendo a categoria selecionada. |
| Categoria vazia | Remove somente a categoria, mantendo o termo pesquisado. |
| Link **Limpar filtros** | Abre `/catalogo/` sem parâmetros, removendo ambos os filtros. |
| Categoria inexistente, não numérica ou fora da faixa de identificadores | HTTP 200 com erro no formulário e nenhum produto listado. |
| Pesquisa acima de 150 caracteres | HTTP 200 com erro no formulário e nenhum produto listado. |

O formulário GET conserva o texto e a categoria enviados para permitir novas consultas sem perder a seleção. As URLs utilizam somente os parâmetros de filtro; o link de limpeza não inclui parâmetros vazios. Entradas inválidas não são ignoradas silenciosamente para apresentar uma lista irrestrita.

As mensagens distinguem três situações:

- Sem produtos ativos e sem filtros: **“Nenhum produto disponível no momento.”**
- Filtros válidos sem correspondência: **“Nenhum produto encontrado para os filtros informados.”**
- Formulário inválido: **“Corrija os filtros para consultar os produtos.”**, acompanhado dos erros dos campos.

### Limites de texto no SQLite

A pesquisa segue `icontains` do Django e o comportamento nativo do SQLite. Diferenças entre letras maiúsculas e minúsculas em caracteres ASCII são ignoradas: por exemplo, `arro` e `ARRO` podem localizar `Arroz`. Caracteres fora do conjunto ASCII podem diferenciar maiúsculas e minúsculas; não se promete equivalência universal para Unicode. Não há remoção de acentos, correção ortográfica ou busca aproximada. Essas limitações são descritas na [documentação de comparações do SQLite no Django](https://docs.djangoproject.com/en/5.2/ref/databases/#substring-matching-and-case-sensitivity) e na [referência de `icontains`](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#icontains).

## Detalhes e indisponibilidade

A view `detalhe_produto` consulta o identificador somente entre produtos ativos e carrega a categoria na mesma consulta. O template exibe nome, categoria, preço e unidade já cadastrados. Não foi criado campo de descrição, imagem ou conteúdo comercial fictício.

Produto inexistente e produto inativo recebem HTTP 404, sem apresentação dos seus dados. Isso vale também para quem digita diretamente a URL e para usuários autenticados. Desativar um produto no Admin o retira da listagem, da pesquisa, dos filtros e da consulta pública de detalhes nas próximas requisições.

## Integração com o Admin e navegação

O catálogo utiliza os mesmos registros de `Categoria` e `Produto` administrados desde a Semana 3. Cadastro e edição permanecem em `/admin/`, com as permissões nativas existentes. Mudanças no nome da categoria e nos dados ou na atividade do produto são refletidas nas consultas públicas seguintes.

O link **Catálogo** foi adicionado a `templates/base.html`, mantendo a navegação de visitantes e clientes, o formulário POST de logout e a área autenticada. A página inicial histórica permanece disponível em `/`.

Os templates novos são:

- `templates/principal/catalogo.html`: formulário GET, produtos disponíveis, links de detalhes e mensagens de resultado.
- `templates/principal/detalhe_produto.html`: informações do produto ativo e retorno ao catálogo.

Ambos estendem `base.html`. Labels, controles HTML nativos, foco de teclado e CSS mínimo mantêm a apresentação funcional. Não há JavaScript, imagens comerciais fictícias, controles de quantidade, botões de compra ou carrinho visual. As ações futuras presentes nos wireframes da Semana 2 não foram antecipadas.

## Testes e validação

Antes da implementação, os **61 testes anteriores passaram em 8,661 s**. A suíte específica do catálogo está em `principal/test_catalogo.py` e utiliza somente o banco temporário do Django, sem usuários ou produtos permanentes no SQLite local.

As verificações abrangem acesso público e autenticado, dados exibidos, exclusão de inativos, catálogo vazio, ordenação, categorias válidas e inválidas, pesquisa parcial, combinação e remoção dos filtros, detalhes, atualizações do cadastro e regressão da autenticação e do Admin. Os testes verificam conteúdo e produtos retornados, além dos códigos HTTP.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py test principal.test_catalogo
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe -m pip check
```

### Validação final da retomada — 28/10/2026

A auditoria encontrou o catálogo, os templates, 24 testes e esta documentação já implementados localmente, sem commit da Semana 5. O HEAD e o `main` remoto permaneciam em `b62289854eadc947987ca463279e86b79ea048f2`, correspondente à Semana 4. O trabalho existente foi preservado.

A primeira execução da suíte encontrou 85 testes, com 84 aprovados e uma falha no cenário de cadastro pelo Admin. O dado fictício de unidade tinha 31 caracteres, excedendo o limite de 30 do modelo. O formulário rejeitou corretamente esse valor; foi corrigido somente o dado do teste da Semana 5, sem flexibilizar a validação nem modificar os testes das Semanas 1 a 4.

A cobertura foi complementada com um teste que aceita pesquisa de 150 caracteres e rejeita 151, mantendo a categoria selecionada e os registros intactos. O teste de atualização de produto também passou a consultar a categoria antiga e a nova, confirmando que a troca de categoria se reflete nos filtros.

| Verificação executada | Resultado |
| --- | --- |
| `manage.py check` | Nenhum problema identificado. |
| `manage.py makemigrations --check --dry-run` | Nenhuma alteração detectada; nenhuma migration criada. |
| `manage.py migrate --plan` | Nenhuma operação planejada. |
| `manage.py migrate` | Nenhuma migration pendente para aplicar. |
| `manage.py test principal.test_catalogo --verbosity 2` | 25 testes aprovados, zero falhas. |
| `manage.py test` | 86 testes aprovados em 7,853 s, zero falhas: 61 anteriores e 25 de catálogo. |
| `python -m pip check` | Nenhuma incompatibilidade de dependências. |

As requisições foram verificadas pelo cliente HTTP de testes do Django, com banco temporário em memória: catálogo e detalhes ativos retornam 200 com conteúdo esperado; detalhes inativos/inexistentes retornam 404; filtros inválidos conservam 200 com erros e lista vazia; POST nas rotas de consulta retorna 405. Foram conferidos HTML, campos, links, registros retornados, remoção e combinação dos filtros, acesso autenticado, permissões administrativas e quantidade constante de consultas ao ampliar a lista.

A integração exercitou cadastro, edição e inativação no Admin e a visualização pública correspondente. Os testes anteriores de autenticação, CSRF, sessões e permissões permaneceram aprovados. Não foi necessário iniciar `runserver`.

O SHA-256 do `db.sqlite3` permaneceu idêntico antes e depois dos comandos. Nenhum dado fictício foi criado permanentemente e nenhuma migration anterior, modelo, configuração ou dependência foi alterada. Nesta retomada, somente `principal/test_catalogo.py`, este documento e o README receberam complementos; views, formulário, templates e CSS já existentes da Semana 5 foram preservados.

**Classificação técnica: A — Semana 5 concluída e pronta para revisão.** Nenhum commit, push ou funcionalidade da Semana 6 foi realizado nesta retomada.

## Critérios de aceite

| Critério | Implementação |
| --- | --- |
| Listagem de produtos ativos | Consulta restrita a `ativo=True` em todas as combinações. |
| Nome, preço e unidade | Dados do cadastro exibidos na listagem e nos detalhes. |
| Filtragem por categoria | Seleção validada e aplicada ao queryset público. |
| Pesquisa simples | Trecho do nome por `icontains`, com limites do SQLite documentados. |
| Combinação de filtros | Condições aplicadas conjuntamente no servidor; remoção independente e limpeza completa. |
| Detalhes do produto | Consulta pública aos dados existentes de um produto ativo. |
| Bloqueio de produtos inativos | Ausência na listagem e HTTP 404 no acesso direto. |
| Preservação do Admin | Cadastros e permissões existentes mantidos. |
| Testes automatizados | Suíte específica de catálogo e suíte completa das semanas anteriores. |
| Documentação | Este documento e seção da Semana 5 no README. |

## Decisões, pendências e próximas semanas

Foi preservada uma única aplicação, sem novos modelos, migrations, dependências ou permissões. O formulário centraliza a validação dos filtros, enquanto as views consultam os modelos existentes. A categoria inválida produz erro de formulário e lista vazia; produtos indisponíveis produzem HTTP 404. Essas escolhas evitam erro interno e divulgação de produtos inativos.

Disponibilidade continua sendo o campo booleano `ativo`, sem estoque quantitativo. Não há paginação, ordenação escolhida pelo visitante, busca aproximada ou tratamento adicional de acentos nesta entrega. Os dados comerciais reais e a identificação do supermercado dependem de D-005; nenhum cadastro comercial permanente foi inventado. A aprovação formal do supervisor permanece externa à validação técnica.

Carrinho e quantidades pertencem à Semana 6. Checkout, entrega, pagamento na entrega e criação de pedidos pertencem à Semana 7; consulta e operação dos pedidos pertencem à Semana 8. Não há API REST, pagamento online, integração externa, frontend definitivo ou deploy nesta implementação.
