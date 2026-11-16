import re
import threading
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.db import DatabaseError, connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from . import pedidos
from .models import Categoria, EstadoPedido, ItemPedido, Pedido, Produto

E = EstadoPedido
MSG_SEM_PERMISSAO = 'Você não tem permissão para acessar esta área.'
MSG_INVALIDA = 'Esta alteração não é permitida para o estado atual.'
MSG_MUDOU = 'O estado do pedido mudou. Atualize a consulta.'
MSG_FALHA = 'Não foi possível salvar a alteração.'

# Tabela documentada em regras-negocio.md (RN-018), escrita aqui de forma independente.
VALIDAS = {
    (E.RECEBIDO, E.CONFIRMADO), (E.CONFIRMADO, E.EM_PREPARO),
    (E.EM_PREPARO, E.SAIU_PARA_ENTREGA), (E.SAIU_PARA_ENTREGA, E.ENTREGUE),
    (E.RECEBIDO, E.CANCELADO), (E.CONFIRMADO, E.CANCELADO), (E.EM_PREPARO, E.CANCELADO),
}


def mensagens(resposta):
    """Mensagens da requisição pela API pública do framework de mensagens."""
    return [str(mensagem) for mensagem in get_messages(resposta.wsgi_request)]


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


def permissao(codinome):
    return Permission.objects.get(content_type__app_label='principal', codename=codinome)


class Dados:
    """Usuários e pedidos criados somente no banco de testes."""

    def criar_dados(self):
        usuarios = get_user_model().objects
        self.cliente = usuarios.create_user('cliente_pedidos_a', password=None)
        self.outro_cliente = usuarios.create_user('cliente_pedidos_b', password=None)
        self.staff_sem_permissao = usuarios.create_user('staff_sem_permissao', password=None, is_staff=True)
        self.staff_consulta = usuarios.create_user('staff_consulta', password=None, is_staff=True)
        self.staff_consulta.user_permissions.add(permissao('view_pedido'))
        self.operador = usuarios.create_user('staff_operador', password=None, is_staff=True)
        self.operador.user_permissions.add(permissao('view_pedido'), permissao('change_pedido'))
        self.staff_so_alteracao = usuarios.create_user('staff_so_alteracao', password=None, is_staff=True)
        self.staff_so_alteracao.user_permissions.add(permissao('change_pedido'))
        self.cliente_com_permissoes = usuarios.create_user('cliente_com_permissoes', password=None)
        self.cliente_com_permissoes.user_permissions.add(permissao('view_pedido'), permissao('change_pedido'))
        self.superusuario = usuarios.create_superuser('superusuario_pedidos', password=None)
        self.superusuario_sem_staff = usuarios.create_user(
            'superusuario_sem_staff', password=None, is_superuser=True, is_staff=False,
        )
        categoria = Categoria.objects.create(nome='Categoria pedidos de teste')
        self.arroz = Produto.objects.create(
            categoria=categoria, nome='Arroz pedidos de teste', preco=Decimal('12.50'), unidade='pacote de teste',
        )
        self.leite = Produto.objects.create(
            categoria=categoria, nome='Leite pedidos de teste', preco=Decimal('6.70'), unidade='caixa de teste',
        )

    def criar_pedido(self, cliente=None, estado=E.RECEBIDO, bairro='Bairro A de teste', minutos_atras=0):
        pedido = Pedido.objects.create(
            cliente=cliente or self.cliente, logradouro='Rua de teste', numero='10',
            complemento='Bloco de teste', bairro=bairro, telefone='telefone de teste',
            subtotal=Decimal('31.70'), taxa_entrega=Decimal('5.00'), total=Decimal('36.70'), estado=estado,
        )
        ItemPedido.objects.create(
            pedido=pedido, produto=self.arroz, nome_produto='Arroz historico de teste',
            unidade='pacote historico', quantidade=2, preco_unitario=Decimal('12.50'),
        )
        ItemPedido.objects.create(
            pedido=pedido, produto=self.leite, nome_produto='Leite historico de teste',
            unidade='caixa historica', quantidade=1, preco_unitario=Decimal('6.70'),
        )
        if minutos_atras:
            Pedido.objects.filter(pk=pedido.pk).update(
                criado_em=timezone.now() - timedelta(minutes=minutos_atras),
            )
            pedido.refresh_from_db()
        return pedido

    def entrar(self, usuario):
        cliente = Client()
        cliente.force_login(usuario)
        return cliente

    def alterar(self, cliente_http, pedido, esperado, novo):
        return cliente_http.post(
            reverse('principal:equipe_alterar_estado', args=[pedido.pk]),
            {'estado_atual': esperado, 'novo_estado': novo},
        )

    def retrato(self, pedido):
        """Tudo do pedido e dos itens, exceto o estado."""
        pedido = Pedido.objects.get(pk=pedido.pk)
        campos = {
            campo.attname: getattr(pedido, campo.attname)
            for campo in Pedido._meta.concrete_fields if campo.name != 'estado'
        }
        itens = list(ItemPedido.objects.filter(pedido=pedido).order_by('pk').values())
        return campos, itens


class AcessoInternoTests(Dados, TestCase):

    def setUp(self):
        self.criar_dados()
        self.pedido = self.criar_pedido()
        self.urls_consulta = (
            reverse('principal:equipe_pedidos'),
            reverse('principal:equipe_pedido_detalhe', args=[self.pedido.pk]),
        )

    def test_visitante_e_direcionado_ao_login(self):
        for url in self.urls_consulta:
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), f"{reverse('principal:login')}?next={url}",
                    fetch_redirect_response=False,
                )
        url = reverse('principal:equipe_alterar_estado', args=[self.pedido.pk])
        resposta = self.client.post(url, {'estado_atual': E.RECEBIDO, 'novo_estado': E.CONFIRMADO})
        self.assertRedirects(resposta, f"{reverse('principal:login')}?next={url}", fetch_redirect_response=False)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.RECEBIDO)

    def test_sem_staff_ou_sem_view_pedido_recebe_403(self):
        for usuario in (
            self.cliente, self.staff_sem_permissao, self.staff_so_alteracao,
            self.cliente_com_permissoes, self.superusuario_sem_staff,
        ):
            cliente_http = self.entrar(usuario)
            for url in self.urls_consulta:
                with self.subTest(usuario=usuario.username, url=url):
                    resposta = cliente_http.get(url)
                    self.assertEqual(resposta.status_code, 403)
                    self.assertContains(resposta, MSG_SEM_PERMISSAO, status_code=403)
                    self.assertNotContains(resposta, 'telefone de teste', status_code=403)

    def test_staff_com_view_pedido_consulta_mas_nao_altera(self):
        cliente_http = self.entrar(self.staff_consulta)
        for url in self.urls_consulta:
            self.assertEqual(cliente_http.get(url).status_code, 200)
        detalhe = cliente_http.get(self.urls_consulta[1])
        self.assertNotContains(detalhe, 'name="novo_estado"')

        resposta = self.alterar(cliente_http, self.pedido, E.RECEBIDO, E.CONFIRMADO)
        self.assertContains(resposta, MSG_SEM_PERMISSAO, status_code=403)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.RECEBIDO)

    def test_sem_staff_ou_sem_change_pedido_nao_altera(self):
        for usuario in (
            self.cliente, self.staff_sem_permissao, self.staff_consulta,
            self.cliente_com_permissoes, self.superusuario_sem_staff,
        ):
            with self.subTest(usuario=usuario.username):
                resposta = self.alterar(self.entrar(usuario), self.pedido, E.RECEBIDO, E.CONFIRMADO)
                self.assertContains(resposta, MSG_SEM_PERMISSAO, status_code=403)
                self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.RECEBIDO)

    def test_operador_com_view_e_change_opera(self):
        cliente_http = self.entrar(self.operador)
        detalhe = cliente_http.get(self.urls_consulta[1])
        self.assertContains(detalhe, 'name="novo_estado"')
        resposta = self.alterar(cliente_http, self.pedido, E.RECEBIDO, E.CONFIRMADO)
        self.assertRedirects(resposta, self.urls_consulta[1])
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.CONFIRMADO)

    def test_superusuario_com_staff_opera_pelas_permissoes_nativas(self):
        cliente_http = self.entrar(self.superusuario)
        self.assertEqual(cliente_http.get(self.urls_consulta[0]).status_code, 200)
        self.alterar(cliente_http, self.pedido, E.RECEBIDO, E.CANCELADO)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.CANCELADO)

    def test_servico_tambem_verifica_permissoes(self):
        for usuario in (
            self.cliente, self.staff_sem_permissao, self.staff_consulta, self.cliente_com_permissoes,
            self.superusuario_sem_staff,
        ):
            with self.subTest(usuario=usuario.username), self.assertRaises(pedidos.SemPermissao):
                pedidos.alterar_estado(
                    usuario=usuario, pedido_id=self.pedido.pk,
                    estado_esperado=E.RECEBIDO, novo_estado=E.CONFIRMADO,
                )
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.RECEBIDO)

    def test_pedido_inexistente_retorna_404(self):
        cliente_http = self.entrar(self.operador)
        self.assertEqual(cliente_http.get(reverse('principal:equipe_pedido_detalhe', args=[999999])).status_code, 404)
        self.assertEqual(
            cliente_http.post(
                reverse('principal:equipe_alterar_estado', args=[999999]),
                {'estado_atual': E.RECEBIDO, 'novo_estado': E.CONFIRMADO},
            ).status_code,
            404,
        )

    def test_navegacao_mostra_painel_somente_a_quem_pode_consultar(self):
        url_painel = reverse('principal:equipe_pedidos')
        url_meus = reverse('principal:meus_pedidos')
        visitante = self.client.get(reverse('principal:inicio'))
        self.assertNotContains(visitante, url_meus)
        self.assertNotContains(visitante, url_painel)
        for usuario, ve_painel in (
            (self.cliente, False), (self.staff_sem_permissao, False), (self.cliente_com_permissoes, False),
            (self.staff_consulta, True), (self.operador, True), (self.superusuario, True),
        ):
            with self.subTest(usuario=usuario.username):
                resposta = self.entrar(usuario).get(reverse('principal:inicio'))
                self.assertContains(resposta, f'href="{url_meus}"')
                if ve_painel:
                    self.assertContains(resposta, f'href="{url_painel}"')
                else:
                    self.assertNotContains(resposta, f'href="{url_painel}"')


class PainelEquipeTests(Dados, TestCase):

    def setUp(self):
        self.criar_dados()
        self.http = self.entrar(self.operador)

    def test_lista_vazia(self):
        resposta = self.http.get(reverse('principal:equipe_pedidos'))
        self.assertContains(resposta, 'Nenhum pedido recebido.')

    def test_lista_mais_recentes_primeiro_com_cliente_bairro_total_e_estado(self):
        antigo = self.criar_pedido(bairro='Bairro antigo de teste', minutos_atras=30)
        recente = self.criar_pedido(cliente=self.outro_cliente, estado=E.CONFIRMADO, bairro='Bairro recente de teste')
        mesmo_instante = self.criar_pedido(minutos_atras=0)
        Pedido.objects.filter(pk=mesmo_instante.pk).update(criado_em=recente.criado_em)

        resposta = self.http.get(reverse('principal:equipe_pedidos'))
        self.assertEqual(
            [pedido.pk for pedido in resposta.context['pedidos']], [mesmo_instante.pk, recente.pk, antigo.pk],
        )
        for texto in (
            f'Pedido {recente.pk}', self.outro_cliente.username, 'Bairro recente de teste', 'R$ 36,70',
            'Confirmado', 'Bairro antigo de teste', 'Recebido',
        ):
            self.assertContains(resposta, texto)

    def test_lista_sem_consultas_n_mais_1(self):
        self.criar_pedido()
        url = reverse('principal:equipe_pedidos')
        with CaptureQueriesContext(connection) as consultas:
            self.http.get(url)
        for _ in range(5):
            self.criar_pedido(cliente=self.outro_cliente)
        with self.assertNumQueries(len(consultas)):
            resposta = self.http.get(url)
        self.assertEqual(len(resposta.context['pedidos']), 6)

    def test_detalhe_exibe_todos_os_dados_de_rf_023(self):
        pedido = self.criar_pedido()
        resposta = self.http.get(reverse('principal:equipe_pedido_detalhe', args=[pedido.pk]))
        for texto in (
            f'Pedido {pedido.pk}', timezone.localtime(pedido.criado_em).strftime('%d/%m/%Y %H:%M'),
            self.cliente.username, 'telefone de teste', 'Rua de teste', '10', 'Bloco de teste',
            'Bairro A de teste', 'Arroz historico de teste', 'pacote historico', 'Leite historico de teste',
            'caixa historica', 'R$ 12,50', 'R$ 25,00', 'R$ 6,70', 'R$ 31,70', 'R$ 5,00', 'R$ 36,70',
            'Na entrega', 'Recebido',
        ):
            self.assertContains(resposta, texto)

    def test_detalhe_sem_consultas_n_mais_1(self):
        pedido = self.criar_pedido()
        url = reverse('principal:equipe_pedido_detalhe', args=[pedido.pk])
        with CaptureQueriesContext(connection) as consultas:
            self.http.get(url)
        for _ in range(4):
            ItemPedido.objects.create(
                pedido=pedido, produto=self.arroz, nome_produto='Extra', unidade='u',
                quantidade=1, preco_unitario=Decimal('1.00'),
            )
        with self.assertNumQueries(len(consultas)):
            self.http.get(url)

    def test_acoes_apresentadas_correspondem_a_tabela(self):
        for estado in E.values:
            with self.subTest(estado=estado):
                pedido = self.criar_pedido(estado=estado)
                resposta = self.http.get(reverse('principal:equipe_pedido_detalhe', args=[pedido.pk]))
                oferecidas = [acao['estado'] for acao in resposta.context['acoes']]
                esperadas = sorted(novo for atual, novo in VALIDAS if atual == estado)
                self.assertEqual(sorted(oferecidas), esperadas)
                for novo in E.values:
                    contem = f'name="novo_estado" value="{novo}"' in resposta.content.decode()
                    self.assertEqual(contem, novo in esperadas)
                terminal = estado in (E.ENTREGUE, E.CANCELADO)
                self.assertEqual(resposta.context['terminal'], terminal)
                if terminal:
                    self.assertContains(resposta, 'Estado terminal: nenhuma alteração disponível.')
                    self.assertNotContains(resposta, 'name="novo_estado"')

    def test_dados_comerciais_nao_sao_editaveis(self):
        pedido = self.criar_pedido()
        url = reverse('principal:equipe_pedido_detalhe', args=[pedido.pk])
        resposta = self.http.get(url)
        conteudo = resposta.content.decode()
        for campo in ('logradouro', 'numero', 'complemento', 'bairro', 'telefone', 'subtotal',
                      'taxa_entrega', 'total', 'quantidade', 'preco_unitario', 'cliente'):
            self.assertNotIn(f'name="{campo}"', conteudo)
        antes = self.retrato(pedido)
        self.assertEqual(self.http.post(url, {'logradouro': 'Outra rua', 'total': '0.01'}).status_code, 405)
        alterar = reverse('principal:equipe_alterar_estado', args=[pedido.pk])
        self.http.post(alterar, {
            'estado_atual': E.RECEBIDO, 'novo_estado': E.CONFIRMADO,
            'logradouro': 'Outra rua', 'total': '0.01', 'cliente': self.outro_cliente.pk,
        })
        self.assertEqual(self.retrato(pedido), antes)
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.CONFIRMADO)


class TransicoesTests(Dados, TestCase):

    def setUp(self):
        self.criar_dados()
        self.http = self.entrar(self.operador)

    def test_tabela_do_servico_corresponde_a_documentacao(self):
        implementadas = {
            (atual, novo) for atual, proximos in pedidos.TRANSICOES.items() for novo in proximos
        }
        self.assertEqual(implementadas, VALIDAS)
        self.assertEqual(set(pedidos.TRANSICOES), set(E.values))

    def test_cada_transicao_valida_altera_somente_o_estado(self):
        for atual, novo in sorted(VALIDAS):
            with self.subTest(atual=atual, novo=novo):
                pedido = self.criar_pedido(estado=atual)
                antes = self.retrato(pedido)
                resposta = self.alterar(self.http, pedido, atual, novo)
                self.assertRedirects(resposta, reverse('principal:equipe_pedido_detalhe', args=[pedido.pk]))
                self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, novo)
                self.assertEqual(self.retrato(pedido), antes)

    def test_sequencia_completa_ate_entregue(self):
        pedido = self.criar_pedido()
        antes = self.retrato(pedido)
        sequencia = [E.RECEBIDO, E.CONFIRMADO, E.EM_PREPARO, E.SAIU_PARA_ENTREGA, E.ENTREGUE]
        for atual, novo in zip(sequencia, sequencia[1:]):
            self.alterar(self.http, pedido, atual, novo)
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.ENTREGUE)
        self.assertEqual(self.retrato(pedido), antes)

    def test_toda_transicao_fora_da_tabela_e_recusada_sem_alterar_nada(self):
        for atual in E.values:
            for novo in list(E.values) + ['inexistente', '', 'RECEBIDO', ' confirmado']:
                if (atual, novo) in VALIDAS:
                    continue
                with self.subTest(atual=atual, novo=novo):
                    pedido = self.criar_pedido(estado=atual)
                    antes = self.retrato(pedido)
                    resposta = self.alterar(self.http, pedido, atual, novo)
                    self.assertRedirects(resposta, reverse('principal:equipe_pedido_detalhe', args=[pedido.pk]))
                    self.assertIn(MSG_INVALIDA, mensagens(resposta))
                    self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, atual)
                    self.assertEqual(self.retrato(pedido), antes)

    def test_casos_nomeados_pular_retroceder_cancelar_tarde_e_terminais(self):
        casos = {
            'pular etapa': (E.RECEBIDO, E.EM_PREPARO),
            'pular para entregue': (E.CONFIRMADO, E.ENTREGUE),
            'retroceder': (E.EM_PREPARO, E.CONFIRMADO),
            'cancelar após saída': (E.SAIU_PARA_ENTREGA, E.CANCELADO),
            'alterar entregue': (E.ENTREGUE, E.CANCELADO),
            'reabrir cancelado': (E.CANCELADO, E.RECEBIDO),
            'estado inexistente': (E.RECEBIDO, 'aprovado'),
        }
        for nome, (atual, novo) in casos.items():
            with self.subTest(caso=nome):
                pedido = self.criar_pedido(estado=atual)
                with self.assertRaises(pedidos.TransicaoInvalida):
                    pedidos.alterar_estado(
                        usuario=self.operador, pedido_id=pedido.pk, estado_esperado=atual, novo_estado=novo,
                    )
                self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, atual)

    def test_estado_esperado_divergente_e_recusado(self):
        pedido = self.criar_pedido(estado=E.CONFIRMADO)
        antes = self.retrato(pedido)
        resposta = self.alterar(self.http, pedido, E.RECEBIDO, E.CONFIRMADO)
        self.assertIn(MSG_MUDOU, mensagens(resposta))
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.CONFIRMADO)
        self.assertEqual(self.retrato(pedido), antes)

    def test_estado_esperado_ausente_ou_forjado_nao_autoriza(self):
        pedido = self.criar_pedido(estado=E.SAIU_PARA_ENTREGA)
        url = reverse('principal:equipe_alterar_estado', args=[pedido.pk])
        for dados in (
            {'novo_estado': E.CANCELADO},
            {'estado_atual': E.RECEBIDO, 'novo_estado': E.CANCELADO},
            {'estado_atual': E.EM_PREPARO, 'novo_estado': E.CANCELADO},
            {},
        ):
            with self.subTest(dados=dados):
                self.http.post(url, dados)
                self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.SAIU_PARA_ENTREGA)

    def test_acao_repetida_nao_avanca_duas_etapas(self):
        pedido = self.criar_pedido()
        primeira = self.alterar(self.http, pedido, E.RECEBIDO, E.CONFIRMADO)
        segunda = self.alterar(self.http, pedido, E.RECEBIDO, E.CONFIRMADO)
        self.assertIn(f'Pedido {pedido.pk}: Recebido → Confirmado.', mensagens(primeira))
        self.assertIn(MSG_MUDOU, mensagens(segunda))
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.CONFIRMADO)

    def test_duas_pessoas_com_paginas_antigas(self):
        pedido = self.criar_pedido()
        outra = self.entrar(self.superusuario)
        # As duas abriram o pedido em Recebido; a primeira confirma e a segunda tenta cancelar.
        self.alterar(self.http, pedido, E.RECEBIDO, E.CONFIRMADO)
        resposta = self.alterar(outra, pedido, E.RECEBIDO, E.CANCELADO)
        self.assertIn(MSG_MUDOU, mensagens(resposta))
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.CONFIRMADO)
        detalhe = outra.get(reverse('principal:equipe_pedido_detalhe', args=[pedido.pk]))
        self.assertContains(detalhe, MSG_MUDOU)
        self.assertContains(detalhe, 'Confirmado')

    def test_falha_do_banco_preserva_o_estado(self):
        pedido = self.criar_pedido()
        with mock.patch('django.db.models.query.QuerySet.update', side_effect=DatabaseError('falha simulada')):
            resposta = self.alterar(self.http, pedido, E.RECEBIDO, E.CONFIRMADO)
        self.assertIn(MSG_FALHA, mensagens(resposta))
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.RECEBIDO)

    def test_alteracao_usa_uma_unica_atualizacao_condicional(self):
        pedido = self.criar_pedido()
        with CaptureQueriesContext(connection) as consultas:
            pedidos.alterar_estado(
                usuario=self.operador, pedido_id=pedido.pk, estado_esperado=E.RECEBIDO, novo_estado=E.CONFIRMADO,
            )
        atualizacoes = [c['sql'] for c in consultas.captured_queries if c['sql'].startswith('UPDATE')]
        self.assertEqual(len(atualizacoes), 1)
        self.assertIn('"estado" = ', atualizacoes[0].split('WHERE')[1])
        self.assertNotIn('"total"', atualizacoes[0].split('WHERE')[0])


class MetodosECsrfTests(Dados, TestCase):

    def setUp(self):
        self.criar_dados()
        self.pedido = self.criar_pedido()
        self.url = reverse('principal:equipe_alterar_estado', args=[self.pedido.pk])

    def test_get_e_head_na_rota_de_alteracao_retornam_405(self):
        http = self.entrar(self.operador)
        dados = {'estado_atual': E.RECEBIDO, 'novo_estado': E.CONFIRMADO}
        self.assertEqual(http.get(self.url, dados).status_code, 405)
        self.assertEqual(http.head(self.url, dados).status_code, 405)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.RECEBIDO)

    def test_post_sem_csrf_e_rejeitado_e_com_csrf_funciona(self):
        http = Client(enforce_csrf_checks=True)
        http.force_login(self.operador)
        http.get(reverse('principal:equipe_pedido_detalhe', args=[self.pedido.pk]))
        dados = {'estado_atual': E.RECEBIDO, 'novo_estado': E.CONFIRMADO}
        self.assertEqual(http.post(self.url, dados).status_code, 403)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.RECEBIDO)

        resposta = http.post(self.url, {**dados, 'csrfmiddlewaretoken': http.cookies['csrftoken'].value})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).estado, E.CONFIRMADO)

    def test_paginas_de_consulta_nao_aceitam_post(self):
        http = self.entrar(self.operador)
        for url in (
            reverse('principal:equipe_pedidos'), reverse('principal:equipe_pedido_detalhe', args=[self.pedido.pk]),
        ):
            self.assertEqual(http.post(url).status_code, 405)


class AreaDoClienteTests(Dados, TestCase):

    def setUp(self):
        self.criar_dados()
        self.http = self.entrar(self.cliente)

    def test_lista_somente_pedidos_proprios_do_mais_recente(self):
        antigo = self.criar_pedido(minutos_atras=60)
        recente = self.criar_pedido(estado=E.EM_PREPARO)
        alheio = self.criar_pedido(cliente=self.outro_cliente)

        resposta = self.http.get(reverse('principal:meus_pedidos'))
        self.assertEqual([p.pk for p in resposta.context['pedidos']], [recente.pk, antigo.pk])
        self.assertNotContains(resposta, f'Pedido {alheio.pk}<')
        self.assertNotContains(resposta, reverse('principal:acompanhamento_pedido', args=[alheio.pk]))
        for texto in (
            f'Pedido {recente.pk}', 'Em preparo', 'R$ 36,70',
            timezone.localtime(antigo.criado_em).strftime('%d/%m/%Y %H:%M'),
        ):
            self.assertContains(resposta, texto)

    def test_lista_vazia(self):
        self.criar_pedido(cliente=self.outro_cliente)
        self.assertContains(self.http.get(reverse('principal:meus_pedidos')), 'Você ainda não possui pedidos.')

    def test_detalhe_do_proprio_pedido(self):
        pedido = self.criar_pedido()
        resposta = self.http.get(reverse('principal:acompanhamento_pedido', args=[pedido.pk]))
        for texto in (
            'Acompanhamento do pedido', 'Arroz historico de teste', 'pacote historico', 'R$ 12,50',
            'R$ 25,00', 'R$ 36,70', 'Rua de teste', 'Bairro A de teste', 'telefone de teste', 'Recebido',
        ):
            self.assertContains(resposta, texto)
        self.assertIn('no-cache', resposta['Cache-Control'])
        confirmacao = self.http.get(reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertContains(confirmacao, 'Pedido registrado')

    def test_pedido_de_outro_cliente_retorna_404_sem_dados(self):
        alheio = self.criar_pedido(cliente=self.outro_cliente)
        Pedido.objects.filter(pk=alheio.pk).update(logradouro='Rua secreta de teste')
        for nome in ('acompanhamento_pedido', 'confirmacao_pedido'):
            with self.subTest(rota=nome):
                resposta = self.http.get(reverse(f'principal:{nome}', args=[alheio.pk]))
                self.assertEqual(resposta.status_code, 404)
                self.assertNotContains(resposta, 'Rua secreta de teste', status_code=404)

    def test_visitante_e_direcionado_ao_login(self):
        pedido = self.criar_pedido()
        for url in (reverse('principal:meus_pedidos'), reverse('principal:acompanhamento_pedido', args=[pedido.pk])):
            with self.subTest(url=url):
                self.assertRedirects(
                    Client().get(url), f"{reverse('principal:login')}?next={url}", fetch_redirect_response=False,
                )

    def test_novo_estado_aparece_ao_recarregar(self):
        pedido = self.criar_pedido()
        url = reverse('principal:acompanhamento_pedido', args=[pedido.pk])
        self.assertContains(self.http.get(url), 'Recebido')
        for atual, novo in ((E.RECEBIDO, E.CONFIRMADO), (E.CONFIRMADO, E.CANCELADO)):
            pedidos.alterar_estado(usuario=self.operador, pedido_id=pedido.pk, estado_esperado=atual, novo_estado=novo)
            resposta = self.http.get(url)
            self.assertEqual(resposta.context['pedido'].estado, novo)
            self.assertContains(resposta, EstadoPedido(novo).label)
            self.assertEqual(
                self.http.get(reverse('principal:meus_pedidos')).context['pedidos'][0].estado, novo,
            )

    def test_cliente_nao_ve_acoes_administrativas(self):
        pedido = self.criar_pedido()
        for url in (reverse('principal:meus_pedidos'), reverse('principal:acompanhamento_pedido', args=[pedido.pk])):
            resposta = self.http.get(url)
            self.assertNotContains(resposta, 'name="novo_estado"')
            self.assertNotContains(resposta, reverse('principal:equipe_alterar_estado', args=[pedido.pk]))
            self.assertNotContains(resposta, reverse('principal:equipe_pedidos'))

    def test_post_direto_do_cliente_retorna_403(self):
        pedido = self.criar_pedido()
        antes = self.retrato(pedido)
        for novo in (E.CANCELADO, E.CONFIRMADO, E.ENTREGUE):
            with self.subTest(novo=novo):
                resposta = self.alterar(self.http, pedido, E.RECEBIDO, novo)
                self.assertContains(resposta, MSG_SEM_PERMISSAO, status_code=403)
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.RECEBIDO)
        self.assertEqual(self.retrato(pedido), antes)
        self.assertEqual(self.http.post(reverse('principal:acompanhamento_pedido', args=[pedido.pk])).status_code, 405)


MSG_PEDIDO_NAO_ENCONTRADO = 'Pedido não encontrado ou acesso não permitido.'
MSG_ENTRE_PARA_PEDIDOS = 'Entre para consultar seus pedidos.'


def sem_tokens_csrf(conteudo):
    """Remove os valores de CSRF, que mudam a cada renderização, para comparar páginas."""
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', 'name="csrfmiddlewaretoken"', conteudo)


class PedidoNaoEncontradoTests(Dados, TestCase):
    """S9-02: pedido inexistente ou alheio responde 404 com a mesma mensagem, sem dados."""

    def setUp(self):
        self.criar_dados()
        self.http = self.entrar(self.cliente)
        self.alheio = self.criar_pedido(cliente=self.outro_cliente)
        Pedido.objects.filter(pk=self.alheio.pk).update(logradouro='Rua secreta de teste', telefone='tel secreto')

    def test_inexistente_alheio_e_gigante_tem_resposta_identica(self):
        for nome in ('acompanhamento_pedido', 'confirmacao_pedido'):
            corpos = []
            for identificador in (self.alheio.pk, 999999, 10 ** 30):
                with self.subTest(rota=nome, identificador=identificador):
                    resposta = self.http.get(reverse(f'principal:{nome}', args=[identificador]))
                    self.assertEqual(resposta.status_code, 404)
                    self.assertTemplateUsed(resposta, 'principal/pedido_nao_encontrado.html')
                    self.assertContains(resposta, MSG_PEDIDO_NAO_ENCONTRADO, status_code=404)
                    for dado in ('Rua secreta de teste', 'tel secreto', self.outro_cliente.username,
                                 str(self.alheio.total).replace('.', ',')):
                        self.assertNotContains(resposta, dado, status_code=404)
                    corpos.append(sem_tokens_csrf(resposta.content.decode()))
            # Nada distingue um pedido alheio existente de um identificador inexistente.
            self.assertEqual(len(set(corpos)), 1)

    def test_pedido_proprio_continua_acessivel(self):
        proprio = self.criar_pedido()
        for nome in ('acompanhamento_pedido', 'confirmacao_pedido'):
            self.assertEqual(self.http.get(reverse(f'principal:{nome}', args=[proprio.pk])).status_code, 200)


class MensagemLoginMeusPedidosTests(Dados, TestCase):
    """S9-03: visitante em Meus pedidos vê a mensagem prevista no login, somente nesse caso."""

    def setUp(self):
        self.criar_dados()
        self.cliente.set_password('Chuva!Telhado42Mar')
        self.cliente.save()

    def test_visitante_em_meus_pedidos_recebe_a_mensagem_e_volta_ao_destino(self):
        url = reverse('principal:meus_pedidos')
        resposta = self.client.get(url, follow=True)
        self.assertEqual(resposta.redirect_chain, [(f"{reverse('principal:login')}?next={url}", 302)])
        self.assertEqual(resposta.content.decode().count(MSG_ENTRE_PARA_PEDIDOS), 1)
        self.assertContains(resposta, f'name="next" value="{url}"')

        login = self.client.post(
            f"{reverse('principal:login')}?next={url}",
            {'username': self.cliente.username, 'password': 'Chuva!Telhado42Mar', 'next': url},
        )
        self.assertRedirects(login, url)

    def test_mensagem_nao_se_acumula_em_recargas(self):
        url_login = f"{reverse('principal:login')}?next={reverse('principal:meus_pedidos')}"
        for _ in range(3):
            self.assertEqual(self.client.get(url_login).content.decode().count(MSG_ENTRE_PARA_PEDIDOS), 1)

    def test_outras_rotas_nao_recebem_a_mensagem(self):
        pedido = self.criar_pedido()
        for url in (
            reverse('principal:minha_conta'), reverse('principal:checkout'),
            reverse('principal:equipe_pedidos'), reverse('principal:acompanhamento_pedido', args=[pedido.pk]),
        ):
            with self.subTest(url=url):
                resposta = self.client.get(url, follow=True)
                self.assertTemplateUsed(resposta, 'registration/login.html')
                self.assertNotContains(resposta, MSG_ENTRE_PARA_PEDIDOS)
        self.assertNotContains(self.client.get(reverse('principal:login')), MSG_ENTRE_PARA_PEDIDOS)

    def test_next_externo_nao_dispara_a_mensagem_nem_redireciona_para_fora(self):
        for destino in ('https://externo.example/pedidos/', '//externo.example/pedidos/',
                        'http://testserver.evil/pedidos/'):
            with self.subTest(destino=destino):
                url_login = f"{reverse('principal:login')}?next={destino}"
                self.assertNotContains(self.client.get(url_login), MSG_ENTRE_PARA_PEDIDOS)
                login = Client().post(url_login, {
                    'username': self.cliente.username, 'password': 'Chuva!Telhado42Mar', 'next': destino,
                })
                self.assertRedirects(login, reverse('principal:minha_conta'), fetch_redirect_response=False)


class ConcorrenciaTransicoesTests(Dados, TransactionTestCase):
    """Requisições simultâneas a partir do mesmo estado: no máximo uma transição é efetivada."""

    def setUp(self):
        self.criar_dados()

    def disputar(self, acoes):
        """Executa as ações do serviço em threads liberadas ao mesmo tempo por uma barreira."""
        barreira = threading.Barrier(len(acoes))
        resultados = {}

        def executar(indice, usuario, pedido_id, esperado, novo):
            try:
                barreira.wait(10)
                resultado = pedidos.alterar_estado(
                    usuario=usuario, pedido_id=pedido_id, estado_esperado=esperado, novo_estado=novo,
                )
                resultados[indice] = ('ok', resultado.novo)
            except pedidos.ErroPedido as erro:
                resultados[indice] = (type(erro).__name__, None)
            finally:
                fechar_conexoes_da_thread()

        threads = [
            threading.Thread(target=executar, args=(indice, *acao)) for indice, acao in enumerate(acoes)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        return [resultados[indice] for indice in range(len(acoes))]

    def test_mesma_acao_simultanea_avanca_uma_unica_vez(self):
        for rodada in range(5):
            with self.subTest(rodada=rodada):
                pedido = self.criar_pedido()
                antes = self.retrato(pedido)
                resultados = self.disputar([
                    (self.operador, pedido.pk, E.RECEBIDO, E.CONFIRMADO),
                    (self.superusuario, pedido.pk, E.RECEBIDO, E.CONFIRMADO),
                ])
                self.assertEqual([r[0] for r in resultados].count('ok'), 1, resultados)
                self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.CONFIRMADO)
                self.assertEqual(self.retrato(pedido), antes)

    def test_acoes_diferentes_simultaneas_a_partir_do_mesmo_estado(self):
        for rodada in range(5):
            with self.subTest(rodada=rodada):
                pedido = self.criar_pedido()
                resultados = self.disputar([
                    (self.operador, pedido.pk, E.RECEBIDO, E.CONFIRMADO),
                    (self.superusuario, pedido.pk, E.RECEBIDO, E.CANCELADO),
                ])
                vencedores = [r[1] for r in resultados if r[0] == 'ok']
                self.assertEqual(len(vencedores), 1, resultados)
                self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, vencedores[0])
