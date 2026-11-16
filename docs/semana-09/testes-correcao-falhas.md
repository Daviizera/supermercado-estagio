# Semana 9 — Testes automatizados e correção de falhas

## Objetivo

Verificar se a aplicação atende aos requisitos e regras documentados, avaliar se a suíte automatizada realmente comprova os comportamentos esperados, corrigir as falhas encontradas e registrar os resultados para a validação final, conforme RNF-008 ([requisitos](../semana-02/requisitos.md)): testes de quantidades, totais, indisponibilidade, bairro inválido, permissões, transições e falha de registro, com resultados registrados.

Não houve alteração de modelos, migrations, dependências, regras comerciais ou configurações. Funcionalidades novas e ajustes visuais ficaram fora do escopo.

## Estado inicial

| Item | Situação |
| --- | --- |
| Commit de partida | `67343eb` (Semana 8), sincronizado com `origin/main`, sem alterações locais |
| Suíte | **273 testes aprovados** em 23,7 s |
| Avisos com `python -W default manage.py test` | **50 `ResourceWarning: unclosed database`** |
| Migrations | `0001` a `0004`, sem pendências |
| SQLite local | SHA-256 `4430d882de9f5f050c04c43ff7864693582bd9a3178bfbc6a2b79d4917576199`, sem pedidos |

## Metodologia

1. **Leitura** dos documentos das Semanas 2 a 8 e de todo o código e testes.
2. **Validação**: `check`, `check --deploy`, suíte com `-W default`, `makemigrations --check --dry-run`, `pip check`, `git diff --check`.
3. **Análise estática da suíte** por AST: testes por classe, testes sem asserção, uso de APIs privadas, verificações de banco e asserções negativas.
4. **Sondagens** em banco de testes em memória, fora do repositório, para comportamentos sem teste: identificadores fora da faixa, escape de HTML, mensagens previstas nos protótipos, preservação de dados após erros, usuário desativado e quantidades extremas.
5. **Concorrência** em cópias temporárias do `db.sqlite3`, fora do repositório: 20 rodadas de checkout simultâneo e 40 rodadas de transições simultâneas.
6. **Correções orientadas por testes**: para cada falha funcional, o teste de regressão foi escrito e executado antes da correção, demonstrando a falha; depois, a correção mínima e a suíte completa.
7. **Mutação**: defeitos injetados em memória para confirmar que os testes novos detectam regressões.

## Inventário da suíte

| Arquivo | Antes | Depois | Responsabilidade |
| --- | --- | --- | --- |
| `tests.py` | 1 | 1 | Página inicial |
| `test_models.py` | 23 | 23 | Validações e restrições do banco |
| `test_admin.py` | 13 | 13 | Cadastro interno, permissões; Pedido fora do Admin |
| `test_auth.py` | 24 | 24 | Cadastro, login, logout, CSRF, sessões |
| `test_catalogo.py` | 25 | 25 | Listagem, filtros, detalhes |
| `test_carrinho.py` | 59 | 59 | Quantidades, sessão malformada, serviço do carrinho |
| `test_checkout.py` | 88 | **91** | Configuração, valores, revisão, idempotência, concorrência, migration, preservação do endereço, análise AST |
| `test_pedidos.py` | 40 | **46** | Permissões, transições, área do cliente, mensagens da Tela 6 |
| `test_seguranca.py` | — | **11** | Escape de HTML, mascaramento de senhas, identificadores fora da faixa, acesso durante a sessão |
| **Total** | **273** | **293** | |

Avaliação da suíte anterior: as asserções são relevantes; os testes das áreas que gravam dados verificam o banco e a sessão, e os negativos comprovam que nada mudou (comparação da sessão, ausência de pedido, retrato completo do pedido e dos itens). A varredura apontou três testes "sem asserção" em `test_checkout.py`, que delegam as verificações ao auxiliar `alterar_produto_e_confirmar` (falso positivo). Há redundância parcial, mantida por decisão desta semana, entre `test_nova_compra_legitima_usa_outra_chave` e `test_compra_posterior_usa_a_nova_base`, e entre `test_reenvio_da_mesma_chave…` e `test_base_antiga_com_pedido…`.

## Matriz de cobertura

| Requisito / regra | Testes | Situação após a Semana 9 |
| --- | --- | --- |
| RF-001 a RF-004, RN-003 (catálogo) | `CatalogoTests`; escape em `EscapeHtmlTests` | Adequada |
| RF-005, RF-006 (cadastro, login, logout) | `AutenticacaoClientesTests`; mensagem do login em `MensagemLoginMeusPedidosTests` | Adequada |
| RNF-001 (credenciais) | `AutenticacaoClientesTests`; `MascaramentoDeSenhasTests` | Adequada (antes: parcial) |
| RF-007 (identificação para concluir) | `PersistenciaCheckoutTests` | Adequada |
| RF-008, RN-021 (pedidos próprios) | `AreaDoClienteTests`, `PedidoNaoEncontradoTests`, `IdentificadoresForaDaFaixaTests` | Adequada (antes: parcial e divergente) |
| RF-009 a RF-012, RN-005 a RN-007 (carrinho) | `test_carrinho.py` | Adequada |
| RF-013, RF-021 (revalidação, indisponibilidade) | `ProdutosCheckoutTests`, `RevisaoCompletaTests` | Adequada |
| RF-014, RF-015, RN-009, RN-011 (endereço, bairro) | `EnderecoCheckoutTests`, `PreservacaoEnderecoTests` | Adequada; formatos pendentes em D-004 |
| RF-016, RN-010, RN-013 (taxa, total, limite) | `ConfiguracaoCheckoutTests`, `ValoresCheckoutTests` | Adequada; valores reais pendentes em D-001 e D-002 |
| RF-017, RN-012 (pagamento na entrega) | `PersistenciaCheckoutTests` | Adequada |
| RF-018, RN-014, RN-015, RNF-004 (registro atômico, histórico) | `TransacaoCheckoutTests`, `PersistenciaCheckoutTests` | Adequada |
| RN-016 / D-003 (reconfirmação) | `RevisaoAssinadaTests`, `RevisaoCompletaTests` | Adequada |
| Idempotência (T-709 a T-711) | `IdempotenciaDeterministicaTests`, `BaseDaTentativaTests`, `ConcorrenciaCheckoutTests` | Adequada |
| RF-022, RN-021 (permissões) | `test_admin.py`, `AcessoInternoTests`, `AcessoDuranteASessaoTests` | Adequada (antes: parcial) |
| RF-023 (painel da equipe) | `PainelEquipeTests` | Adequada |
| RF-024, RN-018, RN-019 (transições) | `TransicoesTests`, `ConcorrenciaTransicoesTests` | Adequada |
| RF-025, RF-026, RN-020 (confirmação, estado atual) | `AreaDoClienteTests`, `PersistenciaCheckoutTests` | Adequada |
| RNF-002, RNF-003 (acesso no servidor, GET seguro, CSRF) | Distribuídos nos nove arquivos | Adequada |
| RNF-005 (erros preservam dados válidos) | Formulários; `PreservacaoEnderecoTests` | Adequada (antes: divergente) |
| Escape de HTML | `EscapeHtmlTests` | Adequada (antes: sem cobertura, comportamento correto) |
| RNF-006 (responsividade) | — | Semana 10 |

## Achados e correções

### Problemas funcionais

| ID | Severidade | Problema | Correção |
| --- | --- | --- | --- |
| S9-01 | Baixo | RNF-005: com token de revisão inválido ou base desatualizada, o checkout reapresentava o formulário vazio e o endereço digitado era perdido. | `principal/views.py`: nos erros da leitura da revisão, o formulário é reapresentado vinculado aos dados enviados (`EntregaForm(request.POST, configuracao=…)`, auxiliar `_entrega_enviada`). Somente campos de endereço são reaproveitados; a revisão continua recalculada no servidor. |
| S9-02 | Baixo | Tela 6: pedido inexistente ou de outro cliente retornava o 404 genérico, sem a mensagem prevista. | `_render_pedido_do_cliente` responde com o template `pedido_nao_encontrado.html` e status 404, com “Pedido não encontrado ou acesso não permitido.”. A resposta é idêntica para pedido inexistente, alheio ou identificador fora da faixa. As páginas globais de erro não foram alteradas. |
| S9-03 | Baixo | Tela 6: o visitante em Meus pedidos era levado ao login sem a mensagem prevista. | `EntrarView` (subclasse da `LoginView` nativa) acrescenta “Entre para consultar seus pedidos.” somente quando o destino já validado pelo Django (`get_redirect_url`) é `reverse('principal:meus_pedidos')`. A mensagem vai no contexto do template, sem acúmulo em recargas; `next` externo não exibe a mensagem nem redireciona para fora. |

### Problemas da própria suíte

| ID | Severidade | Problema | Correção |
| --- | --- | --- | --- |
| S9-04 | Baixo | 50 `ResourceWarning: unclosed database` nos testes com threads. Origem confirmada: o `close()` do backend SQLite do Django é ignorado para bancos em memória, e as conexões das threads nunca eram fechadas. | `fechar_conexoes_da_thread()` em `test_checkout.py` e `test_pedidos.py`: no `finally` da própria thread, fecha a conexão crua de cada wrapper inicializado e limpa a referência. As conexões do Django são locais a cada thread; o auxiliar recusa execução na thread principal, que mantém o banco compartilhado aberto. Nenhum filtro de avisos foi usado. |
| S9-05 | Baixo | `test_pedidos.py` lia mensagens pelo atributo privado `wsgi_request._messages` (6 usos). | Auxiliar `mensagens()` com a API pública `django.contrib.messages.get_messages`. |

### Comportamentos corretos sem teste

| ID | Severidade | Situação | Testes adicionados |
| --- | --- | --- | --- |
| S9-06 | Informativo | Escape de HTML, mascaramento de senhas, identificadores fora da faixa, perda de acesso durante a sessão e análise de `float` limitada a uma expressão regular. | `test_seguranca.py` (11 testes) e análise AST em `test_checkout.py` (descrita abaixo). |

### Pendências que não são defeitos

| ID | Tipo | Situação |
| --- | --- | --- |
| S9-07 | Supervisor | Produto com preço R$ 0,00 e quantidade no limite técnico (2⁶³−1) gera pedido válido: o limite monetário não restringe a quantidade. Não alterado. |
| S9-08 | Implantação | `check --deploy` aponta W004, W008, W009, W012, W016 e W018 (`SECRET_KEY` pública, `DEBUG`, cookies e HTTPS). Configuração de desenvolvimento; tratar nas Semanas 11 e 12. |

Continuam pendentes do supervisor: D-001 a D-004, o limite provisório de R$ 5.000,00, T-709 a T-711 e D-007.

## Testes de regressão adicionados

| Arquivo / classe | Testes | Comprova |
| --- | --- | --- |
| `test_checkout.PreservacaoEnderecoTests` | 2 | Token adulterado e base desatualizada preservam logradouro, número, complemento, bairro e telefone; a revisão apresentada é recalculada no servidor e ignora valores enviados; nenhum pedido criado; carrinho intacto. |
| `test_checkout.ValoresCheckoutTests` | +1 (e o teste de `float` fortalecido) | Análise AST sem achados nos seis módulos (`carrinho`, `checkout`, `forms`, `models`, `pedidos`, `views`); seis injeções detectadas. |
| `test_pedidos.PedidoNaoEncontradoTests` | 2 | Mensagem e 404 idênticos para pedido alheio, inexistente e 10³⁰, nas rotas de acompanhamento e confirmação, sem dados do proprietário; pedido próprio continua acessível. |
| `test_pedidos.MensagemLoginMeusPedidosTests` | 4 | Mensagem no login apenas para Meus pedidos, uma vez por página, com retorno ao destino; ausente em outras rotas e com `next` externo, que não redireciona para fora. |
| `test_seguranca.EscapeHtmlTests` | 3 | Nomes, unidades, endereço, bairro, usernames e mensagens com `<script>` e `<img onerror>` aparecem escapados no catálogo, detalhe, carrinho, checkout, confirmação, acompanhamento, Meus pedidos e painel da equipe. |
| `test_seguranca.MascaramentoDeSenhasTests` | 2 | O cadastro marca `password1` e `password2` como sensíveis e o login marca todos os parâmetros; o relatório de erro do Django não contém a senha (fictícia, nunca impressa). |
| `test_seguranca.IdentificadoresForaDaFaixaTests` | 3 | 10³⁰ em `/pedidos/<id>/`, `/pedidos/<id>/confirmacao/`, `/equipe/pedidos/<id>/`, `/equipe/pedidos/<id>/estado/`, detalhe de produto e rotas do carrinho: 404 ou redirecionamento, nunca 500. |
| `test_seguranca.AcessoDuranteASessaoTests` | 3 | Cliente ou integrante desativado vai ao login na requisição seguinte; retirar `change_pedido`, `view_pedido` ou `is_staff` produz 403 na requisição seguinte, sem alterar o pedido. |

### Análise AST de ponto flutuante

`usos_de_float` aponta chamadas a `float()`, conversões `from_float` e `create_decimal_from_float`, literais `float` e divisão verdadeira (`/`, que produz `float` entre inteiros). O único literal aceito é o atribuído diretamente a `ESPERA_INICIAL_APOS_TRAVA` (`0.05` segundo de espera após trava do banco, não valor monetário); qualquer chamada nessa mesma atribuição continua apontada. Resultado: **nenhum achado** no código atual; as injeções `float(subtotal)`, `Decimal.from_float`, `create_decimal_from_float`, `0.1`, `subtotal / 2` e `0.05 * float(1)` foram todas detectadas, e uma versão de `checkout.py` com o total calculado por `float()` gerou dois achados na linha alterada.

## Resultados antes e depois

| Etapa | Resultado |
| --- | --- |
| Suíte inicial | 273 testes aprovados; 50 `ResourceWarning`. |
| Testes de regressão de S9-01 a S9-03 antes das correções | 8 testes executados: **5 falharam** (18 asserções), reproduzindo as três falhas; 3 passaram, protegendo contra correções excessivas (pedido próprio acessível, ausência da mensagem em outras rotas e com `next` externo). |
| Os mesmos testes após as correções | 8 aprovados; suíte completa com 281 testes aprovados. |
| Testes de concorrência após S9-04 | 7 aprovados, 0 `ResourceWarning`. |
| Suíte final | **293 testes aprovados**, **0 `ResourceWarning`** e nenhum outro aviso com `-W default`. |

### Mutação

| Defeito injetado em memória | Testes que falharam |
| --- | --- |
| Templates com `autoescape` desligado | 9 (`test_seguranca`) |
| Área interna sem exigir `is_staff` | 1 (`test_seguranca`); 9 em `test_pedidos` (Semana 8) |
| `float()` no cálculo do total | Detectado pela análise AST |

Mutações das Semanas 6 a 8 (revisão sem nome/unidade, chave aleatória, `UPDATE` sem condição, transição extra, entre outras) continuam válidas para a suíte, que não teve testes removidos.

## Verificações de cálculos, permissões, segurança e concorrência

- **Cálculos:** nenhum `float` em código monetário; `localcontext(prec=100)` com `Inexact` no carrinho e no checkout; `full_clean()` antes de salvar `Pedido` e cada `ItemPedido`; limites de `DecimalField`, limite monetário inclusivo e precisão da taxa cobertos; preço apresentado, confirmado e gravado coincidem (revisão versão 2).
- **Permissões:** testadas por acesso direto às rotas e ao serviço, inclusive com permissões retiradas durante a sessão.
- **Segurança:** escape de HTML em todas as páginas que exibem dados de cadastro e pedidos; nenhum `|safe`, `mark_safe` ou `autoescape off`; senhas mascaradas em relatórios de erro; identificadores fora da faixa sem erro interno; GET e HEAD sem efeitos; CSRF em todos os POST.
- **Concorrência** (cópias do SQLite fora do repositório): checkout com duas abas simultâneas em 20 rodadas, 1 pedido por rodada, as duas respostas no mesmo pedido e nenhuma falha; transições simultâneas em 40 rodadas, sempre uma efetivada e a outra recusada com “O estado do pedido mudou. Atualize a consulta.”. O last-write-wins do carrinho na sessão continua como limitação documentada na Semana 6, sem efeito sobre a duplicidade de pedidos.

## Limitações

- RNF-006 (responsividade) e a revisão de usabilidade de RNF-005 pertencem à Semana 10.
- As mensagens corrigidas em S9-02 e S9-03 são as previstas nos protótipos, que continuam em revisão pelo supervisor (D-007).
- A concorrência totalmente simultânea foi verificada fora da suíte, em cópias do SQLite em arquivo, porque o banco de testes em memória usa cache compartilhado com travas por tabela.

## Validação final

| Comando | Resultado |
| --- | --- |
| `python manage.py check` | Nenhum problema identificado. |
| `python -W default manage.py test` | 293 testes aprovados; nenhum aviso. |
| `python manage.py makemigrations --check --dry-run` | Nenhuma alteração detectada; continuam `0001` a `0004`. |
| `python -m pip check` | Nenhuma incompatibilidade de dependências. |
| `git diff --check` | Nenhum problema de espaços em branco. |
| SQLite local | SHA-256 inalterado; sem pedidos, itens órfãos ou erros de integridade. |
