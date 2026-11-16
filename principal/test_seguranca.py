"""Regressão da Semana 9 (S9-06): comportamentos de segurança comprovados na auditoria.

Escape de HTML, mascaramento de senhas em relatórios de erro, identificadores fora da faixa
e perda de acesso durante a sessão. Todos os dados são fictícios e existem só no banco de testes.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape
from django.views.debug import ExceptionReporter, SafeExceptionReporterFilter

from .carrinho import CHAVE_SESSAO
from .models import Categoria, EstadoPedido, ItemPedido, Pedido, Produto

SCRIPT = '<script>alert("x")</script>'
IMAGEM = '<img src=x onerror=alert(1)>'
BAIRRO_MALICIOSO = '<b>Bairro</b> de teste'
GIGANTE = 10 ** 30
MSG_PEDIDO_NAO_ENCONTRADO = 'Pedido não encontrado ou acesso não permitido.'


def permissoes(*codinomes):
    return Permission.objects.filter(content_type__app_label='principal', codename__in=codinomes)


@override_settings(CHECKOUT_BAIRROS_ATENDIDOS=(BAIRRO_MALICIOSO,), CHECKOUT_TAXA_ENTREGA=Decimal('5.00'))
class EscapeHtmlTests(TestCase):
    """Conteúdo malicioso de cadastros e pedidos é exibido como texto, nunca como HTML."""

    @classmethod
    def setUpTestData(cls):
        usuarios = get_user_model().objects
        # create_user não aplica o validador de username: simula um nome malicioso já gravado.
        cls.cliente = usuarios.create_user(f'cliente{SCRIPT}', password=None)
        cls.operador = usuarios.create_user(f'operador{IMAGEM}', password=None, is_staff=True)
        cls.operador.user_permissions.add(*permissoes('view_pedido', 'change_pedido'))
        categoria = Categoria.objects.create(nome=f'Categoria {IMAGEM}')
        cls.produto = Produto.objects.create(
            categoria=categoria, nome=f'Produto {SCRIPT}', preco=Decimal('2.00'), unidade=f'un {IMAGEM}',
        )
        cls.pedido = Pedido.objects.create(
            cliente=cls.cliente, logradouro=f'Rua {SCRIPT}', numero='1', complemento=f'Bloco {IMAGEM}',
            bairro=BAIRRO_MALICIOSO, telefone=f'tel {SCRIPT}', subtotal=Decimal('2.00'),
            taxa_entrega=Decimal('5.00'), total=Decimal('7.00'),
        )
        ItemPedido.objects.create(
            pedido=cls.pedido, produto=cls.produto, nome_produto=f'Produto {SCRIPT}',
            unidade=f'un {IMAGEM}', quantidade=1, preco_unitario=Decimal('2.00'),
        )

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.cliente)
        sessao = self.http.session
        sessao[CHAVE_SESSAO] = {str(self.produto.pk): 1}
        sessao.save()
        self.equipe = Client()
        self.equipe.force_login(self.operador)

    def assert_escapado(self, resposta, *conteudos):
        html = resposta.content.decode()
        for bruto in (SCRIPT, IMAGEM, '<b>Bairro</b>'):
            self.assertNotIn(bruto, html)
        for conteudo in conteudos:
            self.assertIn(escape(conteudo), html)

    def test_paginas_do_cliente(self):
        paginas = {
            'catalogo': (self.http.get(reverse('principal:catalogo')), (self.produto.nome, self.produto.unidade)),
            'detalhe': (
                self.http.get(reverse('principal:detalhe_produto', args=[self.produto.pk])),
                (self.produto.nome, self.produto.unidade),
            ),
            'carrinho': (self.http.get(reverse('principal:carrinho')), (self.produto.nome, self.produto.unidade)),
            'checkout': (self.http.get(reverse('principal:checkout')), (self.produto.nome, BAIRRO_MALICIOSO)),
            'confirmacao': (
                self.http.get(reverse('principal:confirmacao_pedido', args=[self.pedido.pk])),
                (f'Produto {SCRIPT}', f'Rua {SCRIPT}', f'Bloco {IMAGEM}', f'tel {SCRIPT}'),
            ),
            'acompanhamento': (
                self.http.get(reverse('principal:acompanhamento_pedido', args=[self.pedido.pk])),
                (f'Produto {SCRIPT}', BAIRRO_MALICIOSO),
            ),
            'meus_pedidos': (self.http.get(reverse('principal:meus_pedidos')), ()),
        }
        for nome, (resposta, conteudos) in paginas.items():
            with self.subTest(pagina=nome):
                self.assertEqual(resposta.status_code, 200)
                # O nome de usuário malicioso também aparece na navegação.
                self.assert_escapado(resposta, self.cliente.username, *conteudos)

    def test_paginas_da_equipe(self):
        lista = self.equipe.get(reverse('principal:equipe_pedidos'))
        self.assert_escapado(lista, self.cliente.username, BAIRRO_MALICIOSO, self.operador.username)
        detalhe = self.equipe.get(reverse('principal:equipe_pedido_detalhe', args=[self.pedido.pk]))
        self.assert_escapado(
            detalhe, self.cliente.username, f'Rua {SCRIPT}', f'Bloco {IMAGEM}', f'tel {SCRIPT}',
            f'Produto {SCRIPT}', f'un {IMAGEM}',
        )

    def test_mensagens_com_conteudo_malicioso(self):
        resposta = self.http.post(
            reverse('principal:adicionar_ao_carrinho', args=[self.produto.pk]), {'quantidade': '1'}, follow=True,
        )
        self.assert_escapado(resposta, f'{self.produto.nome} adicionado ao carrinho.')
        alteracao = self.equipe.post(
            reverse('principal:equipe_alterar_estado', args=[self.pedido.pk]),
            {'estado_atual': f'{SCRIPT}', 'novo_estado': EstadoPedido.CONFIRMADO}, follow=True,
        )
        self.assert_escapado(alteracao)


class MascaramentoDeSenhasTests(TestCase):
    """RNF-001: senhas enviadas não aparecem em relatórios de erro."""

    # Senha fictícia, usada somente neste teste e nunca impressa.
    senha = 'Ficticia!Relatorio93'

    def relatorio(self, requisicao):
        return ExceptionReporter(
            requisicao, ValueError, ValueError('erro simulado'), None, is_email=True,
        ).get_traceback_text()

    def test_cadastro_marca_e_mascara_as_senhas(self):
        resposta = self.client.post(reverse('principal:cadastro'), {
            'username': 'cliente_relatorio', 'password1': self.senha, 'password2': self.senha + 'x',
        })
        requisicao = resposta.wsgi_request
        self.assertEqual(set(requisicao.sensitive_post_parameters), {'password1', 'password2'})
        filtrados = SafeExceptionReporterFilter().get_post_parameters(requisicao)
        self.assertEqual(filtrados['username'], 'cliente_relatorio')
        for campo in ('password1', 'password2'):
            self.assertNotIn(self.senha, filtrados[campo])
            self.assertTrue(set(filtrados[campo]) == {'*'})
        texto = self.relatorio(requisicao)
        self.assertNotIn(self.senha, texto)
        self.assertIn('cliente_relatorio', texto)
        self.assertFalse(get_user_model().objects.filter(username='cliente_relatorio').exists())

    def test_login_mascara_todos_os_parametros(self):
        resposta = self.client.post(reverse('principal:login'), {'username': 'alguem', 'password': self.senha})
        requisicao = resposta.wsgi_request
        self.assertEqual(requisicao.sensitive_post_parameters, '__ALL__')
        self.assertNotIn(self.senha, self.relatorio(requisicao))


class IdentificadoresForaDaFaixaTests(TestCase):
    """Identificadores como 10**30 resultam em 404, nunca em HTTP 500."""

    @classmethod
    def setUpTestData(cls):
        usuarios = get_user_model().objects
        cls.cliente = usuarios.create_user('cliente_faixa', password=None)
        cls.operador = usuarios.create_user('operador_faixa', password=None, is_staff=True)
        cls.operador.user_permissions.add(*permissoes('view_pedido', 'change_pedido'))

    def test_rotas_de_pedido_do_cliente(self):
        http = Client()
        http.force_login(self.cliente)
        for nome in ('acompanhamento_pedido', 'confirmacao_pedido'):
            with self.subTest(rota=nome):
                resposta = http.get(reverse(f'principal:{nome}', args=[GIGANTE]))
                self.assertContains(resposta, MSG_PEDIDO_NAO_ENCONTRADO, status_code=404)

    def test_rotas_da_equipe(self):
        http = Client()
        http.force_login(self.operador)
        self.assertEqual(http.get(reverse('principal:equipe_pedido_detalhe', args=[GIGANTE])).status_code, 404)
        resposta = http.post(
            reverse('principal:equipe_alterar_estado', args=[GIGANTE]),
            {'estado_atual': EstadoPedido.RECEBIDO, 'novo_estado': EstadoPedido.CONFIRMADO},
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_rotas_publicas_e_do_carrinho(self):
        self.assertEqual(self.client.get(reverse('principal:detalhe_produto', args=[GIGANTE])).status_code, 404)
        for nome in ('atualizar_item_carrinho', 'remover_item_carrinho'):
            with self.subTest(rota=nome):
                resposta = self.client.post(reverse(f'principal:{nome}', args=[GIGANTE]), {'quantidade': '1'})
                self.assertRedirects(resposta, reverse('principal:carrinho'))


class AcessoDuranteASessaoTests(TestCase):
    """Desativação ou retirada de permissões vale na requisição seguinte da mesma sessão."""

    @classmethod
    def setUpTestData(cls):
        usuarios = get_user_model().objects
        cls.cliente = usuarios.create_user('cliente_sessao', password=None)
        cls.operador = usuarios.create_user('operador_sessao', password=None, is_staff=True)
        cls.operador.user_permissions.add(*permissoes('view_pedido', 'change_pedido'))
        cls.pedido = Pedido.objects.create(
            cliente=cls.cliente, logradouro='Rua', numero='1', bairro='Bairro', telefone='tel',
            subtotal=Decimal('1.00'), taxa_entrega=Decimal('0.00'), total=Decimal('1.00'),
        )

    def entrar(self, usuario):
        http = Client()
        http.force_login(usuario)
        return http

    def test_cliente_desativado_perde_acesso(self):
        http = self.entrar(self.cliente)
        url = reverse('principal:meus_pedidos')
        self.assertEqual(http.get(url).status_code, 200)
        get_user_model().objects.filter(pk=self.cliente.pk).update(is_active=False)
        self.assertRedirects(http.get(url), f"{reverse('principal:login')}?next={url}", fetch_redirect_response=False)

    def test_integrante_desativado_perde_acesso(self):
        http = self.entrar(self.operador)
        url = reverse('principal:equipe_pedidos')
        self.assertEqual(http.get(url).status_code, 200)
        get_user_model().objects.filter(pk=self.operador.pk).update(is_active=False)
        self.assertRedirects(http.get(url), f"{reverse('principal:login')}?next={url}", fetch_redirect_response=False)

    def test_permissoes_ou_is_staff_removidos_valem_na_requisicao_seguinte(self):
        http = self.entrar(self.operador)
        lista = reverse('principal:equipe_pedidos')
        alterar = reverse('principal:equipe_alterar_estado', args=[self.pedido.pk])
        dados = {'estado_atual': EstadoPedido.RECEBIDO, 'novo_estado': EstadoPedido.CONFIRMADO}

        self.operador.user_permissions.remove(*permissoes('change_pedido'))
        self.assertEqual(http.post(alterar, dados).status_code, 403)
        self.assertEqual(http.get(lista).status_code, 200)

        self.operador.user_permissions.remove(*permissoes('view_pedido'))
        self.assertEqual(http.get(lista).status_code, 403)

        self.operador.user_permissions.add(*permissoes('view_pedido', 'change_pedido'))
        get_user_model().objects.filter(pk=self.operador.pk).update(is_staff=False)
        self.assertEqual(http.get(lista).status_code, 403)
        self.assertEqual(http.post(alterar, dados).status_code, 403)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, EstadoPedido.RECEBIDO)
