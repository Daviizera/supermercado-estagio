import ast
import inspect
import threading
import uuid
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.messages import get_messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, OperationalError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from . import carrinho as carrinho_modulo
from . import checkout
from . import forms as forms_modulo
from . import models as models_modulo
from . import pedidos as pedidos_modulo
from . import views as views_modulo
from .carrinho import CHAVE_SESSAO
from .forms import EntregaForm
from .models import Categoria, EstadoPedido, ItemPedido, Pedido, Produto

# Valores fictícios usados somente pelos testes; não são dados comerciais.
BAIRRO_TESTE = 'Bairro Ficticio de Teste'
TAXA_TESTE = Decimal('5.00')
ENTREGA_TESTE = {
    'logradouro': 'Rua de teste', 'numero': '10', 'complemento': 'Bloco de teste',
    'bairro': BAIRRO_TESTE, 'telefone': 'telefone de teste',
}
configurado = override_settings(
    CHECKOUT_BAIRROS_ATENDIDOS=(BAIRRO_TESTE,), CHECKOUT_TAXA_ENTREGA=TAXA_TESTE,
)

MSG_INDISPONIVEL = checkout.CheckoutIndisponivel.mensagem
MSG_VALORES_ATUALIZADOS = checkout.RevisaoDesatualizada.mensagem
MSG_REVISAO_INVALIDA = checkout.RevisaoInvalida.mensagem
MSG_FALHA = checkout.FalhaAoRegistrar.mensagem


MODULOS_MONETARIOS = {
    'carrinho': carrinho_modulo, 'checkout': checkout, 'forms': forms_modulo,
    'models': models_modulo, 'pedidos': pedidos_modulo, 'views': views_modulo,
}
# Literais float aceitos somente nestas atribuições: espera em segundos, não valor monetário.
FLOAT_PERMITIDO_EM = frozenset({'ESPERA_INICIAL_APOS_TRAVA'})


def usos_de_float(fonte):
    """Lista (linha, descrição) dos usos de ponto flutuante binário em um código-fonte.

    Detecta chamadas a float(), conversões from_float, literais float e divisão verdadeira
    ('/'), que produz float entre inteiros. A atribuição direta de um literal às constantes
    de FLOAT_PERMITIDO_EM é aceita; qualquer chamada dentro dela continua sendo apontada.
    """
    arvore = ast.parse(fonte)
    literais_permitidos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and isinstance(no.value, ast.Constant) and any(
            isinstance(alvo, ast.Name) and alvo.id in FLOAT_PERMITIDO_EM for alvo in no.targets
        ):
            literais_permitidos.add(id(no.value))
    achados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            funcao = no.func
            if isinstance(funcao, ast.Name) and funcao.id == 'float':
                achados.append((no.lineno, 'float()'))
            elif isinstance(funcao, ast.Attribute) and funcao.attr in ('from_float', 'create_decimal_from_float'):
                achados.append((no.lineno, f'{funcao.attr}()'))
        elif isinstance(no, ast.Constant) and isinstance(no.value, float) and id(no) not in literais_permitidos:
            achados.append((no.lineno, f'literal float {no.value!r}'))
        elif isinstance(no, ast.BinOp) and isinstance(no.op, ast.Div):
            achados.append((no.lineno, 'divisão verdadeira'))
    return sorted(achados)


def fechar_conexoes_da_thread():
    """Fecha as conexões abertas pela thread de teste atual, na própria thread.

    No banco de testes SQLite em memória, o close() do Django é ignorado para não apagar o
    banco; a conexão crua desta thread é então fechada diretamente. As conexões do Django são
    locais a cada thread, e o banco compartilhado continua aberto pela thread principal.
    """
    if threading.current_thread() is threading.main_thread():
        raise RuntimeError('A conexão da thread principal não deve ser fechada.')
    for conexao in connections.all(initialized_only=True):
        if conexao.connection is not None:
            conexao.connection.close()
            conexao.connection = None


class _Combinados:
    """Aplica vários patches como um único gerenciador de contexto."""

    def __init__(self, *patches):
        self.patches = patches

    def __enter__(self):
        return [patch.__enter__() for patch in self.patches]

    def __exit__(self, *erro):
        for patch in reversed(self.patches):
            patch.__exit__(*erro)
        return False


class CheckoutBase(TestCase):
    senha = 'Chuva!Telhado42Mar'

    @classmethod
    def setUpTestData(cls):
        cls.categoria = Categoria.objects.create(nome='Mercearia checkout de teste')
        cls.arroz = Produto.objects.create(
            categoria=cls.categoria, nome='Arroz checkout de teste',
            preco=Decimal('12.50'), unidade='pacote de teste',
        )
        cls.leite = Produto.objects.create(
            categoria=cls.categoria, nome='Leite checkout de teste',
            preco=Decimal('6.70'), unidade='caixa de teste',
        )
        usuarios = get_user_model().objects
        cls.cliente = usuarios.create_user(username='cliente_checkout_testes', password=cls.senha)
        cls.outro_cliente = usuarios.create_user(
            username='outro_cliente_checkout_testes', password=cls.senha,
        )

    def setUp(self):
        self.client.force_login(self.cliente)

    def preencher(self, *itens, cliente=None):
        sessao = (cliente or self.client).session
        sessao[CHAVE_SESSAO] = {str(produto.pk): quantidade for produto, quantidade in itens}
        sessao.save()

    def gravar_carrinho(self, valor, cliente=None):
        sessao = (cliente or self.client).session
        sessao[CHAVE_SESSAO] = valor
        sessao.save()

    def itens_sessao(self, cliente=None):
        return (cliente or self.client).session.get(CHAVE_SESSAO)

    def revisar(self, cliente=None):
        resposta = (cliente or self.client).get(reverse('principal:checkout'))
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'principal/checkout.html')
        return resposta

    def token(self, cliente=None):
        token = self.revisar(cliente).context['token']
        self.assertTrue(token)
        return token

    def confirmar(self, token, cliente=None, **alteracoes):
        dados = {**ENTREGA_TESTE, 'revisao': token, **alteracoes}
        return (cliente or self.client).post(reverse('principal:checkout'), dados)

    def chave_do_token(self, token):
        """Chave que o servidor deriva do token: usuário e base assinados, nunca uma chave."""
        dados = signing.loads(token, salt=checkout.SAL_REVISAO)
        usuario = get_user_model().objects.get(pk=dados['usuario'])
        return checkout.chave_da_tentativa(usuario, dados['base'])

    def mensagens(self, resposta):
        return [str(mensagem) for mensagem in get_messages(resposta.wsgi_request)]

    def assert_sem_pedido(self):
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(ItemPedido.objects.count(), 0)

    def assert_confirmado(self, resposta):
        pedido = Pedido.objects.get()
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        return pedido

    def criar_pedido_direto(self, cliente, chave):
        return Pedido.objects.create(
            cliente=cliente, chave_idempotencia=chave, logradouro='Rua anterior de teste',
            numero='1', bairro=BAIRRO_TESTE, telefone='telefone anterior de teste',
            subtotal=Decimal('1.00'), taxa_entrega=Decimal('0.00'), total=Decimal('1.00'),
        )


class ConfiguracaoCheckoutTests(CheckoutBase):

    def test_configuracao_padrao_nao_tem_dados_comerciais_e_bloqueia(self):
        self.assertEqual(tuple(settings.CHECKOUT_BAIRROS_ATENDIDOS), ())
        self.assertIsNone(settings.CHECKOUT_TAXA_ENTREGA)
        self.assertEqual(settings.CHECKOUT_VALOR_MAXIMO_PEDIDO, Decimal('5000.00'))
        self.preencher((self.arroz, 1))

        resposta = self.revisar()
        self.assertContains(resposta, MSG_INDISPONIVEL)
        self.assertIsNone(resposta.context['token'])
        self.assertNotContains(resposta, 'name="revisao"')

    def test_checkout_bloqueado_sem_bairros_preserva_carrinho(self):
        self.preencher((self.arroz, 2))
        with configurado:
            token = self.token()
        with override_settings(CHECKOUT_BAIRROS_ATENDIDOS=(), CHECKOUT_TAXA_ENTREGA=TAXA_TESTE):
            self.assertContains(self.revisar(), MSG_INDISPONIVEL)
            resposta = self.confirmar(token)
        self.assertContains(resposta, MSG_INDISPONIVEL)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_checkout_bloqueado_sem_taxa_preserva_carrinho(self):
        self.preencher((self.arroz, 2))
        with configurado:
            token = self.token()
        with override_settings(CHECKOUT_BAIRROS_ATENDIDOS=(BAIRRO_TESTE,), CHECKOUT_TAXA_ENTREGA=None):
            self.assertContains(self.revisar(), MSG_INDISPONIVEL)
            resposta = self.confirmar(token)
        self.assertContains(resposta, MSG_INDISPONIVEL)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    @override_settings(CHECKOUT_BAIRROS_ATENDIDOS=(BAIRRO_TESTE,), CHECKOUT_TAXA_ENTREGA=Decimal('0.00'))
    def test_taxa_explicitamente_zero_e_aceita(self):
        self.preencher((self.arroz, 2))
        pedido = self.assert_confirmado(self.confirmar(self.token()))

        self.assertEqual(pedido.taxa_entrega, Decimal('0.00'))
        self.assertEqual(pedido.total, pedido.subtotal)
        self.assertEqual(pedido.total, Decimal('25.00'))

    def test_configuracoes_invalidas_bloqueiam_o_checkout(self):
        invalidas = [
            {'CHECKOUT_TAXA_ENTREGA': valor} for valor in (
                5, 5.0, '5.00', True, Decimal('5.005'), Decimal('-0.01'), Decimal('NaN'),
                Decimal('Infinity'), Decimal('1E+20'),
            )
        ] + [
            {'CHECKOUT_BAIRROS_ATENDIDOS': valor} for valor in (
                BAIRRO_TESTE, None, [123], ['   '], ['x' * 101],
            )
        ] + [
            {'CHECKOUT_VALOR_MAXIMO_PEDIDO': valor} for valor in (
                None, 5000, 5000.0, Decimal('0.00'), Decimal('-1.00'), Decimal('5000.001'),
                Decimal('99999999999.99'),
            )
        ]
        for alteracao in invalidas:
            with self.subTest(alteracao=alteracao):
                base = {
                    'CHECKOUT_BAIRROS_ATENDIDOS': (BAIRRO_TESTE,), 'CHECKOUT_TAXA_ENTREGA': TAXA_TESTE,
                    'CHECKOUT_VALOR_MAXIMO_PEDIDO': Decimal('5000.00'),
                }
                with override_settings(**{**base, **alteracao}):
                    with self.assertRaises(checkout.CheckoutIndisponivel):
                        checkout.obter_configuracao()

    def test_configuracao_normaliza_sem_arredondar(self):
        with override_settings(
            CHECKOUT_BAIRROS_ATENDIDOS=['  Bairro   Ficticio de Teste ', 'bairro ficticio de teste'],
            CHECKOUT_TAXA_ENTREGA=Decimal('5.000'),
        ):
            configuracao = checkout.obter_configuracao()
        # Zeros extras não mudam o valor; nomes repetidos após normalização são unificados.
        self.assertEqual(configuracao.taxa_entrega, Decimal('5.00'))
        self.assertEqual(configuracao.taxa_entrega.as_tuple().exponent, -2)
        self.assertEqual(configuracao.bairros, (BAIRRO_TESTE,))
        self.assertEqual(configuracao.valor_maximo, settings.CHECKOUT_VALOR_MAXIMO_PEDIDO)


@configurado
class EnderecoCheckoutTests(CheckoutBase):

    def setUp(self):
        super().setUp()
        self.preencher((self.arroz, 2))

    def test_endereco_valido_e_gravado_sem_espacos_externos(self):
        resposta = self.confirmar(
            self.token(), logradouro='  Rua de teste  ', complemento='', telefone=' telefone de teste ',
        )
        pedido = self.assert_confirmado(resposta)

        self.assertEqual(pedido.logradouro, 'Rua de teste')
        self.assertEqual(pedido.numero, '10')
        self.assertEqual(pedido.complemento, '')
        self.assertEqual(pedido.bairro, BAIRRO_TESTE)
        self.assertEqual(pedido.telefone, 'telefone de teste')

    def test_bairro_com_espacos_e_capitalizacao_diferentes_e_normalizado(self):
        pedido = self.assert_confirmado(
            self.confirmar(self.token(), bairro='  bairro   FICTICIO de teste '),
        )
        self.assertEqual(pedido.bairro, BAIRRO_TESTE)

    def test_bairro_nao_atendido_e_recusado(self):
        for bairro in ('Outro bairro de teste', 'Bairro Ficticio', 'Bairro Fictício de Teste'):
            with self.subTest(bairro=bairro):
                resposta = self.confirmar(self.token(), bairro=bairro)
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, checkout.MENSAGEM_BAIRRO_NAO_ATENDIDO)
                self.assert_sem_pedido()
                self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_campos_obrigatorios(self):
        for campo in ('logradouro', 'numero', 'bairro', 'telefone'):
            for valor in ('', '   '):
                with self.subTest(campo=campo, valor=valor):
                    resposta = self.confirmar(self.token(), **{campo: valor})
                    self.assertEqual(resposta.status_code, 200)
                    self.assertContains(resposta, checkout.MENSAGEM_CAMPO_OBRIGATORIO)
                    self.assert_sem_pedido()
                    self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_campos_acima_do_tamanho_maximo(self):
        for campo in ('logradouro', 'numero', 'complemento', 'bairro', 'telefone'):
            maximo = Pedido._meta.get_field(campo).max_length
            with self.subTest(campo=campo, maximo=maximo):
                resposta = self.confirmar(self.token(), **{campo: 'x' * (maximo + 1)})
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context['form'].errors[campo])
                self.assert_sem_pedido()

    def test_campos_no_tamanho_maximo_sao_aceitos(self):
        dados = {
            campo: 'x' * Pedido._meta.get_field(campo).max_length
            for campo in ('logradouro', 'numero', 'complemento', 'telefone')
        }
        pedido = self.assert_confirmado(self.confirmar(self.token(), **dados))
        for campo, valor in dados.items():
            self.assertEqual(getattr(pedido, campo), valor)

    def test_servico_valida_entrega_sem_formulario(self):
        configuracao = checkout.obter_configuracao()
        with self.assertRaises(checkout.EntregaInvalida) as contexto:
            checkout.validar_entrega({'logradouro': 5, 'bairro': 'Outro bairro'}, configuracao)
        self.assertEqual(
            set(contexto.exception.erros), {'logradouro', 'numero', 'bairro', 'telefone'},
        )
        limpos = checkout.validar_entrega(
            {**ENTREGA_TESTE, 'bairro': 'BAIRRO FICTICIO DE TESTE'}, configuracao,
        )
        self.assertEqual(limpos['bairro'], BAIRRO_TESTE)

    def test_formulario_lista_somente_bairros_configurados(self):
        resposta = self.revisar()
        self.assertContains(resposta, f'<option value="{BAIRRO_TESTE}">{BAIRRO_TESTE}</option>', html=True)
        self.assertContains(resposta, 'name="logradouro"')
        self.assertContains(resposta, 'Pagamento: exclusivamente na entrega.')
        self.assertFalse(EntregaForm(ENTREGA_TESTE).is_valid())


@configurado
class ValoresCheckoutTests(CheckoutBase):

    def produto_com_preco(self, preco):
        return Produto.objects.create(
            categoria=self.categoria, nome='Produto de limite de teste', preco=preco,
            unidade='unidade de teste',
        )

    def test_subtotal_taxa_e_total_corretos_em_decimal(self):
        self.preencher((self.arroz, 2), (self.leite, 1))
        resposta = self.revisar()
        revisao = resposta.context['revisao']

        self.assertEqual(revisao.subtotal, Decimal('31.70'))
        self.assertEqual(revisao.taxa_entrega, TAXA_TESTE)
        self.assertEqual(revisao.total, Decimal('36.70'))
        for texto in ('R$ 25,00', 'R$ 6,70', 'R$ 31,70', 'R$ 5,00', 'R$ 36,70'):
            self.assertContains(resposta, texto)

        pedido = self.assert_confirmado(self.confirmar(resposta.context['token']))
        for valor, esperado in (
            (pedido.subtotal, Decimal('31.70')), (pedido.taxa_entrega, Decimal('5.00')),
            (pedido.total, Decimal('36.70')),
        ):
            self.assertIsInstance(valor, Decimal)
            self.assertEqual(valor, esperado)

    def test_total_exatamente_no_limite_e_aceito(self):
        limite = settings.CHECKOUT_VALOR_MAXIMO_PEDIDO
        produto = self.produto_com_preco(limite - TAXA_TESTE)
        self.preencher((produto, 1))

        pedido = self.assert_confirmado(self.confirmar(self.token()))
        self.assertEqual(pedido.total, limite)

    def test_total_um_centavo_acima_do_limite_e_recusado(self):
        limite = settings.CHECKOUT_VALOR_MAXIMO_PEDIDO
        produto = self.produto_com_preco(limite - TAXA_TESTE + Decimal('0.01'))
        self.preencher((produto, 1))
        resposta = self.revisar()

        self.assertTrue(resposta.context['revisao'].excede_limite)
        self.assertContains(resposta, 'ultrapassa o limite de R$ 5000,00')
        self.assertNotContains(resposta, 'Confirmar pedido')
        resposta = self.confirmar(resposta.context['token'])
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'ultrapassa o limite')
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(produto.pk): 1})

    def test_subtotal_acima_do_limite_e_recusado(self):
        produto = self.produto_com_preco(settings.CHECKOUT_VALOR_MAXIMO_PEDIDO + Decimal('1.00'))
        self.preencher((produto, 1))
        resposta = self.confirmar(self.revisar().context['token'])

        self.assertContains(resposta, 'ultrapassa o limite')
        self.assert_sem_pedido()

    def test_limite_vem_exclusivamente_da_configuracao(self):
        self.preencher((self.arroz, 2), (self.leite, 1))
        with override_settings(CHECKOUT_VALOR_MAXIMO_PEDIDO=Decimal('36.70')):
            self.assert_confirmado(self.confirmar(self.token()))
        self.preencher((self.arroz, 2), (self.leite, 1))
        with override_settings(CHECKOUT_VALOR_MAXIMO_PEDIDO=Decimal('36.69')):
            resposta = self.confirmar(self.token())
        self.assertContains(resposta, 'ultrapassa o limite de R$ 36,69')
        self.assertEqual(Pedido.objects.count(), 1)

    def test_limite_nao_esta_duplicado_no_codigo(self):
        for modulo in ('checkout', 'views', 'forms', 'carrinho', 'models'):
            fonte = inspect.getsource(__import__(f'principal.{modulo}', fromlist=['x']))
            with self.subTest(modulo=modulo):
                self.assertNotIn('5000', fonte)
                self.assertNotIn('5.000', fonte)

    def test_calculos_nao_usam_float(self):
        self.assertNotRegex(inspect.getsource(checkout), r'\bfloat\s*\(')
        # Análise AST de todos os módulos que calculam, validam ou exibem valores.
        for nome, modulo in MODULOS_MONETARIOS.items():
            with self.subTest(modulo=nome):
                self.assertEqual(usos_de_float(inspect.getsource(modulo)), [])
        self.preencher((self.arroz, 3))
        revisao = self.revisar().context['revisao']
        for valor in (revisao.subtotal, revisao.taxa_entrega, revisao.total, revisao.linhas[0].valor):
            self.assertIs(type(valor), Decimal)
            self.assertEqual(valor.as_tuple().exponent, -2)
        conteudo = revisao.conteudo()
        self.assertEqual(
            conteudo['itens'],
            [[self.arroz.pk, self.arroz.nome, self.arroz.unidade, 3, '12.50', '37.50']],
        )
        self.assertEqual(
            (conteudo['subtotal'], conteudo['taxa_entrega'], conteudo['total']),
            ('37.50', '5.00', '42.50'),
        )
        self.assertEqual(conteudo['bairros'], [BAIRRO_TESTE])

    def test_analise_ast_detecta_float_injetado_e_aceita_a_espera_da_trava(self):
        fonte = inspect.getsource(checkout)
        # A constante de espera (segundos, não dinheiro) é o único literal float permitido.
        self.assertIn('ESPERA_INICIAL_APOS_TRAVA = 0.05', fonte)
        for injecao, esperado in (
            ('total = float(subtotal)', 'float()'),
            ('taxa = Decimal.from_float(taxa)', 'from_float()'),
            ('taxa = decimal.Context().create_decimal_from_float(taxa)', 'create_decimal_from_float()'),
            ('desconto = 0.1', 'literal float 0.1'),
            ('metade = subtotal / 2', 'divisão verdadeira'),
            # A exceção vale só para o literal atribuído diretamente à constante de espera.
            ('ESPERA_INICIAL_APOS_TRAVA = 0.05 * float(1)', ['float()', 'literal float 0.05']),
        ):
            with self.subTest(injecao=injecao):
                achados = usos_de_float(fonte + '\n' + injecao + '\n')
                esperados = esperado if isinstance(esperado, list) else [esperado]
                self.assertEqual(sorted(descricao for _, descricao in achados), sorted(esperados))

    def test_validacao_estrutural_ocorre_antes_de_salvar(self):
        self.preencher((self.arroz, 2))
        token = self.token()
        erro = ValidationError({'total': 'Valor fora da capacidade do campo.'})
        with mock.patch.object(Pedido, 'full_clean', side_effect=erro), \
                mock.patch.object(Pedido, 'save') as salvar:
            resposta = self.confirmar(token)
        salvar.assert_not_called()
        self.assertContains(resposta, MSG_FALHA)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})


@configurado
class ProdutosCheckoutTests(CheckoutBase):

    def test_carrinho_vazio_bloqueia_finalizacao(self):
        self.assertContains(self.revisar(), 'Seu carrinho está vazio.')
        self.preencher((self.arroz, 1))
        token = self.token()
        self.gravar_carrinho({})

        resposta = self.confirmar(token)
        self.assertContains(resposta, 'Seu carrinho está vazio.')
        self.assert_sem_pedido()

    def test_produto_inativo_bloqueia_pedido(self):
        self.preencher((self.arroz, 2), (self.leite, 1))
        token = self.token()
        Produto.objects.filter(pk=self.leite.pk).update(ativo=False)

        resposta = self.confirmar(token)
        self.assertContains(resposta, checkout.MENSAGEM_PRODUTO_INDISPONIVEL)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2, str(self.leite.pk): 1})
        self.assertContains(self.revisar(), checkout.MENSAGEM_PRODUTO_INDISPONIVEL)

    def test_produto_excluido_bloqueia_pedido(self):
        excluido = Produto.objects.create(
            categoria=self.categoria, nome='Produto excluido checkout de teste',
            preco=Decimal('3.00'), unidade='unidade de teste',
        )
        self.preencher((self.arroz, 1), (excluido, 1))
        token = self.token()
        excluido.delete()

        resposta = self.confirmar(token)
        self.assertContains(resposta, checkout.MENSAGEM_PRODUTO_INDISPONIVEL)
        self.assert_sem_pedido()

    def test_preco_alterado_exige_nova_confirmacao_com_valores_recalculados(self):
        self.preencher((self.arroz, 2))
        token = self.token()
        Produto.objects.filter(pk=self.arroz.pk).update(preco=Decimal('13.00'))

        resposta = self.confirmar(token)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, MSG_VALORES_ATUALIZADOS)
        self.assertContains(resposta, 'R$ 26,00')
        self.assert_sem_pedido()
        novo_token = resposta.context['token']
        # A reapresentação mantém a mesma tentativa de finalização.
        self.assertEqual(self.chave_do_token(novo_token), self.chave_do_token(token))

        pedido = self.assert_confirmado(self.confirmar(novo_token))
        self.assertEqual(pedido.subtotal, Decimal('26.00'))
        self.assertEqual(pedido.itens.get().preco_unitario, Decimal('13.00'))
        self.assertEqual(pedido.chave_idempotencia, self.chave_do_token(token))

    def test_carrinho_alterado_apos_revisao_exige_nova_confirmacao(self):
        self.preencher((self.arroz, 2))
        token = self.token()
        self.preencher((self.arroz, 3))
        self.assertContains(self.confirmar(token), MSG_VALORES_ATUALIZADOS)
        self.preencher((self.arroz, 3), (self.leite, 1))
        self.assertContains(self.confirmar(token), MSG_VALORES_ATUALIZADOS)
        self.assert_sem_pedido()

    def test_valores_enviados_pelo_navegador_sao_ignorados(self):
        self.preencher((self.arroz, 2))
        forjados = {
            campo: '0.01' for campo in ('preco', 'preco_unitario', 'subtotal', 'taxa_entrega', 'total')
        }
        resposta = self.confirmar(
            self.token(), cliente_id=self.outro_cliente.pk, estado='entregue', **forjados,
        )
        pedido = self.assert_confirmado(resposta)

        self.assertEqual(pedido.cliente, self.cliente)
        self.assertEqual(pedido.estado, EstadoPedido.RECEBIDO)
        self.assertEqual((pedido.subtotal, pedido.taxa_entrega, pedido.total),
                         (Decimal('25.00'), Decimal('5.00'), Decimal('30.00')))
        self.assertEqual(pedido.itens.get().preco_unitario, Decimal('12.50'))

    def test_entradas_malformadas_impedem_a_criacao(self):
        self.preencher((self.arroz, 2))
        token = self.token()
        for malformado in (
            {str(self.arroz.pk): 2, 'abc': 1},
            {str(self.arroz.pk): '2'},
            {str(self.arroz.pk): 2, '07': 1},
            'texto',
        ):
            with self.subTest(malformado=malformado):
                self.gravar_carrinho(malformado)
                resposta = self.confirmar(token)
                self.assertContains(resposta, checkout.MENSAGEM_CARRINHO_INCONSISTENTE)
                self.assert_sem_pedido()
                self.assertEqual(self.itens_sessao(), malformado)
                self.assertContains(self.revisar(), checkout.MENSAGEM_CARRINHO_INCONSISTENTE)


class RemocaoNaoIdentificadosTests(CheckoutBase):
    """T-608: ação explícita para registros sem produto identificável."""

    url = reverse('principal:remover_entradas_nao_identificadas')

    def test_remove_somente_registros_nao_identificados(self):
        self.gravar_carrinho({
            str(self.arroz.pk): 2, 'abc': 1, '07': 3, '-5': 1, '9' * 5000: 1,
            str(self.leite.pk): '3',
        })
        resposta = self.client.post(self.url)

        self.assertRedirects(resposta, reverse('principal:carrinho'))
        self.assertIn('4 registro(s) não identificado(s) removido(s) do carrinho.', self.mensagens(resposta))
        # O item com quantidade inconsistente é identificável e continua sujeito à remoção individual.
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2, str(self.leite.pk): '3'})

    def test_estrutura_que_nao_e_dicionario_e_substituida_por_carrinho_vazio(self):
        self.gravar_carrinho('texto')
        self.client.post(self.url)
        self.assertEqual(self.itens_sessao(), {})

    def test_sem_registros_invalidos_nada_e_alterado(self):
        self.preencher((self.arroz, 2))
        resposta = self.client.post(self.url)
        self.assertIn('Não há registros não identificados no carrinho.', self.mensagens(resposta))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_get_e_head_nao_removem_e_csrf_e_exigido(self):
        original = {str(self.arroz.pk): 2, 'abc': 1}
        self.gravar_carrinho(original)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.head(self.url).status_code, 405)
        self.assertContains(self.client.get(reverse('principal:carrinho')), 'Remover registros não identificados')
        self.assertEqual(self.itens_sessao(), original)

        cliente = Client(enforce_csrf_checks=True)
        self.gravar_carrinho(original, cliente=cliente)
        self.assertEqual(cliente.post(self.url).status_code, 403)
        self.assertEqual(self.itens_sessao(cliente), original)

    def test_visitante_tambem_pode_corrigir_o_proprio_carrinho(self):
        visitante = Client()
        self.gravar_carrinho({str(self.arroz.pk): 1, 'abc': 1}, cliente=visitante)
        visitante.post(self.url)
        self.assertEqual(self.itens_sessao(visitante), {str(self.arroz.pk): 1})

    def test_botao_aparece_somente_com_registros_nao_identificados(self):
        self.preencher((self.arroz, 1))
        self.assertNotContains(self.client.get(reverse('principal:carrinho')), self.url)


@configurado
class PersistenciaCheckoutTests(CheckoutBase):

    def test_pedido_e_itens_sao_criados_com_historico_e_estado_inicial(self):
        self.preencher((self.arroz, 2), (self.leite, 3))
        token = self.token()
        pedido = self.assert_confirmado(self.confirmar(token))

        self.assertEqual(pedido.cliente, self.cliente)
        self.assertEqual(pedido.chave_idempotencia, self.chave_do_token(token))
        self.assertEqual(pedido.estado, EstadoPedido.RECEBIDO)
        self.assertEqual(pedido.pagamento, 'na_entrega')
        self.assertEqual(pedido.subtotal, Decimal('45.10'))
        self.assertEqual(pedido.total, Decimal('50.10'))
        itens = list(pedido.itens.order_by('id'))
        self.assertEqual(
            [(i.produto_id, i.nome_produto, i.unidade, i.quantidade, i.preco_unitario) for i in itens],
            [
                (self.arroz.pk, self.arroz.nome, self.arroz.unidade, 2, Decimal('12.50')),
                (self.leite.pk, self.leite.nome, self.leite.unidade, 3, Decimal('6.70')),
            ],
        )
        self.assertEqual(sum(i.quantidade * i.preco_unitario for i in itens), pedido.subtotal)

    def test_historico_nao_muda_quando_produto_e_alterado(self):
        self.preencher((self.arroz, 2))
        pedido = self.assert_confirmado(self.confirmar(self.token()))
        Produto.objects.filter(pk=self.arroz.pk).update(
            nome='Nome alterado de teste', preco=Decimal('99.90'), unidade='outra unidade', ativo=False,
        )

        item = ItemPedido.objects.get(pedido=pedido)
        self.assertEqual(
            (item.nome_produto, item.unidade, item.preco_unitario),
            (self.arroz.nome, self.arroz.unidade, Decimal('12.50')),
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.total, Decimal('30.00'))
        resposta = self.client.get(reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertContains(resposta, self.arroz.nome)
        self.assertNotContains(resposta, 'Nome alterado de teste')

    def test_confirmacao_exibe_pedido_somente_ao_proprio_cliente(self):
        self.preencher((self.arroz, 2))
        pedido = self.assert_confirmado(self.confirmar(self.token()))
        url = reverse('principal:confirmacao_pedido', args=[pedido.pk])

        resposta = self.client.get(url)
        for texto in (
            'Pedido registrado', str(pedido.pk), 'Recebido', self.arroz.nome, 'R$ 25,00', 'R$ 30,00',
            'Rua de teste', BAIRRO_TESTE, 'telefone de teste', 'Na entrega',
        ):
            self.assertContains(resposta, texto)
        self.assertIn('no-cache', resposta['Cache-Control'])
        self.assertEqual(self.client.post(url).status_code, 405)

        outro = Client()
        outro.force_login(self.outro_cliente)
        negado = outro.get(url)
        self.assertEqual(negado.status_code, 404)
        self.assertNotContains(negado, 'Rua de teste', status_code=404)

        visitante = Client().get(url)
        self.assertRedirects(visitante, f"{reverse('principal:login')}?next={url}", fetch_redirect_response=False)

    def test_visitante_precisa_entrar_e_retorna_ao_checkout_com_carrinho(self):
        visitante = Client()
        self.preencher((self.arroz, 2), cliente=visitante)
        url = reverse('principal:checkout')
        destino_login = f"{reverse('principal:login')}?next={url}"

        self.assertRedirects(visitante.get(url), destino_login)
        self.assertRedirects(visitante.post(url, {**ENTREGA_TESTE, 'revisao': 'x'}), destino_login)
        self.assert_sem_pedido()

        login = visitante.post(
            destino_login, {'username': self.cliente.username, 'password': self.senha, 'next': url},
        )
        self.assertRedirects(login, url)
        self.assertEqual(self.itens_sessao(visitante), {str(self.arroz.pk): 2})
        self.assertIsNotNone(self.revisar(visitante).context['token'])

    def test_get_nao_altera_sessao_nem_cria_pedido(self):
        self.preencher((self.arroz, 2))
        antes = dict(self.client.session.items())
        self.revisar()
        self.client.head(reverse('principal:checkout'))

        self.assertEqual(dict(self.client.session.items()), antes)
        self.assert_sem_pedido()

    def test_metodos_nao_permitidos_e_csrf(self):
        url = reverse('principal:checkout')
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)

        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.cliente)
        self.preencher((self.arroz, 2), cliente=cliente)
        token = self.token(cliente)
        self.assertEqual(self.confirmar(token, cliente=cliente).status_code, 403)
        self.assert_sem_pedido()
        aceito = self.confirmar(token, cliente=cliente, csrfmiddlewaretoken=cliente.cookies['csrftoken'].value)
        self.assertEqual(aceito.status_code, 302)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_consultas_da_revisao_nao_crescem_com_mais_itens(self):
        self.preencher((self.arroz, 1))
        with CaptureQueriesContext(connection) as contexto:
            self.revisar()
        extras = Produto.objects.bulk_create([
            Produto(categoria=self.categoria, nome=f'Extra {i} de teste', preco=Decimal('1.00'), unidade='un')
            for i in range(5)
        ])
        self.preencher((self.arroz, 1), *[(produto, 1) for produto in extras])
        with self.assertNumQueries(len(contexto.captured_queries)):
            self.revisar()


@configurado
class TransacaoCheckoutTests(CheckoutBase):

    def setUp(self):
        super().setUp()
        self.preencher((self.arroz, 2), (self.leite, 1))
        self.carrinho_original = dict(self.itens_sessao())

    def assert_falha_preserva(self, resposta):
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, MSG_FALHA)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), self.carrinho_original)

    def test_erro_ao_salvar_pedido_gera_rollback(self):
        token = self.token()
        with mock.patch.object(Pedido, 'save', side_effect=DatabaseError('falha simulada')):
            self.assert_falha_preserva(self.confirmar(token))

    def test_erro_ao_salvar_segundo_item_gera_rollback_do_pedido_e_do_primeiro_item(self):
        token = self.token()
        salvar_original = ItemPedido.save
        chamadas = []

        def falhar_no_segundo(item, *args, **kwargs):
            chamadas.append(item)
            if len(chamadas) == 2:
                raise DatabaseError('falha simulada no segundo item')
            return salvar_original(item, *args, **kwargs)

        with mock.patch.object(ItemPedido, 'save', new=falhar_no_segundo):
            self.assert_falha_preserva(self.confirmar(token))
        self.assertEqual(len(chamadas), 2)

    def test_erro_de_validacao_do_item_desfaz_o_pedido(self):
        token = self.token()
        erro = ValidationError({'preco_unitario': 'Valor inválido.'})
        with mock.patch.object(ItemPedido, 'full_clean', side_effect=erro), \
                mock.patch.object(ItemPedido, 'save') as salvar_item:
            self.assert_falha_preserva(self.confirmar(token))
        salvar_item.assert_not_called()

    def test_apos_falha_a_mesma_tentativa_pode_ser_concluida(self):
        token = self.token()
        with mock.patch.object(Pedido, 'save', side_effect=DatabaseError('falha simulada')):
            self.confirmar(token)
        pedido = self.assert_confirmado(self.confirmar(token))
        self.assertEqual(pedido.chave_idempotencia, self.chave_do_token(token))
        self.assertEqual(pedido.itens.count(), 2)


@configurado
class IdempotenciaCheckoutTests(CheckoutBase):

    def test_reenvio_da_mesma_chave_nao_cria_outro_pedido_nem_apaga_carrinho_novo(self):
        self.preencher((self.arroz, 2))
        token = self.token()
        pedido = self.assert_confirmado(self.confirmar(token))
        self.assertIsNone(self.itens_sessao())

        self.preencher((self.leite, 4))
        resposta = self.confirmar(token)
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(ItemPedido.objects.count(), 1)
        self.assertEqual(self.itens_sessao(), {str(self.leite.pk): 4})

    def test_nova_compra_legitima_usa_outra_chave(self):
        # Páginas abertas antes da conclusão são a mesma tentativa; depois dela, outra chave.
        self.preencher((self.arroz, 1))
        primeiro_token = self.token()
        segundo_token = self.token()
        self.assertEqual(self.chave_do_token(primeiro_token), self.chave_do_token(segundo_token))

        primeiro = self.assert_confirmado(self.confirmar(primeiro_token))
        self.preencher((self.leite, 1))
        terceiro_token = self.token()
        self.assertNotEqual(self.chave_do_token(terceiro_token), primeiro.chave_idempotencia)
        resposta = self.confirmar(terceiro_token)
        segundo = Pedido.objects.exclude(pk=primeiro.pk).get()
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[segundo.pk]))
        self.assertNotEqual(primeiro.chave_idempotencia, segundo.chave_idempotencia)

    def test_chave_de_pedido_de_outro_cliente_nao_revela_dados(self):
        # A derivação inclui o usuário, então a colisão é impossível pelo token; o teste
        # força a derivação para exercitar a proteção defensiva.
        self.assertNotEqual(
            checkout.chave_da_tentativa(self.cliente, 0), checkout.chave_da_tentativa(self.outro_cliente, 0),
        )
        chave_alheia = uuid.uuid4()
        self.criar_pedido_direto(self.outro_cliente, chave_alheia)
        self.preencher((self.arroz, 2))
        token = self.token()

        with mock.patch.object(checkout, 'chave_da_tentativa', return_value=chave_alheia):
            resposta = self.confirmar(token)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, checkout.ChaveDeOutroCliente.mensagem)
        for texto in ('Rua anterior de teste', 'telefone anterior de teste', self.outro_cliente.username):
            self.assertNotContains(resposta, texto)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        # A nova revisão apresentada usa outra chave.
        self.assertNotEqual(self.chave_do_token(resposta.context['token']), chave_alheia)

    def test_token_emitido_para_outro_cliente_e_recusado(self):
        outro = Client()
        outro.force_login(self.outro_cliente)
        self.preencher((self.arroz, 1), cliente=outro)
        token_alheio = self.token(outro)
        self.preencher((self.arroz, 1))

        resposta = self.confirmar(token_alheio)
        self.assertContains(resposta, MSG_REVISAO_INVALIDA)
        self.assert_sem_pedido()

    def chave_existente_com_token(self):
        """Pedido já gravado com a chave da base 0 e um token emitido antes dele (base 0)."""
        base = checkout.pedido_base(self.cliente)
        existente = self.criar_pedido_direto(self.cliente, checkout.chave_da_tentativa(self.cliente, base))
        self.preencher((self.arroz, 2))
        revisao = self.revisar().context['revisao']
        return existente, checkout.assinar_revisao(revisao, base, self.cliente)

    def simular_consulta_previa_sem_pedido(self):
        """Simula uma requisição concorrente: as consultas prévias não veem o pedido.

        Enquanto o pedido da outra requisição não está visível, ele também não é o último
        pedido do usuário; por isso a base atual permanece 0 durante a simulação.
        """
        consultar = checkout._pedido_por_chave
        chamadas = []

        def consulta(chave):
            chamadas.append(chave)
            return None if len(chamadas) <= 2 else consultar(chave)

        consultas = mock.patch.object(checkout, '_pedido_por_chave', side_effect=consulta)
        base_anterior = mock.patch.object(checkout, 'pedido_base', return_value=0)
        return _Combinados(consultas, base_anterior)

    def test_conflito_detectado_na_validacao_devolve_pedido_existente(self):
        existente, token = self.chave_existente_com_token()
        with self.simular_consulta_previa_sem_pedido():
            resposta = self.confirmar(token)
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[existente.pk]))
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_restricao_do_banco_impede_duplicidade_mesmo_sem_validacao_previa(self):
        existente, token = self.chave_existente_com_token()
        with self.simular_consulta_previa_sem_pedido(), \
                mock.patch.object(Pedido, 'validate_unique', return_value=None):
            resposta = self.confirmar(token)
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[existente.pk]))
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(ItemPedido.objects.count(), 0)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_restricao_unica_esta_ativa_no_banco(self):
        chave = uuid.uuid4()
        self.criar_pedido_direto(self.cliente, chave)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.criar_pedido_direto(self.outro_cliente, chave)

        with connection.cursor() as cursor:
            restricoes = connection.introspection.get_constraints(cursor, Pedido._meta.db_table)
        self.assertTrue(any(
            info['unique'] and info['columns'] == ['chave_idempotencia'] for info in restricoes.values()
        ))
        campo = Pedido._meta.get_field('chave_idempotencia')
        self.assertFalse(campo.editable)
        self.assertTrue(campo.unique)

    def test_pedidos_sem_chave_informada_recebem_chaves_distintas(self):
        primeiro = self.criar_pedido_direto(self.cliente, uuid.uuid4())
        segundo = Pedido.objects.create(
            cliente=self.cliente, logradouro='Rua de teste', numero='1', bairro=BAIRRO_TESTE,
            telefone='telefone de teste', subtotal=Decimal('1.00'), taxa_entrega=Decimal('0.00'),
            total=Decimal('1.00'),
        )
        self.assertIsInstance(segundo.chave_idempotencia, uuid.UUID)
        self.assertNotEqual(primeiro.chave_idempotencia, segundo.chave_idempotencia)


@configurado
class RevisaoAssinadaTests(CheckoutBase):

    def setUp(self):
        super().setUp()
        self.preencher((self.arroz, 2))

    def assert_recusado(self, token):
        resposta = self.confirmar(token)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, MSG_REVISAO_INVALIDA)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_taxa_alterada_exige_nova_confirmacao(self):
        token = self.token()
        with override_settings(CHECKOUT_TAXA_ENTREGA=Decimal('6.00')):
            resposta = self.confirmar(token)
            self.assertContains(resposta, MSG_VALORES_ATUALIZADOS)
            self.assertContains(resposta, 'R$ 6,00')
            self.assert_sem_pedido()
            pedido = self.assert_confirmado(self.confirmar(resposta.context['token']))
        self.assertEqual(pedido.taxa_entrega, Decimal('6.00'))
        self.assertEqual(pedido.total, Decimal('31.00'))

    def test_token_adulterado_e_recusado(self):
        token = self.token()
        meio = len(token) // 2
        for adulterado in (
            token[:-1] + ('A' if token[-1] != 'A' else 'B'),
            token[:meio] + ('A' if token[meio] != 'A' else 'B') + token[meio + 1:],
        ):
            with self.subTest(adulterado=adulterado):
                self.assert_recusado(adulterado)

    def test_tokens_invalidos_nao_criam_pedido(self):
        valido = signing.loads(self.token(), salt=checkout.SAL_REVISAO)
        assinar = lambda dados, sal=checkout.SAL_REVISAO: signing.dumps(dados, salt=sal)  # noqa: E731
        sem_base = {campo: valor for campo, valor in valido.items() if campo != 'base'}
        for token in (
            '', 'abc', assinar(valido, sal='outro.sal'),
            assinar({**valido, 'base': 'texto'}),
            assinar({**valido, 'base': -1}),
            assinar({**valido, 'base': True}),
            assinar({**valido, 'base': 1.5}),
            assinar({**valido, 'base': None}),
            assinar(sem_base),
            assinar({**valido, 'usuario': self.outro_cliente.pk}),
            assinar({**valido, 'v': 1}),
            assinar({**valido, 'v': 99}),
            assinar({**valido, 'conteudo': 'texto'}),
            assinar(['lista']),
        ):
            with self.subTest(token=token[:40]):
                self.assert_recusado(token)
        resposta = self.client.post(reverse('principal:checkout'), ENTREGA_TESTE)
        self.assertContains(resposta, MSG_REVISAO_INVALIDA)
        self.assert_sem_pedido()

    def test_valores_forjados_em_token_assinado_nao_criam_pedido_com_eles(self):
        valido = signing.loads(self.token(), salt=checkout.SAL_REVISAO)
        valido['conteudo']['itens'][0][4] = '0.01'
        resposta = self.confirmar(signing.dumps(valido, salt=checkout.SAL_REVISAO))
        self.assertContains(resposta, MSG_VALORES_ATUALIZADOS)
        self.assert_sem_pedido()


@configurado
class SessaoCheckoutTests(CheckoutBase):

    def test_sucesso_remove_somente_o_carrinho_e_mantem_autenticacao(self):
        self.preencher((self.arroz, 2))
        sessao = self.client.session
        sessao['marcador_de_teste'] = 'preservado'
        sessao.save()

        resposta = self.confirmar(self.token())
        self.assert_confirmado(resposta)
        self.assertIn('Pedido registrado com sucesso.', self.mensagens(resposta))
        sessao = self.client.session
        self.assertNotIn(CHAVE_SESSAO, sessao)
        self.assertEqual(sessao['marcador_de_teste'], 'preservado')
        self.assertEqual(sessao[SESSION_KEY], str(self.cliente.pk))
        self.assertEqual(self.client.get(reverse('principal:minha_conta')).status_code, 200)
        self.assertContains(self.client.get(reverse('principal:carrinho')), 'Seu carrinho está vazio.')

    def test_logout_continua_limpando_o_carrinho(self):
        self.preencher((self.arroz, 2))
        self.client.post(reverse('principal:logout'))
        self.assertIsNone(self.itens_sessao())


@configurado
class RevisaoCompletaTests(CheckoutBase):
    """Correção A: tudo o que é apresentado compõe a revisão assinada (versão 2)."""

    def setUp(self):
        super().setUp()
        self.preencher((self.arroz, 2))

    def alterar_produto_e_confirmar(self, **alteracao):
        pagina = self.revisar()
        self.assertContains(pagina, self.arroz.nome)
        self.assertContains(pagina, self.arroz.unidade)
        Produto.objects.filter(pk=self.arroz.pk).update(**alteracao)
        resposta = self.confirmar(pagina.context['token'])
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, MSG_VALORES_ATUALIZADOS)
        for valor in alteracao.values():
            self.assertContains(resposta, valor)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        return resposta

    def test_nome_alterado_exige_reconfirmacao(self):
        self.alterar_produto_e_confirmar(nome='Arroz renomeado de teste')

    def test_unidade_alterada_exige_reconfirmacao(self):
        self.alterar_produto_e_confirmar(unidade='pacote novo de teste')

    def test_nome_e_unidade_alterados_exigem_reconfirmacao(self):
        self.alterar_produto_e_confirmar(nome='Arroz novo de teste', unidade='saco novo de teste')

    def test_nova_confirmacao_registra_os_dados_reapresentados(self):
        token_original = self.revisar().context['token']
        resposta = self.alterar_produto_e_confirmar(
            nome='Arroz renomeado de teste', unidade='pacote novo de teste',
        )
        novo_token = resposta.context['token']
        self.assertEqual(self.chave_do_token(novo_token), self.chave_do_token(token_original))
        apresentado = signing.loads(novo_token, salt=checkout.SAL_REVISAO)['conteudo']['itens'][0]

        pedido = self.assert_confirmado(self.confirmar(novo_token))
        item = pedido.itens.get()
        self.assertEqual(
            [item.produto_id, item.nome_produto, item.unidade, item.quantidade,
             str(item.preco_unitario), str(item.quantidade * item.preco_unitario)],
            apresentado,
        )
        self.assertEqual(item.nome_produto, 'Arroz renomeado de teste')

    def test_token_antigo_nao_registra_dados_que_nao_foram_apresentados(self):
        token_original = self.revisar().context['token']
        Produto.objects.filter(pk=self.arroz.pk).update(nome='Nome nunca apresentado')
        self.confirmar(token_original)
        self.confirmar(token_original)
        self.assert_sem_pedido()

    def test_lista_de_bairros_alterada_exige_nova_revisao(self):
        token = self.token()
        novos = (BAIRRO_TESTE, 'Outro Bairro de Teste')
        with override_settings(CHECKOUT_BAIRROS_ATENDIDOS=novos):
            resposta = self.confirmar(token)
            self.assertContains(resposta, MSG_VALORES_ATUALIZADOS)
            self.assertContains(resposta, '<option value="Outro Bairro de Teste">', html=False)
            self.assert_sem_pedido()
            pedido = self.assert_confirmado(self.confirmar(resposta.context['token']))
        self.assertEqual(pedido.bairro, BAIRRO_TESTE)

    def test_bairro_retirado_da_lista_e_recusado_com_revisao_atualizada(self):
        token = self.token()
        with override_settings(CHECKOUT_BAIRROS_ATENDIDOS=('Outro Bairro de Teste',)):
            resposta = self.confirmar(token)
        self.assertContains(resposta, checkout.MENSAGEM_BAIRRO_NAO_ATENDIDO)
        self.assertContains(resposta, MSG_VALORES_ATUALIZADOS)
        self.assert_sem_pedido()

    def test_conteudo_assinado_versao_2_contem_todos_os_dados_apresentados(self):
        dados = signing.loads(self.token(), salt=checkout.SAL_REVISAO)
        self.assertEqual(dados['v'], 2)
        self.assertEqual(dados['base'], 0)
        self.assertNotIn('chave', dados)
        self.assertEqual(dados['conteudo'], {
            'itens': [[self.arroz.pk, self.arroz.nome, self.arroz.unidade, 2, '12.50', '25.00']],
            'subtotal': '25.00', 'taxa_entrega': '5.00', 'total': '30.00', 'bairros': [BAIRRO_TESTE],
        })


@configurado
class IdempotenciaDeterministicaTests(CheckoutBase):
    """Correção B: chave derivada de usuário e último pedido, nunca aceita do navegador."""

    def test_derivacao_depende_somente_de_usuario_e_base(self):
        chave = checkout.chave_da_tentativa(self.cliente, 0)
        self.assertEqual(chave, checkout.chave_da_tentativa(self.cliente, 0))
        self.assertEqual(chave.version, 5)
        self.assertNotEqual(chave, checkout.chave_da_tentativa(self.cliente, 1))
        self.assertNotEqual(chave, checkout.chave_da_tentativa(self.outro_cliente, 0))

    def test_duas_paginas_da_mesma_sessao_geram_um_pedido(self):
        self.preencher((self.arroz, 2), (self.leite, 1))
        aba = Client()
        aba.cookies[settings.SESSION_COOKIE_NAME] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        token1, token2 = self.token(), self.token(aba)
        self.assertEqual(self.chave_do_token(token1), self.chave_do_token(token2))

        pedido = self.assert_confirmado(self.confirmar(token1))
        segunda = self.confirmar(token2, cliente=aba)
        self.assertRedirects(segunda, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertEqual((Pedido.objects.count(), ItemPedido.objects.count()), (1, 2))

    def test_segunda_sessao_do_mesmo_usuario_recebe_o_primeiro_pedido_e_mantem_o_carrinho(self):
        dispositivo = Client()
        dispositivo.force_login(self.cliente)
        self.preencher((self.arroz, 2))
        self.preencher((self.leite, 3), cliente=dispositivo)
        token1, token2 = self.token(), self.token(dispositivo)

        pedido = self.assert_confirmado(self.confirmar(token1))
        segunda = self.confirmar(token2, cliente=dispositivo)
        self.assertRedirects(segunda, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(self.itens_sessao(dispositivo), {str(self.leite.pk): 3})

        # Reabrindo o checkout após a conclusão, o segundo dispositivo compra normalmente.
        novo_token = self.token(dispositivo)
        self.assertNotEqual(self.chave_do_token(novo_token), pedido.chave_idempotencia)
        self.confirmar(novo_token, cliente=dispositivo)
        self.assertEqual(Pedido.objects.count(), 2)
        self.assertIsNone(self.itens_sessao(dispositivo))

    def test_chave_enviada_pelo_navegador_e_ignorada(self):
        alheio = self.criar_pedido_direto(self.outro_cliente, uuid.uuid4())
        self.preencher((self.arroz, 1))
        dados = signing.loads(self.token(), salt=checkout.SAL_REVISAO)
        token = signing.dumps(
            {**dados, 'chave': str(alheio.chave_idempotencia)}, salt=checkout.SAL_REVISAO, compress=True,
        )
        resposta = self.confirmar(
            token, chave=str(alheio.chave_idempotencia), chave_idempotencia=str(alheio.chave_idempotencia),
        )
        pedido = Pedido.objects.get(cliente=self.cliente)
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertEqual(pedido.chave_idempotencia, checkout.chave_da_tentativa(self.cliente, 0))

    def preparar_trava(self):
        """Pedido da tentativa já gravado por outra requisição; esta não o viu antes."""
        base = checkout.pedido_base(self.cliente)
        chave = checkout.chave_da_tentativa(self.cliente, base)
        self.preencher((self.leite, 3))
        revisao = self.revisar().context['revisao']
        token = checkout.assinar_revisao(revisao, base, self.cliente)
        return chave, token

    def consultas_que_falham(self, vezes):
        """As primeiras consultas não veem o pedido da outra transação, nem como último pedido."""
        consultar = checkout._pedido_por_chave
        chamadas = []

        def consulta(chave):
            chamadas.append(chave)
            return None if len(chamadas) <= vezes else consultar(chave)

        return chamadas, _Combinados(
            mock.patch.object(checkout, '_pedido_por_chave', side_effect=consulta),
            mock.patch.object(checkout, 'pedido_base', return_value=0),
        )

    def test_database_is_locked_com_pedido_ja_confirmado_devolve_a_confirmacao(self):
        chave, token = self.preparar_trava()
        existente = self.criar_pedido_direto(self.cliente, chave)
        trava = OperationalError('database is locked')
        chamadas, consultas = self.consultas_que_falham(2)
        with consultas, mock.patch.object(Pedido, 'validate_unique', return_value=None), \
                mock.patch.object(Pedido, 'save', side_effect=trava), \
                mock.patch.object(checkout.time, 'sleep') as dormir:
            resposta = self.confirmar(token)
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[existente.pk]))
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(self.itens_sessao(), {str(self.leite.pk): 3})
        self.assertNotIn(MSG_FALHA, self.mensagens(resposta))
        dormir.assert_not_called()

    def test_database_is_locked_aguarda_a_outra_transacao_confirmar(self):
        chave, token = self.preparar_trava()
        existente = self.criar_pedido_direto(self.cliente, chave)
        # Duas consultas prévias e duas após a trava ainda não enxergam o pedido.
        chamadas, consultas = self.consultas_que_falham(4)
        with consultas, mock.patch.object(Pedido, 'validate_unique', return_value=None), \
                mock.patch.object(Pedido, 'save', side_effect=OperationalError('database is locked')), \
                mock.patch.object(checkout.time, 'sleep') as dormir:
            resposta = self.confirmar(token)
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[existente.pk]))
        self.assertEqual(len(chamadas), 5)
        self.assertEqual([c.args[0] for c in dormir.call_args_list], [0.05, 0.1])

    def test_database_is_locked_sem_pedido_registrado_e_falha_real(self):
        chave, token = self.preparar_trava()
        with mock.patch.object(Pedido, 'save', side_effect=OperationalError('database is locked')), \
                mock.patch.object(checkout.time, 'sleep') as dormir:
            resposta = self.confirmar(token)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, MSG_FALHA)
        self.assert_sem_pedido()
        self.assertEqual(self.itens_sessao(), {str(self.leite.pk): 3})
        self.assertEqual(dormir.call_count, checkout.TENTATIVAS_APOS_TRAVA - 1)


@configurado
class BaseDaTentativaTests(CheckoutBase):
    """A base assinada só vale se já gerou o pedido ou se é o último pedido atual do usuário."""

    def setUp(self):
        super().setUp()
        self.preencher((self.arroz, 2))

    def base_do_token(self, token):
        return signing.loads(token, salt=checkout.SAL_REVISAO)['base']

    def forjar(self, **alteracoes):
        """Assina com a SECRET_KEY de desenvolvimento, que é pública no repositório."""
        legitimo = signing.loads(self.token(), salt=checkout.SAL_REVISAO)
        return signing.dumps(
            {**legitimo, **alteracoes}, key=settings.SECRET_KEY, salt=checkout.SAL_REVISAO, compress=True,
        )

    def assert_base_recusada(self, resposta, pedidos):
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, checkout.BaseDesatualizada.mensagem)
        self.assertEqual(Pedido.objects.count(), pedidos)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        # A nova revisão apresentada usa a base atual, nunca a recusada.
        self.assertEqual(self.base_do_token(resposta.context['token']), checkout.pedido_base(self.cliente))

    def test_base_atual_sem_pedido_anterior_e_aceita(self):
        token = self.token()
        self.assertEqual(self.base_do_token(token), 0)
        pedido = self.assert_confirmado(self.confirmar(token))
        self.assertEqual(pedido.chave_idempotencia, checkout.chave_da_tentativa(self.cliente, 0))

    def test_base_antiga_com_pedido_correspondente_devolve_o_pedido(self):
        token_antigo = self.token()
        primeiro = self.assert_confirmado(self.confirmar(token_antigo))
        self.preencher((self.leite, 1))
        self.confirmar(self.token())
        self.assertEqual(Pedido.objects.count(), 2)

        self.preencher((self.arroz, 5))
        resposta = self.confirmar(token_antigo)
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[primeiro.pk]))
        self.assertEqual(Pedido.objects.count(), 2)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 5})

    def test_base_desatualizada_sem_pedido_correspondente_e_recusada(self):
        token = self.token()
        # Pedido registrado por outro caminho depois da revisão: a base 0 deixou de ser a atual.
        outro = self.criar_pedido_direto(self.cliente, uuid.uuid4())
        resposta = self.confirmar(token)
        self.assert_base_recusada(resposta, pedidos=1)

        pedido = Pedido.objects.exclude(pk=outro.pk)
        self.assertFalse(pedido.exists())
        novo = self.confirmar(resposta.context['token'])
        criado = Pedido.objects.exclude(pk=outro.pk).get()
        self.assertRedirects(novo, reverse('principal:confirmacao_pedido', args=[criado.pk]))
        self.assertEqual(criado.chave_idempotencia, checkout.chave_da_tentativa(self.cliente, outro.pk))

    def test_base_arbitraria_sem_pedido_e_recusada(self):
        for base in (1, 999, 10 ** 9):
            with self.subTest(base=base):
                self.assert_base_recusada(self.confirmar(self.forjar(base=base)), pedidos=0)

    def test_token_forjado_com_a_secret_key_de_desenvolvimento_nao_contorna_a_idempotencia(self):
        primeiro = self.assert_confirmado(self.confirmar(self.token()))
        self.preencher((self.arroz, 2))
        for base in (999, primeiro.pk + 1, primeiro.pk + 50):
            with self.subTest(base=base):
                self.assert_base_recusada(self.confirmar(self.forjar(base=base)), pedidos=1)
        # A base que já gerou pedido apenas devolve esse pedido, sem criar outro.
        resposta = self.confirmar(self.forjar(base=0))
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[primeiro.pk]))
        self.assertEqual(Pedido.objects.count(), 1)
        # Forjar o usuário de outro cliente também não é aceito.
        resposta = self.confirmar(self.forjar(usuario=self.outro_cliente.pk))
        self.assertContains(resposta, MSG_REVISAO_INVALIDA)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_compra_posterior_usa_a_nova_base(self):
        primeiro = self.assert_confirmado(self.confirmar(self.token()))
        self.preencher((self.leite, 1))
        token = self.token()
        self.assertEqual(self.base_do_token(token), primeiro.pk)
        self.confirmar(token)
        segundo = Pedido.objects.exclude(pk=primeiro.pk).get()
        self.assertEqual(segundo.chave_idempotencia, checkout.chave_da_tentativa(self.cliente, primeiro.pk))

    def test_usuarios_diferentes_nao_compartilham_chaves(self):
        outro = Client()
        outro.force_login(self.outro_cliente)
        self.preencher((self.arroz, 1), cliente=outro)
        token_alheio = self.token(outro)
        pedido_proprio = self.assert_confirmado(self.confirmar(self.token()))
        self.confirmar(token_alheio, cliente=outro)
        pedido_alheio = Pedido.objects.get(cliente=self.outro_cliente)

        self.assertEqual((self.base_do_token(token_alheio), Pedido.objects.count()), (0, 2))
        self.assertNotEqual(pedido_proprio.chave_idempotencia, pedido_alheio.chave_idempotencia)
        self.assertEqual(
            pedido_alheio.chave_idempotencia, checkout.chave_da_tentativa(self.outro_cliente, 0),
        )
        self.assertEqual(
            self.client.get(reverse('principal:confirmacao_pedido', args=[pedido_alheio.pk])).status_code,
            404,
        )


@configurado
class ConcorrenciaCheckoutTests(TransactionTestCase):
    """Duas confirmações em threads reais, intercaladas em cada camada de proteção.

    A segunda requisição carrega a sessão (com o carrinho) e pausa; a primeira conclui o
    pedido; então a segunda continua. É o intervalo que permitia pedidos duplicados.
    """

    def setUp(self):
        categoria = Categoria.objects.create(nome='Categoria concorrencia de teste')
        self.arroz = Produto.objects.create(
            categoria=categoria, nome='Arroz concorrencia de teste', preco=Decimal('12.50'),
            unidade='pacote de teste',
        )
        self.leite = Produto.objects.create(
            categoria=categoria, nome='Leite concorrencia de teste', preco=Decimal('6.70'),
            unidade='caixa de teste',
        )
        self.cliente = get_user_model().objects.create_user('cliente_concorrencia', password=None)
        self.client.force_login(self.cliente)

    def preencher(self, cliente, *itens):
        sessao = cliente.session
        sessao[CHAVE_SESSAO] = {str(produto.pk): quantidade for produto, quantidade in itens}
        sessao.save()

    def outra_aba(self):
        aba = Client()
        aba.cookies[settings.SESSION_COOKIE_NAME] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        return aba

    def token(self, cliente):
        return cliente.get(reverse('principal:checkout')).context['token']

    def confirmar(self, cliente, token):
        return cliente.post(reverse('principal:checkout'), {**ENTREGA_TESTE, 'revisao': token})

    def intercalar(self, alvo, pausar_na_chamada, primeira, segunda):
        pausou, liberar = threading.Event(), threading.Event()
        original = getattr(checkout, alvo)
        chamadas = []

        def com_pausa(*args, **kwargs):
            if threading.current_thread().name == 'segunda-confirmacao':
                chamadas.append(alvo)
                if len(chamadas) == pausar_na_chamada:
                    pausou.set()
                    liberar.wait(15)
            return original(*args, **kwargs)

        respostas = {}

        def executar_segunda():
            try:
                respostas['segunda'] = segunda()
            finally:
                fechar_conexoes_da_thread()

        with mock.patch.object(checkout, alvo, side_effect=com_pausa):
            thread = threading.Thread(target=executar_segunda, name='segunda-confirmacao')
            thread.start()
            self.assertTrue(pausou.wait(15))
            respostas['primeira'] = primeira()
            liberar.set()
            thread.join(15)
        self.assertFalse(thread.is_alive())
        return respostas['primeira'], respostas['segunda']

    def assert_um_pedido(self, primeira, segunda, itens):
        pedido = Pedido.objects.get()
        destino = reverse('principal:confirmacao_pedido', args=[pedido.pk])
        self.assertEqual((primeira.status_code, primeira['Location']), (302, destino))
        self.assertEqual((segunda.status_code, segunda['Location']), (302, destino))
        self.assertEqual(ItemPedido.objects.count(), itens)
        return pedido

    def duas_abas(self):
        self.preencher(self.client, (self.arroz, 2), (self.leite, 1))
        aba = self.outra_aba()
        return aba, self.token(self.client), self.token(aba)

    def test_duas_abas_com_sessao_carregada_antes_da_conclusao(self):
        aba, token1, token2 = self.duas_abas()
        primeira, segunda = self.intercalar(
            'ler_revisao', 1,
            lambda: self.confirmar(self.client, token1), lambda: self.confirmar(aba, token2),
        )
        self.assert_um_pedido(primeira, segunda, itens=2)
        self.assertIsNone(self.client.session.get(CHAVE_SESSAO))

    def test_duas_abas_apos_a_consulta_previa_do_servico(self):
        # Pausa depois das consultas prévias: a validação de unicidade impede o segundo pedido.
        aba, token1, token2 = self.duas_abas()
        primeira, segunda = self.intercalar(
            'validar_entrega', 2,
            lambda: self.confirmar(self.client, token1), lambda: self.confirmar(aba, token2),
        )
        self.assert_um_pedido(primeira, segunda, itens=2)

    def test_restricao_unique_do_banco_e_a_garantia_final(self):
        aba, token1, token2 = self.duas_abas()
        with mock.patch.object(Pedido, 'validate_unique', return_value=None):
            primeira, segunda = self.intercalar(
                'validar_entrega', 2,
                lambda: self.confirmar(self.client, token1), lambda: self.confirmar(aba, token2),
            )
        self.assert_um_pedido(primeira, segunda, itens=2)

    def test_base_conferida_depois_da_conclusao_concorrente_devolve_o_pedido(self):
        # A segunda requisição não encontra o pedido na primeira consulta e pausa antes de
        # conferir a base; a primeira conclui. A base mudou, mas pertence a esta tentativa.
        aba, token1, token2 = self.duas_abas()
        primeira, segunda = self.intercalar(
            'pedido_base', 1,
            lambda: self.confirmar(self.client, token1), lambda: self.confirmar(aba, token2),
        )
        self.assert_um_pedido(primeira, segunda, itens=2)

    def test_dois_dispositivos_do_mesmo_usuario_preservam_o_segundo_carrinho(self):
        dispositivo = Client()
        dispositivo.force_login(self.cliente)
        self.preencher(self.client, (self.arroz, 2))
        self.preencher(dispositivo, (self.leite, 4))
        token1, token2 = self.token(self.client), self.token(dispositivo)
        primeira, segunda = self.intercalar(
            'validar_entrega', 2,
            lambda: self.confirmar(self.client, token1), lambda: self.confirmar(dispositivo, token2),
        )
        pedido = self.assert_um_pedido(primeira, segunda, itens=1)
        self.assertEqual(pedido.itens.get().produto_id, self.arroz.pk)
        self.assertEqual(dispositivo.session.get(CHAVE_SESSAO), {str(self.leite.pk): 4})


class MigracaoChaveIdempotenciaTests(TransactionTestCase):
    """Executa as migrations 0002-0004 sobre pedidos criados no esquema anterior."""

    antes = [('principal', '0001_initial')]
    depois = [('principal', '0004_alter_pedido_chave_idempotencia')]
    campos = (
        'id', 'cliente_id', 'logradouro', 'numero', 'complemento', 'bairro', 'telefone',
        'subtotal', 'taxa_entrega', 'total', 'pagamento', 'estado', 'criado_em',
    )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_pedidos_preexistentes_recebem_chaves_distintas_e_unicas(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.antes)
        apps = executor.loader.project_state(self.antes).apps
        usuario = apps.get_model('auth', 'User').objects.create(username='cliente_migracao_testes')
        PedidoAntigo = apps.get_model('principal', 'Pedido')
        for indice in range(3):
            PedidoAntigo.objects.create(
                cliente=usuario, logradouro=f'Rua historica {indice} de teste', numero='1',
                complemento='', bairro='Bairro historico de teste', telefone='telefone de teste',
                subtotal=Decimal('10.00'), taxa_entrega=Decimal('1.00'), total=Decimal('11.00'),
                pagamento='na_entrega', estado='recebido',
            )
        historico = list(PedidoAntigo.objects.order_by('pk').values(*self.campos))

        executor = MigrationExecutor(connection)
        executor.migrate(self.depois)
        PedidoNovo = executor.loader.project_state(self.depois).apps.get_model('principal', 'Pedido')
        chaves = list(PedidoNovo.objects.order_by('pk').values_list('chave_idempotencia', flat=True))

        self.assertEqual(len(chaves), 3)
        self.assertTrue(all(isinstance(chave, uuid.UUID) and chave.version == 4 for chave in chaves))
        self.assertEqual(len(set(chaves)), 3)
        self.assertEqual(list(PedidoNovo.objects.order_by('pk').values(*self.campos)), historico)
        with self.assertRaises(IntegrityError):
            PedidoNovo.objects.filter(pk=historico[1]['id']).update(chave_idempotencia=chaves[0])


@configurado
class PreservacaoEnderecoTests(CheckoutBase):
    """S9-01 (RNF-005): erros na leitura da revisão preservam o endereço digitado."""

    forjados = {'subtotal': '0.01', 'taxa_entrega': '0.01', 'total': '0.01', 'preco': '0.01'}

    def setUp(self):
        super().setUp()
        self.preencher((self.arroz, 2))

    def assert_endereco_preservado(self, resposta, mensagem):
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, mensagem)
        form = resposta.context['form']
        for campo in ('logradouro', 'numero', 'complemento', 'bairro', 'telefone'):
            with self.subTest(campo=campo):
                self.assertEqual(form[campo].value(), ENTREGA_TESTE[campo])
        for valor in ('value="Rua de teste"', 'value="10"', 'value="Bloco de teste"', 'value="telefone de teste"'):
            self.assertContains(resposta, valor)
        self.assertContains(resposta, f'<option value="{BAIRRO_TESTE}" selected>', html=False)
        # A revisão reapresentada vem do servidor, nunca dos valores enviados.
        revisao = resposta.context['revisao']
        self.assertEqual((revisao.subtotal, revisao.taxa_entrega, revisao.total),
                         (Decimal('25.00'), TAXA_TESTE, Decimal('30.00')))
        self.assertNotContains(resposta, '0,01')
        if mensagem != checkout.BaseDesatualizada.mensagem:
            self.assert_sem_pedido()
        self.assertFalse(Pedido.objects.filter(itens__isnull=False).exists())
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_token_adulterado_preserva_o_endereco(self):
        token = self.token()
        resposta = self.confirmar(token[:-2] + ('AA' if token[-2:] != 'AA' else 'BB'), **self.forjados)
        self.assert_endereco_preservado(resposta, MSG_REVISAO_INVALIDA)

    def test_base_desatualizada_preserva_o_endereco(self):
        token = self.token()
        self.criar_pedido_direto(self.cliente, uuid.uuid4())
        resposta = self.confirmar(token, **self.forjados)
        self.assert_endereco_preservado(resposta, checkout.BaseDesatualizada.mensagem)
        self.assertEqual(Pedido.objects.count(), 1)
