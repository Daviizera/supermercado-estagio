# Semana 2 — Regras de negócio

Estas regras especificam o comportamento futuro da primeira versão; não representam funcionalidades implementadas. Estão em revisão com o supervisor, conforme D-007 em [requisitos](requisitos.md). As propostas que dependem de decisões adicionais são indicadas expressamente.

## Produtos e cadastro interno

| ID | Regra | Requisitos relacionados |
| --- | --- | --- |
| RN-001 | Todo produto tem nome, uma categoria e uma unidade de comercialização identificável pelo cliente. A equipe mantém esses dados. | RF-001, RF-004, RF-019, RF-020 |
| RN-002 | Preços e demais valores monetários usam representação decimal, com duas casas decimais, sem ponto flutuante binário nos cálculos. Preço e taxa não podem ser negativos. | RF-012, RF-016, RF-020; RNF-004 |
| RN-003 | Apenas produtos ativos aparecem na área pública ou podem ser adicionados/comprados. Inativo ou inexistente não é acessível por endereço direto de detalhes. A disponibilidade é manual; esta versão não controla quantidades em estoque. | RF-001 a RF-004, RF-009, RF-013, RF-021 |
| RN-004 | Manutenção não pode deixar produto sem categoria nem destruir o histórico de pedidos. Categoria com produtos e produto referenciado por pedido não são excluídos fisicamente; para retirar produto da oferta, a equipe o inativa. | RF-019 a RF-021, RF-018 |

## Carrinho e identificação

| ID | Regra | Requisitos relacionados |
| --- | --- | --- |
| RN-005 | O carrinho pertence à sessão atual, inclusive para visitante. Não há sincronização entre dispositivos nem carrinho persistente por conta nesta versão. Login durante a compra mantém o carrinho da sessão para retomar a finalização. | RF-006, RF-009 |
| RN-006 | Quantidade é inteiro positivo. Zero, negativo, fração, texto ou vazio são rejeitados; remover é uma ação explícita. Inclusões repetidas somam quantidades na mesma linha. A unidade exibida descreve o que uma quantidade representa; embalagens/unidades concretas dependem de D-005. | RF-009 a RF-011 |
| RN-007 | O servidor calcula valores das linhas e subtotal; o navegador não define preços, frete ou total. Alterar ou remover itens exige novo cálculo. | RF-012, RF-016 |
| RN-008 | A finalização exige carrinho não vazio e cliente autenticado. Na confirmação, o servidor revalida quantidades, produtos ativos, dados de entrega, bairro e valores, mesmo após uma revisão anterior válida. | RF-007, RF-013 a RF-018 |

## Entrega e pagamento

| ID | Regra | Requisitos relacionados |
| --- | --- | --- |
| RN-009 | Somente bairros da lista previamente definida pelo supermercado são aceitos. A lista será mantida na configuração central de entrega do projeto e utilizada tanto na seleção quanto na validação no servidor. Lista ausente ou bairro fora dela impede concluir. Conteúdo depende de D-001. | RF-015 |
| RN-010 | A entrega tem uma taxa fixa única para todos os bairros atendidos, representada como decimal na mesma configuração central. Valor definitivo depende de D-002; não existe valor padrão comercial presumido e taxa ausente bloqueia a conclusão. | RF-016 |
| RN-011 | Endereço e telefone de contato são obrigatórios. O cliente vê endereço, bairro, subtotal, taxa e total antes de confirmar. Campos e formatos concretos seguem a proposta pendente D-004. | RF-014 a RF-016 |
| RN-012 | O único pagamento previsto é na entrega, claramente informado na revisão. Não há integração com cartões, Pix, gateway ou pagamento online, coleta de dados financeiros ou processamento financeiro externo. Meios presenciais específicos não estão definidos. | RF-017 |

Nenhum bairro real ou valor definitivo de entrega é estabelecido neste documento. A configuração central será implementada na Semana 7; não há arquivos de configuração ou cadastros adicionais nesta semana.

## Cálculo e criação do pedido

```text
Valor da linha = quantidade × preço unitário
Subtotal = soma(quantidade × preço unitário)
Total = subtotal + taxa fixa de entrega
```

| ID | Regra | Requisitos relacionados |
| --- | --- | --- |
| RN-013 | Todos os componentes das fórmulas são calculados no servidor. Quantidades inteiras multiplicam preços com duas casas; frete fixo é acrescentado uma única vez por pedido. Carrinho vazio não pode gerar pedido, mesmo que exista taxa configurada. | RF-012, RF-013, RF-016 |
| RN-014 | Pedido registrado preserva quantidades, preços unitários praticados, identificação/unidade dos itens e valores de subtotal, taxa e total, além dos dados de contato/entrega usados na compra. Alterações posteriores no catálogo ou no frete não recalculam seu histórico. | RF-018, RF-023, RF-025 |
| RN-015 | Pedido e todos os seus itens são criados em uma única operação atômica. Só depois da criação válida o carrinho é esvaziado e a confirmação exibida. Falha desfaz a gravação parcial, mantém o carrinho e informa que a compra não foi concluída. | RF-018, RF-025; RNF-004 |
| RN-016 | **Proposta pendente D-003:** se preço ou frete mudar após a revisão, o servidor reapresenta os valores e exige nova confirmação. Enquanto isso, nenhum pedido é criado e o carrinho permanece. Uma nova confirmação volta a validar todos os dados. | RF-013, RF-016, RF-018 |

Não há edição de itens, endereço ou valores de um pedido após seu registro nesta versão. A operação prevista para a equipe é acompanhar e alterar o estado nas condições abaixo; o cliente apenas consulta. Mudanças no catálogo não corrigem nem reescrevem pedidos anteriores.

## Estados e transições

**RN-017 — Estado inicial:** um pedido criado com sucesso inicia em **Recebido**. Nenhum estado é usado para representar carrinho, formulário incompleto ou tentativa de compra que falhou. Relacionados: RF-018 e RF-025.

**RN-018 — Transições:** somente equipe autorizada pode executar as mudanças da tabela. Revalidar o estado atual no servidor ao receber a ação; uma tela antiga não autoriza uma transição que deixou de ser válida. Relacionados: RF-022 e RF-024.

| Estado atual | Próximo estado permitido | Condição operacional |
| --- | --- | --- |
| Recebido | Confirmado | Equipe confere os dados e aceita atender o pedido. |
| Confirmado | Em preparo | Equipe inicia a separação/preparação. |
| Em preparo | Saiu para entrega | Pedido preparado e encaminhado para entrega. |
| Saiu para entrega | Entregue | Equipe registra que a entrega foi concluída. |
| Recebido | Cancelado | Cancelamento solicitado pela equipe antes da saída. |
| Confirmado | Cancelado | Cancelamento solicitado pela equipe antes da saída. |
| Em preparo | Cancelado | Cancelamento solicitado pela equipe antes da saída. |
| Entregue | Nenhum | Estado terminal. |
| Cancelado | Nenhum | Estado terminal. |

**RN-019 — Bloqueios:** qualquer mudança não listada é proibida: pular etapas, retroceder, reabrir estados terminais ou cancelar após **Saiu para entrega**. Cliente não pode cancelar nem alterar estado diretamente. Ação rejeitada mantém o estado existente e apresenta mensagem. Não há outros estados nesta versão. Relacionado: RF-024.

**RN-020 — Visibilidade:** cliente consulta o estado persistido ao abrir ou recarregar seu pedido. Alterações da equipe, inclusive cancelamento, passam a aparecer nessa consulta. Não há notificações nem atualização em tempo real. Relacionados: RF-008 e RF-026. O [fluxo operacional](fluxo-pedidos.md) representa essas mesmas transições em diagrama.

## Permissões

**RN-021 — Acesso:** verificar identidade, propriedade do pedido e autorização da equipe no servidor, em cada consulta/operação. Ocultar um botão não é controle de acesso. Cadastro público cria somente conta de cliente. Relacionados: RF-005, RF-007, RF-008 e RF-022 a RF-026.

| Operação | Visitante | Cliente | Equipe autorizada |
| --- | --- | --- | --- |
| Consultar catálogo e usar carrinho da própria sessão | Permitido | Permitido | Mesmo acesso público, se utilizado. |
| Confirmar compra | Exige identificação | Permitido, com todas as validações | Se atuar como comprador, seguem as mesmas validações. |
| Consultar pedidos pela área do cliente | Exige identificação | Somente os próprios | Somente os próprios nessa área. |
| Manter categorias/produtos/disponibilidade | Negado | Negado | Permitido conforme permissão interna. |
| Consultar pedidos para atendimento e mudar estados | Negado | Negado | Permitido na área interna, respeitando transições. |

Visitante não conclui compra. Cliente não recebe dados de pedido de outro usuário, mesmo trocando seu identificador na requisição. Integrante da equipe sem a permissão exigida também não executa a operação interna. A modelagem e a atribuição concreta de permissões serão feitas nas semanas indicadas em [requisitos](requisitos.md).
