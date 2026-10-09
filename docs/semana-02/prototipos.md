# Protótipos de baixa fidelidade — Semana 2

Estes esboços especificam interfaces futuras da primeira versão e estão em revisão. Não representam telas implementadas nem aprovação do supervisor. As referências `RF` correspondem a [requisitos.md](requisitos.md); cálculos e permissões seguem [regras-negocio.md](regras-negocio.md).

Os textos entre `<...>` são marcadores de conteúdo, inclusive nome comercial, produtos, preços, bairros e frete. Nenhum valor comercial ou bairro real foi definido. `[Ação]` representa um botão ou link; `[campo: ...]`, um campo de formulário. A disposição é ilustrativa e não estabelece o layout definitivo.

## Convenções comuns

- Visitantes podem consultar o catálogo e montar o carrinho da sessão. Finalizar exige login, preservando o carrinho durante a identificação.
- Quantidades são inteiros positivos. Disponibilidade significa produto ativo ou inativo, definida manualmente pela equipe; não há controle de estoque quantitativo nesta versão.
- Subtotal = soma(quantidade × preço unitário). Total = subtotal + taxa fixa de entrega. O servidor calcula os valores; a interface apenas os apresenta.
- A modalidade exibida é exclusivamente **pagamento na entrega**, sem seleção de meios ou processamento financeiro.
- Erros de validação indicam o campo ou item a corrigir e preservam o carrinho. Falha ao registrar o pedido não produz confirmação de sucesso nem esvazia o carrinho.
- O cliente consulta atualizações ao abrir ou recarregar o acompanhamento. Não está previsto acompanhamento em tempo real.
- Campos de cadastro e formatos de validação são propostas pendentes em D-004. A proposta de reapresentar valores alterados desde a revisão e exigir nova confirmação depende de D-003. Ambas constam em [requisitos.md](requisitos.md).

## Tela 1 — Catálogo

**Objetivo:** encontrar produtos ativos e consultar suas informações antes de adicioná-los ao carrinho.

**Ator:** visitante ou cliente.

**Requisitos:** RF-001, RF-002, RF-003, RF-004, RF-006 e RF-009.

```text
+-------------------------------------------------------------+
| <Nome do supermercado>                                       |
| [Início] [Catálogo] [Carrinho] [Entrar]                        |
| Autenticado: [Meus pedidos] [Sair] substituem [Entrar]         |
+-------------------------------------------------------------+
| Categorias: [Todas v]  Busca: [nome do produto____] [Buscar]   |
| [Limpar busca e categoria]                                   |
+-------------------------------------------------------------+
| <Produto ativo>                 <Preço> / <Unidade>           |
| [Detalhes] Quantidade: [<inteiro positivo>] [Adicionar]        |
|                                                             |
| <Outro produto ativo>           <Preço> / <Unidade>           |
| [Detalhes] Quantidade: [<inteiro positivo>] [Adicionar]        |
+-------------------------------------------------------------+
| <Mensagem de resultado ou validação>                         |
+-------------------------------------------------------------+
```

**Elementos e ações:** identificação comercial, navegação, categoria, busca por nome, nome/preço/unidade de cada produto, quantidade e inclusão no carrinho. Busca e categoria podem ser combinadas. Apenas itens ativos são listados.

**Mensagens previstas:** “Nenhum produto encontrado.”; “Informe uma quantidade inteira maior que zero.”; “Este produto não está disponível.”, caso seja desativado entre a consulta e a inclusão. A lista vazia é um resultado possível, não uma falha do sistema.

**Navegação:** a página inicial existente conduz futuramente ao catálogo; `[Carrinho]` abre a Tela 2; `[Entrar]` abre a Tela 3; `[Meus pedidos]` abre a subvista da Tela 6. `[Sair]` encerra a autenticação. A inclusão bem-sucedida informa que o item foi adicionado e mantém acesso ao carrinho.

### Subvista — Detalhes do produto

```text
+-------------------------------------------------------------+
| [Voltar ao catálogo]                         [Carrinho]      |
| <Nome do produto ativo>                                      |
| Categoria: <Categoria>                                      |
| <Descrição comercial, se fornecida — pendente D-005>          |
| Preço: <Preço> / <Unidade>                                   |
| Quantidade: [<inteiro positivo>] [Adicionar ao carrinho]      |
| <Mensagem de validação>                                     |
+-------------------------------------------------------------+
```

Mantém o mesmo ator, ações e validação de quantidade da Tela 1; corresponde a RF-004 e RF-009. Um produto inativo não exibe seus detalhes na área pública: apresenta indisponibilidade e acesso de volta ao catálogo. O conteúdo comercial da descrição depende de validação com o supermercado.

## Tela 2 — Carrinho

**Objetivo:** revisar os itens da sessão e ajustar a seleção antes do checkout.

**Ator:** visitante ou cliente.

**Requisitos:** RF-007, RF-009, RF-010, RF-011, RF-012 e RF-013.

```text
+-------------------------------------------------------------+
| Carrinho de compras                                         |
+-------------------------------------------------------------+
| Produto / unidade | Preço unitário | Quantidade | Valor item |
| <Produto/unidade> | <Preço>        | [<Qtd>]    | <Valor>    |
| [Atualizar quantidade] [Remover]                             |
| <Mensagem vinculada ao item, se houver>                      |
+-------------------------------------------------------------+
| Subtotal: <Subtotal calculado no servidor>                   |
| Taxa de entrega informada na etapa de endereço.              |
| [Continuar comprando]                   [Finalizar compra]   |
+-------------------------------------------------------------+
```

**Elementos e ações:** itens, unidade, preço unitário, quantidade editável, valor de cada item e subtotal. Atualizar recalcula os valores no servidor; remover exclui o item da sessão. Cada item indica claramente eventual indisponibilidade.

**Mensagens previstas:** “Seu carrinho está vazio.”, com acesso ao catálogo e sem prosseguir; “Informe uma quantidade inteira maior que zero.”; “Há produto indisponível no carrinho. Remova o item para continuar.” Quantidade zero não equivale a remoção: existe uma ação específica para remover. Uma alteração inválida não substitui a quantidade válida anterior.

**Navegação:** continuar comprando retorna à Tela 1. Finalizar exige carrinho não vazio e válido; visitante segue à Tela 3, mantendo os itens, e cliente autenticado segue à Tela 4. A disponibilidade será novamente validada antes da criação do pedido.

## Tela 3 — Identificação

**Objetivo:** identificar o cliente para permitir a finalização e o acesso aos próprios pedidos.

**Ator:** visitante ou cliente sem sessão autenticada.

**Requisitos:** RF-005, RF-006 e RF-007.

```text
+-------------------------------------------------------------+
| Identifique-se para continuar                               |
| Usuário: [____________________________]                      |
| Senha:   [____________________________]                      |
| <Mensagem de validação>                                     |
| [Entrar]                                                    |
| Ainda não possui conta? [Criar conta]                        |
| [Voltar ao carrinho]                                        |
+-------------------------------------------------------------+
| Seus itens permanecem no carrinho durante a identificação.  |
+-------------------------------------------------------------+
```

**Elementos e ações:** formulário de login por usuário e senha, mensagem de validação, entrada e acesso ao cadastro. A proposta dos campos será confirmada em D-004; não se presume e-mail obrigatório.

**Mensagens previstas:** “Informe usuário e senha.”; “Usuário ou senha inválidos.” A mensagem de credenciais inválidas não revela qual dos campos corresponde a uma conta existente.

**Navegação:** login originado no checkout continua na Tela 4 com o carrinho preservado. Login solicitado para consultar pedidos continua na Tela 6; uma entrada pelo catálogo retorna à Tela 1. O acesso restrito da equipe também depende de autenticação e autorização antes da Tela 7. Cadastro é uma subvista desta tela.

### Subvista — Cadastro de conta

```text
+-------------------------------------------------------------+
| Criar conta — proposta de campos pendente em D-004           |
| Usuário:         [___________________________]               |
| Senha:           [___________________________]               |
| Confirmar senha: [___________________________]               |
| <Mensagens junto aos campos>                                |
| [Cadastrar]                           [Voltar para entrar]   |
+-------------------------------------------------------------+
```

**Objetivo e ator:** permitir que o visitante crie uma conta; corresponde a RF-005. A proposta utiliza usuário, senha e confirmação de senha; a lista definitiva e os formatos dependem de D-004. Prevê mensagens de campo obrigatório, usuário já utilizado, senhas divergentes e senha que não atende aos critérios definidos. Na proposta pendente D-004, o cadastro retorna à identificação e só prossegue após autenticação, mantendo o carrinho; não conclui a compra. Não se adicionam recuperação de senha ou outros módulos a estes protótipos.

## Tela 4 — Endereço e entrega

**Objetivo:** coletar os dados necessários para a entrega e informar a taxa fixa.

**Ator:** cliente autenticado com carrinho válido.

**Requisitos:** RF-007, RF-014, RF-015 e RF-016.

```text
+-------------------------------------------------------------+
| Endereço e entrega                                          |
| Logradouro:  [________________________________]             |
| Número:      [________________________________]             |
| Complemento: [________________________________] (opcional)  |
| Bairro:      [<Selecione um bairro atendido> v]              |
| Telefone:    [________________________________]             |
| <Mensagem junto ao campo inválido>                          |
+-------------------------------------------------------------+
| Taxa fixa de entrega: <Valor ainda a definir>                |
| [Voltar ao carrinho]                  [Revisar pedido]       |
+-------------------------------------------------------------+
```

**Elementos e ações:** logradouro, número, complemento opcional, bairro selecionado da lista atendida e telefone. Salvar os dados desta etapa permite revisar a compra; isso não registra um pedido. Formatos e limites dos campos dependem de D-004. A taxa e a lista de bairros dependerão da configuração futura aprovada pelo supermercado.

**Mensagens previstas:** “Preencha este campo obrigatório.”; “Verifique o telefone informado.”, segundo o formato a validar; “Bairro não atendido. Selecione um bairro da lista.” Mesmo que a seleção apresente apenas bairros atendidos, o servidor deve rejeitar valores adulterados ou removidos da configuração. A ausência de bairros ou taxa configurados impede continuar e informa que a entrega ainda não está disponível, sem assumir frete zero.

**Navegação:** voltar abre a Tela 2; revisar abre a Tela 5 somente com dados válidos. Uma sessão expirada exige nova identificação na Tela 3. Erros mantêm o carrinho e os campos não sensíveis já informados para correção.

## Tela 5 — Revisão e confirmação

**Objetivo:** apresentar o pedido completo e obter a confirmação do cliente.

**Ator:** cliente autenticado com carrinho e entrega válidos.

**Requisitos:** RF-007, RF-013, RF-014, RF-015, RF-016, RF-017 e RF-018.

```text
+-------------------------------------------------------------+
| Revise seu pedido                                           |
| Produto / unidade | Quantidade | Preço unitário | Valor item |
| <Produto/unidade> | <Qtd>      | <Preço>        | <Valor>    |
+-------------------------------------------------------------+
| Entrega: <Logradouro>, <Número>, <Complemento se informado>  |
| Bairro: <Bairro atendido>  Telefone: <Telefone>              |
| [Alterar endereço] [Editar carrinho]                         |
+-------------------------------------------------------------+
| Subtotal: <Subtotal>                                         |
| Entrega:  <Taxa fixa de entrega>                             |
| Total:    <Subtotal + taxa fixa de entrega>                  |
| Pagamento: exclusivamente na entrega                        |
| Ao confirmar, você concorda com o pagamento na entrega.      |
| <Mensagem de validação ou falha>                             |
| [Confirmar pedido]                                          |
+-------------------------------------------------------------+
```

**Elementos e ações:** produtos, unidades, quantidades, preços unitários, valores de cada item, endereço, telefone, subtotal, frete e total. A modalidade de pagamento aparece antes da confirmação, sem integração ou seleção financeira. Editar carrinho ou endereço retorna à etapa correspondente; confirmar solicita a criação válida do pedido.

**Mensagens previstas:** carrinho vazio, quantidade inválida, produto indisponível, bairro não atendido, dados obrigatórios ausentes ou identificação necessária impedem a conclusão e apontam a etapa de correção. Uma falha na criação exibe “Não foi possível registrar o pedido. Seu carrinho foi mantido.” sem mostrar número de pedido ou sucesso.

**Revalidação:** o servidor confere autenticação, itens, disponibilidade, quantidades, entrega e cálculos ao confirmar. Se preço ou frete mudar desde a revisão, a **proposta D-003, pendente de aprovação**, é reapresentar os valores atualizados com a mensagem “Os valores foram atualizados. Confira antes de confirmar novamente.” O pedido não deve ser criado silenciosamente com os novos valores nessa proposta.

**Navegação:** editar carrinho abre a Tela 2; alterar endereço abre a Tela 4; autenticação necessária conduz à Tela 3. Sucesso na criação completa e atômica abre a Tela 6 e permite esvaziar o carrinho. Qualquer erro mantém os itens. Os preços e valores preservados no pedido correspondem à compra confirmada, não a consultas posteriores ao catálogo.

## Tela 6 — Confirmação e acompanhamento

**Objetivo:** comprovar o registro e permitir a consulta posterior do próprio pedido.

**Ator:** cliente autenticado, proprietário do pedido.

**Requisitos:** RF-008, RF-025 e RF-026.

```text
+-------------------------------------------------------------+
| Pedido registrado                                           |
| Pedido: <Identificador>                                     |
| Estado atual: Recebido                                      |
+-------------------------------------------------------------+
| <Produtos, unidades, quantidades e preços registrados>      |
| Subtotal: <Subtotal registrado>                             |
| Entrega:  <Taxa registrada>                                 |
| Total:    <Total registrado>                                |
| Destino:  <Endereço e bairro registrados>                    |
| Contato:  <Telefone registrado>                             |
| Pagamento: na entrega                                       |
+-------------------------------------------------------------+
| [Atualizar acompanhamento] [Meus pedidos] [Voltar ao catálogo]|
+-------------------------------------------------------------+
```

**Elementos e ações:** confirmação de sucesso apenas após registro válido, identificador, resumo com valores preservados, endereço, contato e estado atual. Na consulta posterior, o título passa a “Acompanhamento do pedido” e o estado apresenta o valor persistido naquele momento.

**Estados exibidos:** Recebido → Confirmado → Em preparo → Saiu para entrega → Entregue. Também pode ser exibido Cancelado, aplicado somente pela equipe nas condições da Tela 7. Entregue e Cancelado são terminais. O cliente não dispõe de ação para modificar o estado ou cancelar pedidos.

**Mensagens previstas:** “Pedido não encontrado ou acesso não permitido.”, sem revelar dados de terceiros; “Entre para consultar seus pedidos.” quando necessário; “Não foi possível atualizar o acompanhamento. Tente novamente.” em falha de consulta, sem afirmar um novo estado.

**Navegação:** atualizar recarrega a consulta; meus pedidos abre a subvista abaixo; voltar ao catálogo abre a Tela 1. Abrir ou recarregar a tela busca o estado atual no servidor; não há atualização automática em tempo real.

### Subvista — Meus pedidos

```text
+-------------------------------------------------------------+
| Meus pedidos                                                |
| Pedido          | Total registrado | Estado atual | Ação    |
| <Identificador> | <Total>          | <Estado>     | [Abrir] |
| <Identificador> | <Total>          | <Estado>     | [Abrir] |
| [Voltar ao catálogo]                                        |
+-------------------------------------------------------------+
```

O mesmo cliente autenticado consulta somente os próprios pedidos; corresponde a RF-008 e RF-026. `[Abrir]` apresenta o acompanhamento da Tela 6. Sem pedidos, exibe “Você ainda não possui pedidos.” e acesso ao catálogo. Falha de consulta informa o problema; uma lista de terceiros nunca é apresentada. Atualizar a página renova os estados exibidos.

## Tela 7 — Pedidos do supermercado

**Objetivo:** consultar pedidos e registrar cada etapa do atendimento.

**Ator:** integrante autenticado e autorizado da equipe.

**Requisitos:** RF-022, RF-023 e RF-024.

```text
+-------------------------------------------------------------+
| Pedidos do supermercado                                     |
| Pedido          | Cliente   | Bairro   | Total   | Estado   |
| <Identificador> | <Cliente> | <Bairro> | <Total> | <Estado> |
| [Consultar pedido]                                          |
+-------------------------------------------------------------+
| Pedido selecionado: <Identificador>                         |
| Data/hora: <Momento do registro>                             |
| Cliente: <Identificação>  Contato: <Telefone>                |
| Entrega: <Logradouro, número, complemento e bairro>          |
| <Itens: nome, unidade, quantidade, preço e valor registrado> |
| Subtotal: <Subtotal>  Entrega: <Taxa>  Total: <Total>         |
| Pagamento: na entrega                                       |
| Estado atual: Recebido                                      |
| [Confirmar pedido] [Cancelar pedido]                        |
| <Mensagem de operação ou validação>                         |
| [Voltar à lista]                                            |
+-------------------------------------------------------------+
```

**Elementos e ações:** lista dos pedidos recebidos, data/hora do registro, consulta detalhada de itens e quantidades para separação, valores registrados, identificação e telefone para contato, endereço para entrega, modalidade de pagamento e estado. As ações exibidas dependem do estado persistido; o exemplo mostra um pedido Recebido. A lista vazia informa “Nenhum pedido recebido.”

| Estado atual | Ação de avanço | Estado resultante | Cancelamento pela equipe |
| --- | --- | --- | --- |
| Recebido | Confirmar pedido | Confirmado | Permitido → Cancelado |
| Confirmado | Iniciar preparo | Em preparo | Permitido → Cancelado |
| Em preparo | Registrar saída para entrega | Saiu para entrega | Permitido → Cancelado |
| Saiu para entrega | Concluir entrega | Entregue | Bloqueado |
| Entregue | Nenhuma | Terminal | Bloqueado |
| Cancelado | Nenhuma | Terminal | Bloqueado |

**Mensagens previstas:** “Você não tem permissão para acessar esta área.”; “Esta alteração não é permitida para o estado atual.”; “O estado do pedido mudou. Atualize a consulta.”; “Não foi possível salvar a alteração.” O servidor verifica permissão e estado atual a cada operação; ocultar botões não substitui essa validação. Não são permitidos saltos, regressões, reabertura ou cancelamento após a saída para entrega.

**Navegação:** consultar abre os detalhes na mesma tela; voltar retorna à lista. Após alteração válida, a consulta apresenta o estado salvo. Visitantes passam pela identificação da Tela 3 antes da verificação de permissão; clientes sem permissão não acessam pedidos da equipe. O cliente proprietário vê a mudança ao abrir ou recarregar a Tela 6.

O cadastro interno de categorias, produtos e disponibilidade (RF-019 a RF-021) consta nos requisitos futuros, mas não recebe telas adicionais neste conjunto de protótipos.

## Rastreabilidade entre telas e requisitos

| Tela ou subvista | Requisitos correspondentes | Origem → destino |
| --- | --- | --- |
| 1 — Catálogo | RF-001, RF-002, RF-003, RF-004, RF-006, RF-009 | Página inicial / Telas 2 e 6 → detalhes, Telas 2, 3 e 6 |
| 1 — Detalhes do produto | RF-004, RF-009 | Catálogo → catálogo ou Tela 2 |
| 2 — Carrinho | RF-007, RF-009, RF-010, RF-011, RF-012, RF-013 | Telas 1, 4 e 5 → Telas 1, 3 ou 4 |
| 3 — Identificação | RF-005, RF-006, RF-007 | Catálogo, checkout ou acesso protegido → cadastro, Telas 1, 4, 6 ou 7, conforme origem e permissão |
| 3 — Cadastro | RF-005 | Identificação → identificação, preservando origem e carrinho (proposta pendente D-004) |
| 4 — Endereço e entrega | RF-007, RF-014, RF-015, RF-016 | Telas 2, 3 e 5 → Telas 2 e 5; Tela 3 se sessão expirar |
| 5 — Revisão e confirmação | RF-007, RF-013, RF-014, RF-015, RF-016, RF-017, RF-018 | Tela 4 → Telas 2 ou 4 para corrigir, Tela 3 para identificar, Tela 6 após sucesso |
| 6 — Confirmação e acompanhamento | RF-008, RF-025, RF-026 | Tela 5 / meus pedidos → meus pedidos ou Tela 1 |
| 6 — Meus pedidos | RF-008, RF-026 | Telas 1, 3 e 6 → acompanhamento ou Tela 1 |
| 7 — Pedidos do supermercado | RF-022, RF-023, RF-024 | Acesso da equipe autorizado → lista/detalhes; Tela 3 se identificação for necessária |

O planejamento por semana e as decisões pendentes estão consolidados em [requisitos.md](requisitos.md). As sequências de navegação e operação são detalhadas em [fluxo-compra.md](fluxo-compra.md) e [fluxo-pedidos.md](fluxo-pedidos.md). Nenhum destes esboços cria rotas, templates funcionais ou componentes de interface.
