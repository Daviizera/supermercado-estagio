# Semana 8 — Gerenciamento de pedidos e acompanhamento

## Objetivo e requisitos

Permitir que a equipe autorizada consulte os pedidos recebidos e registre cada etapa do atendimento, e que o cliente consulte a lista e o estado atual dos próprios pedidos. A implementação permanece no monólito Django, na aplicação `principal`, com Django Templates e SQLite, sem JavaScript, API ou dependências novas, e **sem alterar modelos nem criar migrations**.

As referências são os [requisitos](../semana-02/requisitos.md), as [regras de negócio](../semana-02/regras-negocio.md), o [fluxo dos pedidos](../semana-02/fluxo-pedidos.md), as Telas 6 (consulta) e 7 dos [protótipos](../semana-02/prototipos.md), a [modelagem](../semana-03/modelagem-dados.md), a [autenticação](../semana-04/autenticacao-clientes.md) e a [finalização da compra](../semana-07/finalizacao-compra.md).

| Referência | Alcance nesta entrega |
| --- | --- |
| RF-008 | “Meus pedidos” e acompanhamento, sempre filtrados pelo usuário da sessão; pedido de outro cliente retorna HTTP 404 sem dados. |
| RF-022 e RN-021 | Área interna exige autenticação, `is_staff` e permissões nativas, verificadas nas views e no serviço; cliente não acessa nem altera. |
| RF-023 | Lista e detalhe da equipe com identificação, data, cliente, telefone, endereço e bairro, itens, quantidades, unidades, valores registrados, pagamento na entrega e estado. |
| RF-024, RN-018 e RN-019 | Somente as transições da tabela; tentativa inválida não altera o pedido; cancelamento apenas antes da saída para entrega. |
| RF-026 e RN-020 | O cliente vê o estado persistido ao abrir ou recarregar; sem atualização em tempo real nem notificações. |
| RNF-002 e RNF-003 | Testes com visitante, cliente A, cliente B e diferentes perfis da equipe; alterações somente por POST com CSRF. |

## Painel próprio da equipe

O gerenciamento usa páginas próprias em Django Templates (Tela 7). O Django Admin **não** é usado para pedidos: `Pedido` e `ItemPedido` continuam fora do registro do Admin, e o teste `test_superusuario_acessa_cadastros_e_pedidos_nao_sao_expostos` da Semana 3 permanece inalterado. Com isso, nenhum dado comercial do pedido é editável e as ações oferecidas seguem exclusivamente a tabela de transições.

- **Lista** (`/equipe/pedidos/`): pedido, username do cliente, bairro, total e estado, dos mais recentes aos mais antigos (`-criado_em`, desempate por `-pk`). Sem pedidos: “Nenhum pedido recebido.”. Não há filtros nem paginação.
- **Detalhe** (`/equipe/pedidos/<id>/`): todos os dados de RF-023 em modo somente leitura, com data/hora no fuso `America/Fortaleza`, valor de cada linha calculado a partir dos dados históricos do item e um botão por transição válida no estado atual. Estados terminais exibem “Estado terminal: nenhuma alteração disponível.”. Quem tem apenas permissão de consulta não vê botões.
- **Alteração** (`POST /equipe/pedidos/<id>/estado/`): envia o estado exibido (`estado_atual`) e o desejado (`novo_estado`), com CSRF, e retorna ao detalhe com mensagem de sucesso ou do erro.

As consultas usam `select_related('cliente')` na lista e `prefetch_related('itens')` no detalhe; testes confirmam número constante de consultas ao aumentar pedidos e itens.

## Permissões

São usadas somente as permissões nativas já existentes para `Pedido`, atribuídas manualmente pelo Admin em Usuários e Grupos. Nenhuma permissão, grupo ou usuário é criado por código.

| Operação | Requisitos |
| --- | --- |
| Lista e detalhe internos | Usuário autenticado e ativo, `is_staff=True` e `principal.view_pedido`. |
| Alteração de estado | Usuário autenticado e ativo, `is_staff=True` e `principal.change_pedido`. |

- Visitante é redirecionado ao login.
- Autenticado sem os requisitos recebe HTTP 403 com “Você não tem permissão para acessar esta área.”, inclusive cliente com permissões atribuídas mas sem `is_staff` e superusuário sem `is_staff`.
- Integrante com apenas `view_pedido` consulta, mas não altera.
- O superusuário com `is_staff` opera pelas permissões nativas do Django.
- A verificação ocorre nas views (decorador `_area_interna`) e novamente no serviço `pedidos.alterar_estado`; os links e botões ocultos são apenas conveniência.

## Área do cliente

| Rota | Conteúdo |
| --- | --- |
| `/pedidos/` | “Meus pedidos”: identificador, data, total e estado atual, somente com `cliente=request.user`, dos mais recentes aos mais antigos. Sem pedidos: “Você ainda não possui pedidos.”. |
| `/pedidos/<id>/` | “Acompanhamento do pedido”: itens, quantidades, unidades, preços e valores registrados, subtotal, taxa, total, endereço, telefone, pagamento e estado atual. |
| `/pedidos/<id>/confirmacao/` | Confirmação da Semana 7, mantida sem quebra de compatibilidade (título “Pedido registrado”). |

O acompanhamento e a confirmação usam a mesma consulta e o mesmo template (`confirmacao_pedido.html`, com o título como parâmetro). Pedido de outro cliente retorna HTTP 404 sem revelar dados; visitante é redirecionado ao login; nenhuma ação de alteração é exibida; um POST direto do cliente para a rota de alteração recebe HTTP 403. As páginas usam `never_cache`: o novo estado aparece ao recarregar. Não há polling, WebSocket nem notificações.

A navegação mostra **Meus pedidos** a usuários autenticados e **Gerenciamento de pedidos** apenas a quem tem `is_staff` e `view_pedido`.

## Rotas

| Rota | Nome | Métodos |
| --- | --- | --- |
| `/pedidos/` | `principal:meus_pedidos` | GET, HEAD |
| `/pedidos/<id>/` | `principal:acompanhamento_pedido` | GET, HEAD |
| `/pedidos/<id>/confirmacao/` | `principal:confirmacao_pedido` | GET, HEAD |
| `/equipe/pedidos/` | `principal:equipe_pedidos` | GET, HEAD |
| `/equipe/pedidos/<id>/` | `principal:equipe_pedido_detalhe` | GET, HEAD |
| `/equipe/pedidos/<id>/estado/` | `principal:equipe_alterar_estado` | POST |

## Tabela de transições

A tabela fica somente em `principal/pedidos.py` (`TRANSICOES`), transcrita de RN-018; um teste a compara com a tabela documentada.

| Estado atual | Próximos estados permitidos |
| --- | --- |
| Recebido | Confirmado, Cancelado |
| Confirmado | Em preparo, Cancelado |
| Em preparo | Saiu para entrega, Cancelado |
| Saiu para entrega | Entregue |
| Entregue | Nenhum (terminal) |
| Cancelado | Nenhum (terminal) |

Não há outras transições: pular etapas, retroceder, reabrir, cancelar após a saída para entrega ou alterar pedidos terminais é recusado com “Esta alteração não é permitida para o estado atual.”. Uma única permissão (`change_pedido`) controla todas as transições; não há perfis separados de atendente e entregador.

## Concorrência e páginas antigas

`pedidos.alterar_estado` executa, nesta ordem:

1. verifica `is_staff` e `change_pedido`;
2. confirma que o pedido existe (inexistente: HTTP 404);
3. verifica na tabela se o novo estado é permitido a partir do estado esperado;
4. executa uma única instrução condicional:

```python
Pedido.objects.filter(pk=pedido_id, estado=estado_esperado).update(estado=novo_estado)
```

O estado esperado, enviado pela página, é apenas uma pré-condição; a autorização vem da permissão e da tabela, e a condição `estado=estado_esperado` garante que a tabela foi aplicada ao estado realmente gravado. Se nenhuma linha for alterada, o pedido não está mais no estado exibido e a resposta é “O estado do pedido mudou. Atualize a consulta.”, sem nova tentativa. Assim:

- uma ação repetida (duplo clique ou reenvio) avança no máximo uma etapa;
- duas pessoas com páginas antigas não sobrepõem a ação uma da outra;
- duas requisições simultâneas a partir do mesmo estado efetivam no máximo uma transição.

Como há uma única gravação, atômica por si, nenhuma transação adicional é necessária. Somente a coluna `estado` é alterada: cliente, endereço, telefone, valores, itens, data de criação e dados históricos dos produtos permanecem iguais, o que os testes comparam antes e depois de cada operação. Falha do banco mantém o estado e informa “Não foi possível salvar a alteração.”.

## Testes e validação

A suíte `principal/test_pedidos.py` contém **40 testes**:

| Grupo | Cobertura |
| --- | --- |
| Acesso interno | Visitante ao login; 403 para cliente, staff sem permissão, staff só com `change_pedido`, cliente com permissões sem `is_staff` e superusuário sem `is_staff`; consulta sem alteração com `view_pedido`; operador e superusuário operam; serviço também verifica; pedido inexistente 404; links de navegação por perfil. |
| Painel | Lista vazia; ordem por data e desempate; cliente, bairro, total e estado; detalhe com todos os dados de RF-023; ações oferecidas iguais à tabela em cada estado; terminais sem ações; dados comerciais não editáveis; consultas constantes na lista e no detalhe. |
| Transições | Tabela igual à documentação; cada transição válida altera somente o estado; sequência completa; todas as combinações fora da tabela, inclusive estados inexistentes e variações de grafia, recusadas sem alterar nada; casos nomeados; estado esperado divergente, ausente ou forjado; ação repetida; páginas antigas de duas pessoas; falha do banco; uma única instrução `UPDATE` condicional. |
| Métodos e CSRF | GET e HEAD na rota de alteração com HTTP 405; POST sem CSRF com HTTP 403; POST com CSRF aplicado; páginas de consulta não aceitam POST. |
| Cliente | Lista apenas com pedidos próprios e na ordem correta; lista vazia; detalhe próprio; pedido alheio 404 nas rotas de acompanhamento e de confirmação; visitante ao login; novo estado após recarregar, inclusive Cancelado; sem ações administrativas; POST direto com HTTP 403. |
| Concorrência | Threads simultâneas com a mesma ação e com ações diferentes a partir do mesmo estado: exatamente uma transição efetivada e dados preservados. |

Verificações por mutação, com defeitos injetados em memória, confirmaram que a suíte detecta atualização sem a condição de estado, ausência da exigência de `is_staff`, serviço sem verificação de permissão e transição extra na tabela. Um ensaio fora da suíte, sobre uma cópia em arquivo do `db.sqlite3`, executou 40 rodadas de duas transições simultâneas a partir do mesmo estado: em todas, exatamente uma foi efetivada e a outra recebeu “O estado do pedido mudou. Atualize a consulta.”.

| Verificação executada | Resultado |
| --- | --- |
| `manage.py check` | Nenhum problema identificado. |
| `manage.py test principal.test_pedidos` | 40 testes aprovados. |
| `manage.py test` | 273 testes aprovados: 233 anteriores e 40 da Semana 8. |
| `manage.py makemigrations --check --dry-run` | Nenhuma alteração detectada; nenhuma migration criada. |
| `python -m pip check` | Nenhuma incompatibilidade de dependências. |
| `git diff --check` | Nenhum problema de espaços em branco. |

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test principal.test_pedidos
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
```

## Decisões adotadas

| ID | Decisão | Origem |
| --- | --- | --- |
| T-801 | Painel próprio em Django Templates; Pedido e ItemPedido fora do Admin. | Aprovada (D-006 para a operação). |
| T-802 | Permissões nativas `view_pedido` e `change_pedido`, mais `is_staff`, sem permissões próprias nem migration. | Aprovada. |
| T-803 | Sem histórico de alterações de estado: o requisito pede o estado atual. | Aprovada. |
| T-804 | Uma permissão para todas as transições; sem perfis de atendente e entregador. | Aprovada. |
| T-805 | Cliente identificado pelo username; sem filtros nem paginação; mais recentes primeiro. | Aprovada. |
| T-806 | Acompanhamento e confirmação compartilham consulta e template, com título por parâmetro. | Técnica. |
| T-807 | Página de acesso negado própria (`acesso_negado.html`, HTTP 403) usada somente pela área interna. | Técnica; o comportamento 403 do Admin e do CSRF não foi alterado. |

## Limitações restantes

- Não há registro de quem alterou o estado nem de quando: somente o estado atual é armazenado (T-803).
- Não há filtros, busca ou paginação na lista da equipe; volumes grandes de pedidos dependerão de decisão futura.
- O cliente vê o novo estado apenas ao recarregar; não há notificações.
- Atribuir `is_staff` e as permissões aos integrantes da equipe é uma tarefa manual no Admin; o banco local continua sem usuários.
- As pendências comerciais das semanas anteriores continuam: sem bairros e taxa configurados (D-001, D-002), o checkout segue bloqueado em uso real, e os pedidos dos testes são criados apenas no banco temporário.
