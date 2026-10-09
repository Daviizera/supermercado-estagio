# Semana 2 — Escopo e requisitos

## Situação e limites

Especificação da primeira versão do sistema de pedidos online para supermercado com entrega. **Documento em revisão para validação pelo supervisor; os requisitos abaixo ainda não estão implementados.** A Semana 2 produz documentação. A aplicação continua com a página inicial da Semana 1.

O escopo solicitado abrange catálogo, identificação do cliente, carrinho da sessão, compra com entrega e pagamento na entrega, cadastro interno e processamento dos pedidos. Visitantes podem consultar o catálogo e montar um carrinho; concluir a compra exige identificação. Cliente é o usuário autenticado que compra; equipe é o integrante com permissão interna, nunca uma permissão obtida pelo cadastro público.

Não fazem parte desta versão: pagamento online, integração Pix/cartões/gateways, controle quantitativo de estoque, cupons, retirada no local, cálculo de frete por distância, rastreamento geográfico ou notificações em tempo real. Disponibilidade significa controle manual de produto ativo/inativo. Não há modelagem de tabelas, campos de banco ou novas rotas nesta entrega.

As regras detalhadas estão em [regras de negócio](regras-negocio.md); a navegação está no [fluxo de compra](fluxo-compra.md), no [fluxo dos pedidos](fluxo-pedidos.md) e nos [protótipos](prototipos.md). As decisões D-001 a D-007 ao final distinguem informações ausentes e propostas de interface do escopo solicitado.

## Requisitos funcionais

Prioridade **Essencial** significa necessária para o aceite da primeira versão, não para implementação nesta semana. A coluna de semana indica a implementação futura; os testes essenciais serão consolidados na Semana 9. Requisitos que atravessam etapas têm os marcos explicitados.

### Catálogo

| ID | Descrição | Ator | Prioridade | Critério de aceite verificável | Semana |
| --- | --- | --- | --- | --- | --- |
| RF-001 | Listar produtos disponíveis com nome, preço e unidade. | Visitante/cliente | Essencial | Um produto ativo aparece com os três dados; um produto inativo não aparece na listagem, busca ou filtro. | 5 |
| RF-002 | Filtrar o catálogo por categoria. | Visitante/cliente | Essencial | Ao escolher uma categoria, aparecem somente seus produtos ativos; sem resultados, é exibida uma mensagem. | 5 |
| RF-003 | Buscar produtos pelo nome. | Visitante/cliente | Essencial | Uma parte do nome encontra produtos ativos correspondentes, sem diferenciar maiúsculas de minúsculas; se houver categoria selecionada, ambos os critérios são aplicados. Busca vazia remove apenas o termo. | 5 |
| RF-004 | Consultar detalhes de um produto disponível. | Visitante/cliente | Essencial | A consulta mostra nome, categoria, preço e unidade; acesso direto a produto inativo ou inexistente não exibe seus detalhes nem permite adicioná-lo. | 5 |

### Identificação e acesso do cliente

| ID | Descrição | Ator | Prioridade | Critério de aceite verificável | Semana |
| --- | --- | --- | --- | --- | --- |
| RF-005 | Cadastrar uma conta de cliente. | Visitante | Essencial | Dados válidos criam uma conta sem permissões de equipe; identificador já utilizado ou dados inválidos impedem o cadastro e geram mensagem. Campos propostos dependem de D-004. | 4 |
| RF-006 | Entrar e sair da conta. | Visitante/cliente | Essencial | Credenciais válidas permitem entrada; inválidas geram erro. Login mantém o carrinho da sessão e permite retomar a finalização. Após logout, páginas privadas exigem nova identificação. | 4 |
| RF-007 | Exigir identificação para concluir a compra. | Visitante/cliente | Essencial | Visitante é encaminhado à identificação; enviar diretamente a confirmação sem sessão autenticada não cria pedido. | 4: identificação; 7: proteção da confirmação |
| RF-008 | Consultar a lista e os detalhes dos próprios pedidos. | Cliente | Essencial | A lista contém apenas pedidos do cliente; tentar acessar o identificador de outro cliente não revela dados do pedido. | 8 |

### Carrinho

| ID | Descrição | Ator | Prioridade | Critério de aceite verificável | Semana |
| --- | --- | --- | --- | --- | --- |
| RF-009 | Adicionar produto ativo ao carrinho da sessão. | Visitante/cliente | Essencial | A inclusão válida atualiza o carrinho somente da sessão atual; repetir o mesmo produto soma sua quantidade, mantendo uma linha por produto. | 6 |
| RF-010 | Alterar a quantidade de um item. | Visitante/cliente | Essencial | Inteiro positivo atualiza o item; zero, negativo, fração, texto ou campo vazio são rejeitados sem perder a quantidade anterior válida. | 6 |
| RF-011 | Remover itens do carrinho. | Visitante/cliente | Essencial | Remover elimina somente o item escolhido e recalcula o subtotal; remover o último item apresenta o carrinho vazio. | 6 |
| RF-012 | Exibir os valores dos itens e o subtotal calculado no servidor. | Visitante/cliente | Essencial | Cada linha mostra quantidade, preço unitário e valor da linha; subtotal equivale à soma dos valores das linhas, inclusive após alterações. Valores enviados pelo navegador não determinam o cálculo. | 6 |
| RF-013 | Revalidar o carrinho antes de concluir a compra. | Cliente/sistema | Essencial | Carrinho vazio, quantidade inválida ou produto indisponível impedem o registro; a validação se repete na confirmação, mesmo que a tela de revisão tenha sido aberta antes. | 7 |

### Entrega e finalização

| ID | Descrição | Ator | Prioridade | Critério de aceite verificável | Semana |
| --- | --- | --- | --- | --- | --- |
| RF-014 | Coletar endereço e telefone para a entrega. | Cliente | Essencial | Falta de endereço ou telefone impede avançar/concluir e identifica os campos a corrigir; dados válidos aparecem na revisão. Formato dos campos depende de D-004. | 7 |
| RF-015 | Selecionar somente bairro atendido. | Cliente | Essencial | A seleção oferece a lista configurada; bairro fora dela é rejeitado pelo servidor mesmo quando enviado manualmente. Sem lista definida, a compra não é liberada. | 7 |
| RF-016 | Exibir subtotal, taxa fixa de entrega e total antes da confirmação. | Cliente | Essencial | O resumo mostra separadamente os três valores e o total é subtotal mais a taxa configurada. Não há frete implícito nem valor inventado; D-001 e D-002 precisam estar resolvidas. | 7 |
| RF-017 | Informar e confirmar pagamento exclusivamente na entrega. | Cliente | Essencial | A revisão informa pagamento na entrega antes do botão de confirmar; não solicita dados financeiros nem inicia processamento externo. | 7 |
| RF-018 | Registrar integralmente o pedido confirmado. | Cliente/sistema | Essencial | Confirmação válida grava pedido e todos os itens vinculados ao cliente, com preços praticados, frete e totais preservados. Só após sucesso o carrinho é esvaziado. Em falha, não fica pedido parcial e o carrinho permanece. | 7 |

### Gerenciamento do supermercado

| ID | Descrição | Ator | Prioridade | Critério de aceite verificável | Semana |
| --- | --- | --- | --- | --- | --- |
| RF-019 | Cadastrar e manter categorias internamente. | Equipe autorizada | Essencial | A equipe pode cadastrar e editar uma categoria; visitante/cliente não pode fazê-lo. Uma categoria referenciada por produtos não pode ser excluída deixando-os sem categoria. | 3 |
| RF-020 | Cadastrar e manter produtos internamente. | Equipe autorizada | Essencial | Cadastro/edição exige nome, categoria, preço decimal e unidade; mudança no catálogo não altera valores de pedidos anteriores. Produtos referenciados por pedidos são preservados. | 3 |
| RF-021 | Controlar disponibilidade manual de produtos. | Equipe autorizada | Essencial | Ao inativar um produto, ele deixa de ser oferecido publicamente e não pode integrar uma nova compra, inclusive se já estiver no carrinho. | 3: controle; 5–7: aplicação pública |
| RF-022 | Separar permissões do cliente e da equipe. | Sistema/equipe autorizada | Essencial | Cadastro público não concede acesso interno; operações sobre categorias, produtos e pedidos verificam a permissão no servidor, inclusive em requisição direta. | 3: cadastro interno; 4: contas; 8: operação |
| RF-023 | Consultar os pedidos recebidos para atendimento. | Equipe autorizada | Essencial | Lista/detalhe mostram identificação, data, cliente, telefone, endereço/bairro, itens com quantidades/unidades, valores, pagamento na entrega e estado atual. | 8 |
| RF-024 | Atualizar estados e cancelar antes da saída para entrega. | Equipe autorizada | Essencial | Somente as transições da tabela de estados em regras-negocio.md são aceitas; tentativa inválida não altera o pedido. Cliente não pode executar a operação. | 8 |

### Confirmação e acompanhamento

| ID | Descrição | Ator | Prioridade | Critério de aceite verificável | Semana |
| --- | --- | --- | --- | --- | --- |
| RF-025 | Exibir confirmação do pedido registrado. | Cliente | Essencial | Após sucesso, o cliente vê identificação do pedido, itens, valores, entrega e estado inicial Recebido; erro de gravação nunca é apresentado como sucesso. | 7 |
| RF-026 | Exibir o estado atualizado ao cliente. | Cliente | Essencial | Após alteração pela equipe, ao abrir ou recarregar seu pedido, o cliente vê o novo estado, inclusive Cancelado. Não há atualização automática em tempo real. | 8 |

## Requisitos não funcionais

| ID | Tema e descrição | Ator responsável | Prioridade | Critério de aceite verificável | Semana |
| --- | --- | --- | --- | --- | --- |
| RNF-001 | Segurança das credenciais: utilizar a autenticação e o armazenamento de senhas do Django. | Desenvolvimento | Essencial | Senhas não aparecem em texto puro no banco, respostas ou registros de erro; credencial inválida não cria sessão autenticada. | 4; verificação 9 |
| RNF-002 | Controle de acesso no servidor, independente de botões visíveis. | Desenvolvimento | Essencial | Testes com visitante, cliente A, cliente B e equipe confirmam que A não lê pedido de B e que cliente não altera produtos/estados. | 3, 4, 7 e 8; verificação 9 |
| RNF-003 | Proteger operações de alteração contra requisições indevidas. | Desenvolvimento | Essencial | GET não altera dados; submissão de alteração sem proteção CSRF válida é rejeitada. | 3–8; verificação 9 |
| RNF-004 | Integridade financeira e gravação atômica do pedido. | Desenvolvimento | Essencial | Cálculos usam decimal no servidor; preços históricos permanecem; falha provocada na criação de um item não deixa pedido parcial nem esvazia o carrinho. | 3 e 7; verificação 9 |
| RNF-005 | Usabilidade de formulários e mensagens. | Desenvolvimento | Essencial | Campos têm rótulos, erros indicam a correção e preservam dados não sensíveis válidos; ações são utilizáveis por teclado e sucesso se distingue de falha. | 4–8; revisão 10 |
| RNF-006 | Responsividade das telas principais. | Desenvolvimento | Essencial | Em larguras de referência de 360, 768 e 1280 px, textos, campos e ações permanecem legíveis e utilizáveis, sem conteúdo essencial cortado nem rolagem horizontal da página. | 10 |
| RNF-007 | Manutenção simples e ambiente reproduzível. | Desenvolvimento | Essencial | Instalação limpa seguindo o README permite executar check, testes e aplicação; instruções e dependências acompanham mudanças, mantendo o monólito Django. | Contínuo, 3–12 |
| RNF-008 | Verificação das regras essenciais antes da entrega. | Desenvolvimento/supervisor | Essencial | Testes cobrem quantidades, totais, indisponibilidade, bairro inválido, permissões, transições e falha de registro; resultados são registrados para validação final. | 9; validação 11–12 |

## Rastreabilidade com o plano de estágio

| Semana | Entrega futura | Requisitos relacionados | Artefatos orientadores |
| --- | --- | --- | --- |
| 3 | Modelos e cadastro interno, sem antecipação nesta semana. | RF-019 a RF-022; base de integridade de RF-018 e RNF-004. | Regras de produtos, histórico e permissões. |
| 4 | Cadastro, login, logout e identificação. | RF-005 a RF-007, RF-022; RNF-001 a RNF-003. | Fluxo de compra e tela 3. |
| 5 | Catálogo público. | RF-001 a RF-004; aplicação de RF-021. | Fluxo de compra e tela 1. |
| 6 | Carrinho da sessão. | RF-009 a RF-012. | Fluxo de compra e tela 2. |
| 7 | Checkout e confirmação. | RF-007, RF-013 a RF-018, RF-025; RNF-004. | Fluxo de compra e telas 4, 5 e 6 (confirmação). |
| 8 | Operação e acompanhamento. | RF-008, RF-022 a RF-024, RF-026. | Fluxo de pedidos e telas 6 (consulta) e 7. |
| 9 | Testes essenciais. | RNF-008 e critérios de aceite dos RF/RNF. | Alternativas, cálculos, permissões e estados. |
| 10 | Responsividade e usabilidade. | RNF-005 e RNF-006. | Todas as telas prototipadas. |
| 11–12 | Validação, documentação e entrega. | Todos os requisitos e RNF-007/RNF-008. | README, decisões validadas e evidências de aceite. |

O cadastro interno da Semana 3 usará os mecanismos de acesso interno previstos no Django; os formulários públicos de identificação continuam previstos para a Semana 4. A interface interna concreta depende de D-006. Não há autorização para implementar qualquer dessas etapas agora.

## Decisões pendentes de validação

Todos os itens abaixo estão **pendentes**, sem valores ou aprovações presumidos. As referências entre documentos usam estes mesmos identificadores.

| ID | Decisão ou proposta | Responsável por validar | Onde será aplicada futuramente / prazo |
| --- | --- | --- | --- |
| D-001 | Definir a área de atendimento e a lista inequívoca de bairros aceitos. Não há bairros reais cadastrados ou assumidos. | Supermercado e supervisor | Configuração central de entrega do projeto, consultada pelo formulário e pelo servidor na Semana 7. Resolver antes de liberar checkout. |
| D-002 | Definir o valor fixo da entrega para todos os bairros atendidos. Ausência de valor não significa entrega gratuita. | Supermercado e supervisor | Mesma configuração central de entrega, usando valor decimal na Semana 7. Resolver antes de liberar checkout. |
| D-003 | Proposta: se preço ou frete mudar entre revisão e confirmação, reapresentar os valores atuais e exigir nova confirmação, preservando o carrinho. | Supervisor | Validação do checkout na Semana 7. Fluxo e protótipos representam esta proposta, ainda não aprovada. |
| D-004 | Validar campos e formatos de cadastro/login, endereço e telefone. Proposta dos esboços: usuário/senha; cadastro com confirmação da senha e retorno ao login; logradouro, número (ou indicação explícita de sem número), complemento opcional, bairro e telefone. | Supervisor e supermercado | Formulários das Semanas 4 e 7. Não se presume e-mail obrigatório nem formato definitivo de telefone. |
| D-005 | Fornecer identificação comercial, categorias, produtos, preços e unidades/embalagens vendidas. Quantidades desta versão serão inteiras; venda por peso variável não está especificada. | Supermercado | Cadastros da Semana 3 e conteúdo do catálogo da Semana 5. Nos esboços, usar somente marcadores. |
| D-006 | Validar a interface do cadastro interno e da operação: uso do Django Admin para cadastro é uma proposta; a tela operacional é conceitual e não determina ferramenta/layout. | Supervisor | Antes do cadastro interno na Semana 3 e do processamento de pedidos na Semana 8. |
| D-007 | Revisar e aprovar escopo, regras derivadas, critérios de aceite, protótipos e sequência do plano. A redação destes documentos não equivale a aprovação. | Supervisor e estudante | Revisão da Semana 2, antes de iniciar a modelagem da Semana 3. |

## Aceite dos artefatos da Semana 2

| Critério | Situação nesta entrega |
| --- | --- |
| Cinco documentos em português com escopo, regras, fluxos e esboços. | Concluído: arquivos presentes e links locais verificados. |
| RF/RNF identificados, com ator, prioridade, aceite e semana futura. | Concluído: 26 RF e 8 RNF nas tabelas, com IDs únicos e sequenciais. |
| Estados, permissões, fórmulas e tratamento de falhas coerentes. | Concluído: revisão conjunta das regras, fluxos e esboços, incluindo os seis estados e transições permitidas. |
| Protótipos ligados aos requisitos e decisões ausentes explicitadas. | Concluído: sete telas principais, três subvistas e matriz de rastreabilidade; nenhum dado comercial inventado. |
| Fundação da Semana 1 preservada e verificada. | Concluído: check sem problemas e 1 teste aprovado. Comparação SHA-256 confirmou código, configurações e SQLite intactos; o texto original do README foi preservado, com seção acrescentada. |
| Aprovação do supervisor e dados comerciais definitivos. | Pendente: D-001 a D-007. Não impede a entrega dos documentos para revisão. |
