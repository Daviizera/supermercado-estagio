# Revisão da documentação técnica (Semana 12)

Este documento organiza a documentação do projeto e registra as divergências entre os documentos
semanais e o sistema efetivamente implementado. A revisão comparou cada documento com o código
atual e com os testes. A suíte de 418 testes foi executada com `DJANGO_ENV=development`.

**Critério adotado:**

- **Documentos históricos:** registros semanais (Semanas 2 a 9 e 11) descrevem o estado ao final
  de cada semana. Eles foram **preservados sem alteração**, e as afirmações superadas estão
  listadas na seção 3.
- **Documentos de estado atual:** o README e os documentos da Semana 12 descrevem o sistema como
  ele está e foram atualizados ou criados nesta revisão.
- **Exceção:** o documento da Semana 11 foi atualizado porque registra uma atividade ainda em
  andamento (a demonstração manual).

## 1. Índice dos documentos

| Documento | Papel | Situação |
|---|---|---|
| [README.md](../../README.md) | Visão geral, instalação resumida, verificação e histórico semanal | **Estado atual** (seções iniciais atualizadas nesta revisão) |
| [semana-02/requisitos.md](../semana-02/requisitos.md) | Escopo, RF/RNF, rastreabilidade e decisões D-001 a D-007 | Histórico (especificação original) |
| [semana-02/regras-negocio.md](../semana-02/regras-negocio.md) | Regras RN-001 a RN-021 | Histórico; regras implementadas (seção 2) |
| [semana-02/fluxo-compra.md](../semana-02/fluxo-compra.md) | Fluxo de compra do cliente | Histórico; fluxo implementado |
| [semana-02/fluxo-pedidos.md](../semana-02/fluxo-pedidos.md) | Estados e transições dos pedidos | Histórico; diagrama confere com o código |
| [semana-02/prototipos.md](../semana-02/prototipos.md) | Protótipos textuais das telas | Histórico; as telas reais estão nos manuais da Semana 12 |
| [semana-03/modelagem-dados.md](../semana-03/modelagem-dados.md) | Modelos, restrições e diagrama ER | Histórico; diagrama sem o campo da Semana 7 (seção 3) |
| [semana-04/autenticacao-clientes.md](../semana-04/autenticacao-clientes.md) | Cadastro, login e logout | Histórico; complementado na Semana 11 |
| [semana-05/catalogo-produtos.md](../semana-05/catalogo-produtos.md) | Catálogo, pesquisa e filtros | Histórico; limitação de acentos corrigida na Semana 11 |
| [semana-06/carrinho-compras.md](../semana-06/carrinho-compras.md) | Carrinho da sessão | Histórico; sem divergência funcional |
| [semana-07/finalizacao-compra.md](../semana-07/finalizacao-compra.md) | Checkout, idempotência e configuração de entrega | Histórico; configuração e chave secreta mudaram na Semana 11 |
| [semana-08/gerenciamento-pedidos.md](../semana-08/gerenciamento-pedidos.md) | Painel da equipe e acompanhamento | Histórico; sem divergência funcional |
| [semana-09/testes-correcao-falhas.md](../semana-09/testes-correcao-falhas.md) | Auditoria e correções da suíte | Histórico; contagens e avisos de implantação superados |
| [semana-11/validacao-testes-piloto.md](../semana-11/validacao-testes-piloto.md) | Dados demonstrativos, instalação limpa, testes-piloto e demonstração manual | Atualizado nesta revisão (seção 8.4) |
| [semana-12/manual-cliente.md](manual-cliente.md) | Uso do sistema pelo cliente | Estado atual (novo) |
| [semana-12/manual-equipe.md](manual-equipe.md) | Uso do gerenciamento pela equipe | Estado atual (novo) |
| [semana-12/manual-instalacao.md](manual-instalacao.md) | Instalação e execução em desenvolvimento | Estado atual (novo) |
| [semana-12/apresentacao-sistema.md](apresentacao-sistema.md) | Estrutura dos slides | Estado atual (novo) |

Não existe documento técnico próprio da Semana 10. O README resume essa semana e as alterações
de interface estão no código (`templates/` e `static/css/estilos.css`).

## 2. Requisitos e decisões da Semana 2 frente ao sistema atual

### 2.1. Requisitos

| Requisitos | Situação no código atual |
|---|---|
| RF-001 a RF-004 (catálogo) | Implementados. A pesquisa ignora maiúsculas e acentos desde a Semana 11. |
| RF-005 a RF-008 (identificação e pedidos do cliente) | Implementados. |
| RF-009 a RF-013 (carrinho) | Implementados. |
| RF-014 a RF-018 (entrega e finalização) | Implementados. Bairros e taxa usam valores demonstrativos somente em desenvolvimento. |
| RF-019 a RF-021 (cadastro interno) | Implementados pelo Django Admin (categorias e produtos). |
| RF-022 a RF-024 (operação da equipe) | Implementados no painel próprio **Gerenciamento de pedidos**. |
| RF-025 e RF-026 (confirmação e acompanhamento) | Implementados, sem atualização em tempo real. |
| RNF-001 a RNF-004 | Implementados e verificados por testes e pela auditoria de segurança da Semana 11. |
| RNF-005 e RNF-006 (usabilidade e responsividade) | Implementados na Semana 10, com medições em 360 a 1440 px. |
| RNF-007 (ambiente reproduzível) | Instalação limpa validada duas vezes (Semana 11) e passos do manual executados no PowerShell (Semana 12). |
| RNF-008 (verificação antes da entrega) | Suíte de 418 testes e testes-piloto. |

### 2.2. Decisões pendentes

| Decisão | Situação atual |
|---|---|
| D-001 e D-002 (bairros e taxa) | Resolvidas **apenas para a demonstração acadêmica**: "Bairro Ficticio de Teste" e R$ 5,00, somente com `DJANGO_ENV=development`. Na produção continuam pendentes, e o checkout permanece bloqueado. |
| D-003 (revalidação quando os valores mudam) | Implementada conforme a proposta. Aprovação formal não registrada nos documentos. |
| D-004 (campos e formatos) | Campos implementados conforme a proposta. Aprovação formal não registrada. |
| D-005 (dados comerciais) | Substituídos por dados fictícios de demonstração (`preparar_dados_demonstracao`). |
| D-006 (interface interna) | Django Admin para o catálogo; painel próprio para os pedidos. |
| D-007 (aprovação do escopo) | Aprovação formal do supervisor não registrada nos documentos. |

## 3. Divergências encontradas

| Documento e trecho | Afirmação no documento | Estado atual | Tratamento |
|---|---|---|---|
| README, instalação e execução | `migrate` e `runserver` sem configuração de ambiente | Sem `DJANGO_ENV` os comandos falham com `ImproperlyConfigured` | **Corrigido** no README |
| README, estrutura e configuração | "`DEBUG = True` e chave de desenvolvimento definida no projeto" | Ambientes separados por `DJANGO_ENV`; nenhuma chave no código | **Corrigido** no README |
| README, Semana 5 | Pesquisa sem remoção de acentos | Pesquisa e ordenação ignoram acentos (F-01/F-02) | Aviso de atualização acrescentado |
| README, Semana 7 | Bairros `()`, taxa `None`, checkout bloqueado; chave pública no repositório | Valores demonstrativos em desenvolvimento; produção bloqueada; chave fora do código | Aviso de atualização acrescentado |
| README, Semana 3 | `createsuperuser` para usar o cadastro interno | Continua válido para o Admin; a operação de pedidos usa conta da equipe com permissões específicas | Aviso de atualização acrescentado |
| semana-03/modelagem-dados.md, diagrama ER | `Pedido` sem `chave_idempotencia` | Campo `UUIDField` único acrescentado nas migrations 0002 a 0004 (Semana 7) | Registrado aqui; diagrama atualizado na apresentação |
| semana-05/catalogo-produtos.md | Pesquisa por `icontains`, com as limitações do SQLite para acentos | Pesquisa por texto normalizado (`principal/busca.py`) | Registrado aqui |
| semana-07/finalizacao-compra.md | "o checkout real permanece bloqueado"; `SECRET_KEY` literal em `settings.py` | Bloqueado apenas em produção; chave lida de `DJANGO_SECRET_KEY` ou do arquivo local | Registrado aqui |
| semana-04/autenticacao-clientes.md | Validadores padrão do Django; sem limite de tentativas | Senha com no mínimo 12 caracteres; limitação de tentativas no site e no Admin | Registrado aqui |
| semana-09/testes-correcao-falhas.md | 293 testes; avisos de `check --deploy` com a chave pública | 418 testes; produção sem esses avisos, salvo W005/W021 (HSTS) | Registrado aqui |
| semana-02/prototipos.md | Esboços textuais das telas | A interface real segue a identidade da Semana 10 | Registrado aqui; telas reais nos manuais |

Não foram encontradas divergências nas regras de estados e transições, nas permissões, no
carrinho, nos cálculos financeiros, na idempotência ou nas exclusões protegidas. O diagrama de
estados da Semana 2 confere com a tabela `TRANSICOES` de `principal/pedidos.py`.

## 4. Pendências documentais

- Publicar no repositório as alterações das Semanas 10 a 12, para que a clonagem descrita no
  manual de instalação obtenha esta versão.
- Registrar a aprovação do supervisor (D-007) e as decisões comerciais reais (D-001 e D-002),
  se o projeto vier a ser implantado.
- O relatório final de estágio será elaborado em etapa separada, após as orientações do
  professor; ele não faz parte desta revisão.
