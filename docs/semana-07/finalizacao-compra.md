# Semana 7 — Finalização da compra e registro dos pedidos

## Objetivo e requisitos

Permitir que o cliente autenticado revise o carrinho, informe o endereço de entrega, confira subtotal, taxa e total calculados no servidor e confirme a compra com pagamento na entrega, gerando `Pedido` e `ItemPedido` em uma única transação. A implementação permanece no monólito Django, na aplicação `principal`, com Django Templates e SQLite, sem JavaScript, API ou dependências novas.

As referências são os [requisitos](../semana-02/requisitos.md), as [regras de negócio](../semana-02/regras-negocio.md), o [fluxo de compra](../semana-02/fluxo-compra.md), as Telas 4, 5 e 6 (confirmação) dos [protótipos](../semana-02/prototipos.md), a [modelagem](../semana-03/modelagem-dados.md), a [autenticação](../semana-04/autenticacao-clientes.md) e o [carrinho](../semana-06/carrinho-compras.md).

| Referência | Alcance nesta entrega |
| --- | --- |
| RF-007 | Checkout e confirmação exigem login; POST sem autenticação não cria pedido. |
| RF-013 e RN-008 | Carrinho, produtos, quantidades, entrega, bairro e valores são revalidados na confirmação. |
| RF-014 e RN-011 | Logradouro, número, bairro e telefone obrigatórios; complemento opcional. |
| RF-015 e RN-009 | Bairro validado no servidor contra a configuração central; sem lista, a compra não é liberada. |
| RF-016 e RN-010 | Subtotal, taxa fixa única e total exibidos separadamente; sem taxa configurada, a compra não é liberada. |
| RF-017 e RN-012 | Pagamento exclusivamente na entrega, informado antes do botão de confirmação. |
| RF-018, RN-013 a RN-015 e RNF-004 | Pedido e itens criados atomicamente, com valores históricos; carrinho esvaziado somente após sucesso. |
| RN-016 (proposta D-003) | Mudança de preço, itens ou taxa desde a revisão exige nova confirmação. |
| RN-017 | O pedido nasce no estado padrão do modelo, **Recebido**. |
| RF-021 | Produto inativo ou excluído impede a criação do pedido, mesmo já estando no carrinho. |
| RF-025 | Página de confirmação com identificação, itens, valores, entrega e estado. |

Consulta de “Meus pedidos”, acompanhamento, operação pela equipe, transições de estado e registro de Pedido no Admin pertencem à Semana 8 e **não foram implementados**.

## Fluxo de finalização

| Passo | Rota e método | Comportamento |
| --- | --- | --- |
| 1 | `GET /carrinho/` | O link **Finalizar compra** aparece quando o carrinho não está vazio. É apenas um link GET. |
| 2 | `GET /checkout/` | Visitante é redirecionado a `/login/?next=/checkout/`; após o login, retorna ao checkout com o carrinho preservado. |
| 3 | `GET /checkout/` | O servidor valida a configuração e o carrinho, recalcula os valores e apresenta itens, quantidades, preços, valores das linhas, subtotal, taxa, total, pagamento na entrega, formulário de endereço e um token de revisão assinado. Nada é gravado. |
| 4 | `POST /checkout/` | Lê o token, verifica se a chave já gerou pedido, valida configuração e endereço, revalida e recalcula tudo e cria o pedido em transação. |
| 5 | `GET /pedidos/<id>/confirmacao/` | Após o sucesso, redirecionamento para a confirmação, acessível somente pelo próprio cliente. |

A revisão e o endereço ficam na mesma página, e o cliente vê o bairro selecionado, a taxa e o total antes de confirmar. Os protótipos separam essas informações em duas telas (4 e 5); a disposição dos protótipos é ilustrativa ([prototipos.md](../semana-02/prototipos.md), introdução) e a junção é uma decisão técnica provisória (T-701).

Bloqueios apresentados no checkout, sem formulário de confirmação: configuração ausente ou inválida (“A entrega ainda não está disponível. Não é possível finalizar a compra no momento.”), carrinho vazio, produto inativo ou excluído e dados inconsistentes no carrinho. Quando o total ultrapassa o limite, os valores são exibidos com o aviso e sem o botão **Confirmar pedido**.

## Configurações centralizadas

Os valores ficam somente em `supermercado/settings.py` e são lidos e validados a cada uso por `checkout.obter_configuracao()`; views, formulários, templates e o carrinho não repetem os valores.

| Configuração | Valor atual | Significado |
| --- | --- | --- |
| `CHECKOUT_BAIRROS_ATENDIDOS` | `()` | Lista de bairros atendidos. Vazia: nenhum bairro real foi fornecido (D-001). |
| `CHECKOUT_TAXA_ENTREGA` | `None` | Taxa fixa única. `None`: não definida (D-002). `Decimal('0.00')` representaria entrega explicitamente gratuita e é aceito. |
| `CHECKOUT_VALOR_MAXIMO_PEDIDO` | `Decimal('5000.00')` | Valor máximo do pedido, incluindo a taxa. **Decisão operacional provisória, pendente de validação do supervisor.** |

**Com os valores atuais, o checkout real permanece bloqueado** até que o supermercado e o supervisor forneçam bairros e taxa. Nenhum bairro ou taxa fictícios foram colocados na configuração; os testes usam `override_settings` com um bairro e uma taxa de `Decimal('5.00')` exclusivamente durante sua execução.

Validação da configuração (qualquer falha bloqueia o checkout com a mesma mensagem genérica):

- **Bairros:** lista, tupla ou conjunto de textos não vazios, cabendo em `Pedido.bairro` (100 caracteres). Espaços repetidos são reduzidos; nomes iguais após a normalização são unificados.
- **Taxa e limite:** obrigatoriamente `Decimal` (não `int`, `float`, texto ou `bool`), finito, não negativo e que caiba no `DecimalField` correspondente de `Pedido` (12 dígitos, 2 casas). Zeros finais extras são aceitos (`Decimal('5.000')` equivale a `5.00`); qualquer outra casa além da segunda (`Decimal('5.005')`) é **rejeitada, nunca arredondada**. O limite deve ser maior que zero.

## Endereço

O formulário `EntregaForm` usa os campos existentes de `Pedido`, com os tamanhos lidos do próprio modelo. As regras ficam em `checkout.validar_entrega`, aplicada pelo formulário (para associar os erros aos campos) e novamente pelo serviço no registro.

| Campo | Regra |
| --- | --- |
| `logradouro` | Obrigatório, até 200 caracteres. |
| `numero` | Obrigatório, até 20 caracteres, texto livre. |
| `complemento` | Opcional, até 150 caracteres. |
| `bairro` | Obrigatório; escolhido na lista configurada e revalidado no servidor. |
| `telefone` | Obrigatório, até 30 caracteres, texto livre. |

Espaços no início e no fim são removidos; campo composto só de espaços é tratado como vazio. O bairro é comparado sem diferenciar espaços repetidos nem maiúsculas e minúsculas (`casefold`), e o pedido grava o nome configurado. **Acentos não são normalizados**: “Fictício” e “Ficticio” são bairros diferentes. Bairro fora da lista, inclusive enviado manualmente, recebe “Bairro não atendido. Selecione um bairro da lista.”.

Não foram criados formatos de telefone, CEP, máscara de logradouro nem tratamento específico de endereço sem número: dependem de D-004. A formatação comercial definitiva do endereço continua pendente.

## Recálculo de preços e revisão assinada

O navegador nunca determina valores. A cada revisão e na confirmação, o serviço lê o carrinho da sessão, consulta os produtos no banco em uma única consulta e calcula:

```text
Valor da linha = quantidade × preço atual do produto
Subtotal = soma dos valores das linhas
Total = subtotal + taxa de entrega configurada
```

Todos os cálculos usam `Decimal` em contexto de 100 dígitos com a armadilha `Inexact` ativa, como no carrinho; não há uso de `float`. O pedido só é criado se não houver produto inativo ou excluído nem entrada inconsistente no carrinho, de modo que as decisões provisórias T-601 e T-602 da Semana 6 afetam apenas a apresentação do carrinho, nunca os valores de um pedido.

O token de revisão é gerado com `django.core.signing` (sal próprio, assinatura com a `SECRET_KEY`). Na **versão 2**, ele contém o identificador do usuário, a base de idempotência (ver Idempotência) e o conteúdo apresentado:

```json
{
  "v": 2, "usuario": 7, "base": 0,
  "conteudo": {
    "itens": [[12, "<nome>", "<unidade>", 2, "12.50", "25.00"]],
    "subtotal": "25.00", "taxa_entrega": "5.00", "total": "30.00",
    "bairros": ["<bairros configurados>"]
  }
}
```

Cada item traz identificador, nome, unidade, quantidade, preço unitário e valor da linha, em texto decimal. O token não determina valores nem a chave do pedido: na confirmação, o servidor recalcula o conteúdo com os dados atuais e o compara ao conteúdo assinado.

- Conteúdo igual: o pedido é criado com os valores recalculados, que são exatamente os apresentados.
- Qualquer diferença — nome, unidade, preço, quantidade, itens, valores, taxa ou lista de bairros configurados: nenhum pedido é criado; a página reapresenta os dados atualizados com “Os valores foram atualizados. Confira antes de confirmar novamente.”, com um novo token **da mesma tentativa** (mesma base e mesma chave). O cliente precisa confirmar novamente. A mesma mensagem aparece quando o formulário de endereço volta com erros e os dados mudaram desde a revisão.
- Token ausente, adulterado, assinado com outro sal, emitido para outro usuário, da versão 1 ou desconhecida, ou com base que não seja um inteiro não negativo: recusado com “Não foi possível validar a revisão do pedido. Confira os valores e confirme novamente.”, sem pedido.

O bairro escolhido é enviado no próprio formulário de confirmação e validado contra a configuração; a lista de bairros entra na revisão para que uma mudança nas opções oferecidas exija nova confirmação. Bairro retirado da lista é recusado como não atendido.

## Limite monetário provisório

O total (subtotal + taxa) deve ser **menor ou igual** a `CHECKOUT_VALOR_MAXIMO_PEDIDO`: exatamente R$ 5.000,00 é aceito; R$ 5.000,01 é recusado, assim como qualquer subtotal acima do limite. A comparação usa `Decimal`. O valor do limite aparece somente na configuração; um teste verifica que ele não está repetido no código da aplicação.

O carrinho da Semana 6 não foi alterado para antecipar o limite: a validação definitiva ocorre na revisão e novamente na confirmação, dentro da transação. Não foi criada restrição no banco com o valor do limite, para que ele permaneça centralizado e possa ser revisto sem nova migration. O limite também não substitui as validações estruturais dos campos (`max_digits=12`, `decimal_places=2`), que continuam aplicadas por `full_clean()`.

## Transação atômica e validação dos modelos

`checkout.registrar_pedido` executa, nesta ordem:

1. Confirma usuário autenticado e ativo, base e conteúdo revisado, e deriva a chave.
2. Procura um pedido existente com a chave (ver Idempotência).
3. Lê e valida a configuração central.
4. Valida o endereço.
5. Dentro de `transaction.atomic()`:
   1. revalida carrinho e produtos no banco e recalcula os valores;
   2. compara com a revisão assinada;
   3. verifica o limite;
   4. monta o `Pedido` com `cliente=request.user` e a chave, executa `full_clean()` e salva;
   5. para cada linha, monta o `ItemPedido`, executa `full_clean()` e salva.
6. Ao sair da transação confirmada, a view remove a chave do carrinho da sessão e redireciona para a confirmação.

`save()` não chama `full_clean()`. Na auditoria preparatória, gravar valores fora da capacidade sem essa validação produziu arredondamento silencioso (`1.005` lido como `1.00`) e registros ilegíveis (`InvalidOperation` na leitura); por isso a validação é obrigatória antes de cada gravação.

Qualquer `ValidationError` ou `DatabaseError` desfaz toda a transação: não ficam pedidos sem itens nem itens isolados. O tratamento ocorre **fora** do bloco `atomic`, depois do rollback, para que nenhuma consulta seja feita dentro de uma transação com erro:

| Erro | Tratamento |
| --- | --- |
| Validação de unicidade da chave ou `IntegrityError` | Outra requisição já confirmou a mesma tentativa: o pedido existente é consultado e devolvido. |
| Outro `DatabaseError`, como `OperationalError: database is locked` do SQLite | A outra transação pode ainda estar confirmando: a chave é consultada novamente até cinco vezes, com esperas de 0,05, 0,1, 0,2 e 0,4 s (no máximo ~0,75 s). Se o pedido aparecer, é devolvido. |
| Nenhum pedido com a chave após as consultas, ou outro `ValidationError` | Falha real: nenhum pedido foi registrado para esta tentativa, o carrinho permanece e a página informa “Não foi possível registrar o pedido. Seu carrinho foi mantido.”. |

Erros de configuração, endereço, carrinho ou limite são detectados antes de qualquer gravação e também preservam o carrinho. Uma tentativa que falhou pode ser confirmada novamente com a mesma chave.

## Idempotência

`Pedido.chave_idempotencia` é um `UUIDField(default=uuid.uuid4, unique=True, editable=False)`; o modelo e as migrations não mudaram. Os pedidos do checkout usam uma **chave determinística**, derivada no servidor:

```text
chave = uuid5(NAMESPACE_CHAVES_PEDIDO, "<id do usuário>:<base>")
base  = id do último pedido do usuário quando a revisão foi emitida, ou 0
```

A base assinada não é aceita apenas por estar no token, porque a `SECRET_KEY` de desenvolvimento é pública e permitiria forjar uma base qualquer. O POST segue esta ordem (`checkout.pedido_da_tentativa`, usada pela view e novamente pelo serviço):

1. valida o token e identifica usuário e base;
2. deriva a chave no servidor;
3. procura pedido do usuário autenticado com essa chave;
4. se encontrar, devolve a confirmação existente (reenvio legítimo, mesmo de uma base antiga);
5. se não encontrar, exige que a base seja o último pedido atual do usuário;
6. se não for, consulta a chave mais uma vez (o último pedido pode ser o desta tentativa, confirmado por uma requisição concorrente) e, sem pedido, recusa com “Esta revisão do pedido não é mais válida para suas compras. Confira os valores e confirme novamente.”, apresentando nova revisão com a base atual;
7. só então segue para a validação e a criação do pedido.

Assim, um token com base arbitrária ou desatualizada não gera uma chave nova nem contorna a idempotência.

O `NAMESPACE_CHAVES_PEDIDO` é uma constante fixa de `principal/checkout.py`. A base viaja no token assinado; **a chave nunca é recebida do navegador** e campos como `chave` ou `chave_idempotencia` enviados no POST ou inseridos no token são ignorados. Como o usuário faz parte da derivação, um token forjado não alcança a chave de outro cliente. O `default=uuid.uuid4` do modelo continua valendo para pedidos criados fora do checkout, como os preexistentes preenchidos pela migration.

| Situação | Resultado |
| --- | --- |
| Mesma página reenviada | Mesma base e mesma chave: devolve o pedido já registrado, sem tocar no carrinho atual. |
| Duas páginas do mesmo usuário abertas antes da conclusão (abas ou dispositivos) | Mesma base e mesma chave: no máximo um pedido; a outra confirmação recebe a confirmação do primeiro pedido e mantém o próprio carrinho. |
| Compra posterior | Após um pedido, o último pedido do usuário muda; uma nova abertura do checkout gera outra chave. |
| Reapresentação por mudança de dados | Mantém a base e, portanto, a chave. |
| Pedido de outro usuário | A confirmação filtra pelo cliente e retorna HTTP 404; uma colisão de chave, impossível pela derivação, também seria recusada sem revelar dados. |

**A garantia final é a restrição `UNIQUE` do banco.** As consultas prévias apenas devolvem o pedido já criado; se duas requisições concorrentes passarem por elas, a segunda falha na validação de unicidade, na própria restrição ou na trava do SQLite, e o serviço devolve o pedido gravado pela primeira.

**Efeito colateral autorizado (T-709):** duas compras simultâneas do mesmo usuário, abertas em dispositivos distintos antes de qualquer uma ser concluída, são tratadas como uma única tentativa. A segunda recebe a confirmação do primeiro pedido, e seu carrinho atual é preservado; para realizar outra compra, o usuário deve reabrir o checkout após a conclusão da primeira.

A auditoria complementar havia reproduzido dois pedidos para o mesmo carrinho quando duas páginas, com chaves aleatórias distintas, eram confirmadas de forma intercalada, e mensagens de falha falsas quando o SQLite derrubava uma das transações sobrepostas. Ambos os casos são cobertos pelos testes e pelo ensaio descritos em Testes e validação.

### SECRET_KEY

A `SECRET_KEY` atual está literal em `supermercado/settings.py`, tem o prefixo de chave insegura do Django, é exclusiva de desenvolvimento e está versionada desde a Semana 1; portanto é pública. A configuração atual não lê variável de ambiente e não foi alterada nesta etapa. **O ambiente de produção precisa usar uma `SECRET_KEY` privada, gerada separadamente, fornecida por variável de ambiente e independente da chave pública do repositório.** A integridade dos valores não depende do sigilo da assinatura, porque o servidor sempre recalcula e compara o conteúdo, e a derivação da chave inclui o próprio usuário; ainda assim, com a chave pública, qualquer pessoa pode forjar tokens de revisão. Trocar a chave invalida sessões e tokens em aberto.

## Migration

A coluna foi adicionada em três migrations, conforme a orientação do Django para campos únicos em tabelas que podem ter registros:

| Migration | Operação |
| --- | --- |
| `0002_pedido_chave_idempotencia` | Adiciona a coluna anulável, sem unicidade. |
| `0003_preencher_chave_idempotencia` | Gera um `uuid4` distinto para cada pedido sem chave; não altera outras colunas. Reversão sem operação. |
| `0004_alter_pedido_chave_idempotencia` | Torna a coluna obrigatória e única, com `default=uuid.uuid4`. |

No SQLite, a etapa 3 recria a tabela e preenche valores nulos com um único UUID; por isso o preenchimento individual da etapa 2 é indispensável, e qualquer linha não preenchida faria a migration falhar em vez de duplicar chaves. As quatro restrições `CHECK` de `Pedido` são preservadas.

Verificação:

- Teste automatizado com `MigrationExecutor`: três pedidos criados no esquema `0001` recebem chaves UUID4 distintas, mantêm todos os outros campos e uma duplicidade posterior é recusada.
- Ensaio em uma cópia do `db.sqlite3` anterior à migration, com cinco pedidos inseridos somente na cópia: cinco chaves distintas, dados preservados e `UNIQUE constraint failed` ao forçar duplicidade.
- Banco local de desenvolvimento: a migration foi aplicada com `migrate`; o banco tinha zero pedidos. Após a aplicação, `integrity_check` retornou `ok`, `foreign_key_check` não apontou problemas e não há chaves nulas ou duplicadas.

## Histórico dos itens

Cada `ItemPedido` recebe `nome_produto`, `unidade` e `preco_unitario` copiados do produto no momento da confirmação, além da quantidade e da referência ao produto. Os tamanhos desses campos são idênticos aos de `Produto`, então a cópia não trunca dados. `Pedido` guarda endereço, telefone, subtotal, taxa e total. Alterações posteriores de nome, unidade, preço ou disponibilidade do produto não modificam o pedido nem os itens; a página de confirmação exibe os valores registrados.

## Carrinho com entradas não identificadas

A limitação T-608 da Semana 6 foi resolvida com a ação explícita `POST /carrinho/remover-nao-identificados/`, exibida no carrinho somente quando há registros não identificados. Ela exige CSRF, não aceita GET ou HEAD, remove apenas as chaves que não correspondem a um produto identificável (ou substitui por um carrinho vazio uma estrutura que não é dicionário) e preserva todos os itens identificáveis, inclusive os de quantidade inconsistente, que continuam sujeitos à remoção individual. O GET continua sem corrigir a sessão. Enquanto houver qualquer entrada inconsistente, o checkout é bloqueado com “Há dados inconsistentes no carrinho. Corrija o carrinho para continuar.”.

## Segurança

- `@login_required` no checkout e na confirmação; o pedido é sempre vinculado a `request.user`, e campos como `cliente_id`, `estado`, preços e totais enviados no POST são ignorados.
- O checkout aceita GET, HEAD e POST; GET e HEAD não gravam pedido nem sessão. A confirmação aceita somente GET e HEAD. Todos os POST exigem CSRF.
- A confirmação filtra por `cliente=request.user`: outro usuário recebe HTTP 404 sem dados; visitante é redirecionado ao login.
- `never_cache` no checkout e na confirmação, que exibem endereço e telefone.
- Mensagens e dados são exibidos com o escape automático dos templates.

## Sessão

Após a criação de um novo pedido, somente a chave `carrinho` é removida (`Carrinho.esvaziar()`, sem `session.flush()`); autenticação e demais dados da sessão são preservados. Falhas não alteram o carrinho. O logout continua limpando toda a sessão, conforme a Semana 4, decisão confirmada.

A limitação last-write-wins da sessão, documentada na Semana 6, continua existindo para o carrinho; a duplicidade de pedidos, porém, é impedida pela chave determinística e pela restrição única no banco, e não depende da sessão.

## Testes e validação

A suíte `principal/test_checkout.py` contém **88 testes**: 61 da implementação inicial, atualizados para a revisão versão 2 e a chave derivada, 19 das correções de revisão e idempotência e 8 da verificação da base.

| Grupo | Cobertura |
| --- | --- |
| Configuração | Padrão sem dados comerciais e bloqueado; sem bairros; sem taxa; taxa zero aceita; 21 configurações inválidas de taxa, bairros e limite; normalização sem arredondamento. |
| Endereço | Endereço válido; normalização de espaços e capitalização do bairro; bairro não atendido e com acento diferente; campos obrigatórios vazios e só com espaços; tamanhos máximo e máximo + 1; validação pelo serviço sem formulário; lista de bairros exibida. |
| Valores | Subtotal, taxa e total em `Decimal`; total exatamente no limite aceito; um centavo acima e subtotal acima recusados; limite lido somente da configuração e não duplicado no código; ausência de `float`; `full_clean()` antes de salvar. |
| Produtos e carrinho | Carrinho vazio; produto inativo; produto excluído; preço alterado exige nova confirmação com mesma chave; carrinho alterado após a revisão; valores, cliente e estado forjados ignorados; entradas malformadas bloqueiam. |
| Não identificados | Remoção somente dos registros não identificados; estrutura inválida; nada a remover; GET/HEAD com HTTP 405 e CSRF; visitante; botão condicional. |
| Persistência | Pedido, itens, cliente, chave, estado Recebido, pagamento na entrega e histórico; histórico estável após alterar o produto; confirmação restrita ao dono; visitante redirecionado e retorno ao checkout após login; GET sem efeitos; métodos e CSRF; consultas constantes. |
| Transação | Falha ao salvar o pedido; falha no segundo item; erro de validação do item; nova tentativa após falha. Em todos: nenhum pedido ou item e carrinho intacto. |
| Idempotência | Reenvio da mesma página sem novo pedido e sem apagar carrinho novo; páginas anteriores à compra compartilham a chave e uma página posterior recebe outra; chave de outro cliente sem revelar dados; token de outro cliente; conflito detectado pela validação e pela restrição do banco; restrição `UNIQUE` ativa; chaves distintas por padrão do modelo. |
| Revisão | Taxa alterada; token adulterado; catorze tokens inválidos (inclusive versão 1 e bases inválidas); conteúdo forjado com assinatura válida não cria pedido. |
| Revisão completa | Nome, unidade, e nome e unidade alterados exigem reconfirmação sem criar pedido; nova confirmação registra exatamente os dados reapresentados; token antigo reenviado não registra dados não apresentados; lista de bairros alterada exige nova revisão; bairro retirado é recusado; conteúdo assinado da versão 2. |
| Idempotência determinística | Derivação por usuário e base (UUID versão 5); duas abas da mesma sessão geram um pedido; segundo dispositivo recebe o primeiro pedido, mantém o carrinho e compra após reabrir o checkout; chave enviada pelo navegador ignorada; `database is locked` com pedido já confirmado, com a outra transação confirmando depois e sem pedido (falha real). |
| Base da tentativa | Base atual sem pedido aceita; base antiga com pedido devolve esse pedido e preserva o carrinho; base desatualizada sem pedido e bases arbitrárias recusadas, com nova revisão na base atual; tokens forjados com a `SECRET_KEY` de desenvolvimento não criam pedidos adicionais nem aceitam outro usuário; compra posterior usa a nova base; usuários diferentes não compartilham chaves. |
| Concorrência | Threads reais com a segunda confirmação pausada após carregar a sessão: duas abas na consulta inicial, antes da conferência da base, após a consulta prévia do serviço e com a validação de unicidade desligada (somente a restrição `UNIQUE`); dois dispositivos com o segundo carrinho preservado. Em todos: um pedido e as duas respostas apontando para ele. |
| Sessão | Sucesso remove somente o carrinho e mantém a autenticação; logout continua limpando o carrinho. |
| Migration | Pedidos preexistentes recebem chaves distintas, sem alterar os demais dados. |

Verificações por mutação, com defeitos injetados em memória, confirmaram que a suíte detecta: carrinho não esvaziado, limite ignorado, qualquer bairro aceito, revisão não comparada, revisão sem nome, unidade e bairros, revisão sem a lista de bairros, chave aleatória por requisição, ausência de nova consulta após a trava, ausência da validação da base e ausência da nova consulta antes de recusar uma base alterada por uma confirmação concorrente.

O banco de testes em memória do SQLite usa cache compartilhado com travas por tabela, diferente de um arquivo SQLite real. Por isso, a concorrência totalmente simultânea foi verificada também por um ensaio fora da suíte, sobre uma cópia em arquivo do `db.sqlite3`: em 20 rodadas, duas abas da mesma sessão confirmaram ao mesmo tempo, após carregarem a sessão. Resultado, repetido após a validação da base: 20 pedidos (um por rodada), as duas respostas de cada rodada redirecionadas para o mesmo pedido, nenhuma mensagem de falha, nenhuma base legítima recusada, nenhum pedido sem itens e 20 ocorrências de `database is locked` resolvidas pela consulta após o rollback. Antes da correção, o mesmo ensaio produzia uma mensagem de falha falsa em todas as rodadas, e a execução intercalada produzia dois pedidos.

Na Semana 6, o teste `test_carrinho_nao_cria_pedidos_nem_oferece_finalizacao` afirmava a ausência de qualquer texto “Finalizar” no carrinho, conforme a decisão T-607 daquela semana. Como esta semana exige acesso à finalização a partir do carrinho, o teste passou a se chamar `test_carrinho_nao_cria_pedidos_e_so_oferece_link_para_finalizacao`: mantém todas as verificações de que operações do carrinho não criam pedidos nem alteram produtos e verifica que a finalização é oferecida apenas como link GET, sem formulário que crie pedido a partir do carrinho.

| Verificação executada | Resultado |
| --- | --- |
| `manage.py check` | Nenhum problema identificado. |
| `manage.py test principal.test_checkout` | 88 testes aprovados. |
| `manage.py test` | 233 testes aprovados: 145 anteriores e 88 da finalização. |
| `manage.py makemigrations --check --dry-run` | Nenhuma alteração detectada. |
| `manage.py migrate` (banco local) | Migrations 0002 a 0004 aplicadas. |
| `python -m pip check` | Nenhuma incompatibilidade de dependências. |
| `git diff --check` | Nenhum problema de espaços em branco. |

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test principal.test_checkout
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
```

## Decisões técnicas provisórias

**Não são regras de negócio aprovadas.**

| ID | Decisão adotada | Motivo |
| --- | --- | --- |
| T-701 | Revisão, endereço e confirmação na mesma página `/checkout/`. | Os valores e o bairro ficam visíveis antes de confirmar, com um único POST de finalização. |
| T-702 | Limite de R$ 5.000,00 inclusivo sobre o total, verificado somente no checkout. | Decisão operacional recebida, pendente do supervisor; o carrinho não foi alterado. |
| T-703 | Taxa `Decimal('0.00')` aceita como entrega explicitamente gratuita; `None` bloqueia. | D-002 distingue ausência de valor de gratuidade. |
| T-704 | Bairro comparado sem espaços repetidos e sem diferença de maiúsculas; acentos mantidos. | Normalização segura sem presumir equivalências de grafia. |
| T-705 | Implementada a proposta D-003: qualquer dado apresentado que mude exige nova confirmação. | Evita registrar dados ou valores diferentes dos apresentados. |
| T-706 | *Substituída nas correções finais:* nome, unidade e lista de bairros passaram a compor a revisão e exigem nova confirmação. | Auditoria complementar. |
| T-707 | A confirmação `/pedidos/<id>/confirmacao/` permanece acessível ao dono do pedido. | Necessária para o redirecionamento após o POST e para o reenvio idempotente; não há lista nem acompanhamento. |
| T-708 | Remoção explícita dos registros não identificados (resolve T-608). | Recuperação sem corrigir a sessão em GET. |
| T-709 | Chave de idempotência derivada de usuário e último pedido; compras simultâneas do mesmo usuário abertas antes de qualquer conclusão são uma única tentativa. | Efeito colateral autorizado: impede duplicidade sem migration; nova compra após reabrir o checkout. |
| T-710 | Após um erro de trava do banco, nova consulta da chave por até ~0,75 s antes de declarar falha. | Evita informar falha quando a outra transação está confirmando o mesmo pedido. |
| T-711 | Base sem pedido correspondente só é aceita se for o último pedido atual do usuário. | A assinatura não protege a base enquanto a `SECRET_KEY` for pública; reenvios legítimos continuam devolvendo o pedido registrado. |

## Pendências para o supervisor

1. **D-001:** lista de bairros atendidos. Sem ela, o checkout permanece bloqueado.
2. **D-002:** valor da taxa fixa, inclusive se a entrega gratuita é admitida.
3. **Limite de R$ 5.000,00:** aprovação, inclusão do valor exato e aplicação somente na finalização (T-702).
4. **D-003:** aprovação da reconfirmação implementada (T-705).
5. **D-004:** formatos de logradouro, número, endereço sem número, complemento e telefone; manter a origem `next` após o cadastro de uma nova conta, que hoje retorna ao login sem retomar o checkout.
6. **T-701, T-704, T-707, T-709, T-710 e T-711.**
7. **Produtos com preço R$ 0,00:** o limite monetário não restringe sua quantidade, que continua limitada apenas pelo limite técnico de `ItemPedido.quantidade`.
8. **SECRET_KEY de produção:** definir o fornecimento por variável de ambiente antes de qualquer implantação.
9. **D-007:** aprovação geral.
