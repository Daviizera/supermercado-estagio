"""Testes-piloto (Semana 11, Atividade 11): fluxos completos sobre os dados de demonstração.

Rodam no banco de testes do Django, com o catálogo criado pelo comando
preparar_dados_demonstracao. O checkout usa o bairro e a taxa fictícios já empregados nos
testes de checkout (BAIRRO_TESTE e TAXA_TESTE); esses valores pertencem ao cenário de testes
e não representam parâmetros reais de entrega.
Os valores esperados são calculados aqui, de forma independente, a partir dos preços do banco.
"""
from io import StringIO

from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.cache import caches
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from . import checkout as servico_checkout
from . import pedidos as servico_pedidos
from .carrinho import CHAVE_SESSAO
from .management.commands.preparar_dados_demonstracao import PRODUTOS_DEMONSTRACAO
from .models import Categoria, EstadoPedido as E, Pedido, Produto
from .test_checkout import BAIRRO_TESTE, TAXA_TESTE

SENHA = 'Ficticia!Piloto2026Sol'
ENTREGA = {
    'logradouro': 'Rua Fictícia da Demonstração', 'numero': '100', 'complemento': 'Casa de teste',
    'bairro': BAIRRO_TESTE, 'telefone': 'telefone fictício',
}
checkout_configurado = override_settings(CHECKOUT_BAIRROS_ATENDIDOS=(BAIRRO_TESTE,), CHECKOUT_TAXA_ENTREGA=TAXA_TESTE)


def mensagens(resposta):
    return [str(m) for m in get_messages(resposta.wsgi_request)]


def reais(valor):
    return 'R$ ' + f'{valor:.2f}'.replace('.', ',')


class Piloto(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('preparar_dados_demonstracao', stdout=StringIO())
        cls.produtos = {p.nome: p for p in Produto.objects.select_related('categoria')}
        cls.arroz = cls.produtos['Arroz branco tipo 1']
        cls.feijao = cls.produtos['Feijão carioca']
        cls.detergente = cls.produtos['Detergente líquido neutro']
        cls.banana = cls.produtos['Banana prata']

    def setUp(self):
        caches['limite_login'].clear()

    def cliente(self, nome='cliente_piloto'):
        return get_user_model().objects.create_user(nome, password=SENHA)

    def entrar(self, usuario):
        resposta = self.client.post(reverse('principal:login'), {'username': usuario.username, 'password': SENHA})
        self.assertRedirects(resposta, reverse('principal:minha_conta'))

    def adicionar(self, produto, quantidade):
        return self.client.post(reverse('principal:adicionar_ao_carrinho', args=[produto.pk]), {'quantidade': str(quantidade)})


class Cenario1VisitanteTests(Piloto):
    def test_consulta_catalogo_pesquisa_filtros_e_detalhes(self):
        inicio = self.client.get(reverse('principal:inicio'))
        self.assertContains(inicio, f'href="{reverse("principal:catalogo")}"')

        catalogo = self.client.get(reverse('principal:catalogo'))
        self.assertEqual(len(catalogo.context['produtos']), len(PRODUTOS_DEMONSTRACAO))
        for categoria in Categoria.objects.all():
            self.assertContains(catalogo, f'<option value="{categoria.pk}">{categoria.nome}</option>', html=True)
        self.assertContains(catalogo, reais(self.arroz.preco))

        busca = self.client.get(reverse('principal:catalogo'), {'q': 'arroz'})
        self.assertEqual([p.nome for p in busca.context['produtos']], ['Arroz branco tipo 1'])

        limpeza = Categoria.objects.get(nome='Limpeza')
        filtro = self.client.get(reverse('principal:catalogo'), {'categoria': limpeza.pk})
        esperados = sorted(nome for categoria, nome, _, _ in PRODUTOS_DEMONSTRACAO if categoria == 'Limpeza')
        self.assertEqual(sorted(p.nome for p in filtro.context['produtos']), esperados)

        combinado = self.client.get(reverse('principal:catalogo'), {'q': 'Água', 'categoria': limpeza.pk})
        self.assertEqual([p.nome for p in combinado.context['produtos']], ['Água sanitária'])

        detalhe = self.client.get(reverse('principal:detalhe_produto', args=[self.feijao.pk]))
        for texto in (self.feijao.nome, 'Mercearia', self.feijao.unidade, reais(self.feijao.preco)):
            self.assertContains(detalhe, texto)

    def test_busca_ignora_caixa_e_acentos(self):
        # F-01 (encontrada neste piloto e corrigida): antes, "água", "óleo" e "FEIJÃO" não
        # encontravam nada, porque o LIKE do SQLite só ignora a caixa em letras ASCII.
        for termo, esperado in (
            ('água', 'Água sanitária'), ('agua', 'Água sanitária'), ('ÁGUA', 'Água sanitária'),
            ('sanitaria', 'Água sanitária'), ('óleo', 'Óleo de soja'), ('oleo', 'Óleo de soja'),
            ('FEIJAO', 'Feijão carioca'), ('FEIJÃO', 'Feijão carioca'), ('cafe', 'Café em grãos torra média'),
        ):
            with self.subTest(termo=termo):
                nomes = [p.nome for p in self.client.get(reverse('principal:catalogo'), {'q': termo}).context['produtos']]
                self.assertTrue(any(nome.startswith(esperado) for nome in nomes), nomes)

    def test_areas_protegidas_exigem_login(self):
        for nome, args in (('minha_conta', []), ('meus_pedidos', []), ('checkout', []),
                           ('acompanhamento_pedido', [1]), ('equipe_pedidos', [])):
            with self.subTest(pagina=nome):
                url = reverse(f'principal:{nome}', args=args)
                self.assertRedirects(self.client.get(url), f'{reverse("principal:login")}?next={url}',
                                     fetch_redirect_response=False)


class Cenario2CadastroAutenticacaoTests(Piloto):
    def test_cadastro_login_conta_e_logout(self):
        url = reverse('principal:cadastro')
        curta = self.client.post(url, {'username': 'cliente_novo_piloto', 'password1': 'Vbx!tqLm9Rz',
                                       'password2': 'Vbx!tqLm9Rz'})
        self.assertIn('password_too_short', [e.code for e in curta.context['form'].errors.as_data()['password2']])
        self.assertFalse(get_user_model().objects.filter(username='cliente_novo_piloto').exists())

        criado = self.client.post(url, {'username': 'cliente_novo_piloto', 'password1': SENHA, 'password2': SENHA})
        self.assertRedirects(criado, reverse('principal:login'))
        usuario = get_user_model().objects.get(username='cliente_novo_piloto')
        self.assertFalse(usuario.is_staff or usuario.is_superuser)

        self.entrar(usuario)
        self.assertContains(self.client.get(reverse('principal:minha_conta')), 'cliente_novo_piloto')

        saida = self.client.post(reverse('principal:logout'))
        self.assertRedirects(saida, reverse('principal:inicio'), fetch_redirect_response=False)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.get(reverse('principal:minha_conta')).status_code, 302)


class Cenario3CarrinhoTests(Piloto):
    def test_itens_quantidades_remocao_valores_e_logout(self):
        self.entrar(self.cliente())
        for produto, quantidade in ((self.arroz, 2), (self.feijao, 1), (self.detergente, 3)):
            self.assertRedirects(self.adicionar(produto, quantidade), reverse('principal:carrinho'))
        self.assertEqual(self.client.session[CHAVE_SESSAO],
                         {str(self.arroz.pk): 2, str(self.feijao.pk): 1, str(self.detergente.pk): 3})
        carrinho = self.client.get(reverse('principal:carrinho'))
        esperado = self.arroz.preco * 2 + self.feijao.preco + self.detergente.preco * 3
        self.assertEqual(carrinho.context['resumo'].subtotal, esperado)
        self.assertContains(carrinho, reais(esperado))

        self.client.post(reverse('principal:atualizar_item_carrinho', args=[self.feijao.pk]), {'quantidade': '4'})
        self.client.post(reverse('principal:remover_item_carrinho', args=[self.detergente.pk]))
        esperado = self.arroz.preco * 2 + self.feijao.preco * 4
        carrinho = self.client.get(reverse('principal:carrinho'))
        self.assertEqual(self.client.session[CHAVE_SESSAO], {str(self.arroz.pk): 2, str(self.feijao.pk): 4})
        self.assertEqual(carrinho.context['resumo'].subtotal, esperado)
        self.assertContains(carrinho, reais(esperado))

        for invalida in ('0', '-1', '1.5', 'abc', ''):
            with self.subTest(quantidade=invalida):
                resposta = self.client.post(reverse('principal:atualizar_item_carrinho', args=[self.arroz.pk]),
                                            {'quantidade': invalida})
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(self.client.session[CHAVE_SESSAO][str(self.arroz.pk)], 2)
                self.assertEqual(self.adicionar(self.banana, invalida).status_code, 200)
                self.assertNotIn(str(self.banana.pk), self.client.session[CHAVE_SESSAO])

        self.client.post(reverse('principal:logout'))
        self.assertNotIn(CHAVE_SESSAO, self.client.session)
        self.assertContains(self.client.get(reverse('principal:carrinho')), 'Seu carrinho está vazio.')


class Cenario4CheckoutTests(Piloto):
    def preparar_carrinho(self):
        self.usuario = self.cliente()
        self.entrar(self.usuario)
        self.adicionar(self.arroz, 2)
        self.adicionar(self.banana, 3)
        self.subtotal = self.arroz.preco * 2 + self.banana.preco * 3

    @override_settings(CHECKOUT_BAIRROS_ATENDIDOS=(), CHECKOUT_TAXA_ENTREGA=None)
    def test_sem_bairros_e_taxa_checkout_fica_bloqueado(self):
        self.preparar_carrinho()
        resposta = self.client.get(reverse('principal:checkout'))
        self.assertEqual(resposta.context['bloqueio'], servico_checkout.CheckoutIndisponivel.mensagem)
        self.assertNotContains(resposta, 'name="revisao"')

    @checkout_configurado
    def test_compra_completa_com_valores_do_servidor_e_sem_duplicidade(self):
        self.preparar_carrinho()
        revisao = self.client.get(reverse('principal:checkout'))
        total = self.subtotal + TAXA_TESTE
        for valor in (self.subtotal, TAXA_TESTE, total):
            self.assertContains(revisao, reais(valor))
        token = revisao.context['token']

        dados = {**ENTREGA, 'revisao': token, 'total': '0.01', 'subtotal': '0.01', 'taxa_entrega': '0', 'estado': 'entregue'}
        resposta = self.client.post(reverse('principal:checkout'), dados)
        pedido = Pedido.objects.get()
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertIn('Pedido registrado com sucesso.', mensagens(resposta))
        self.assertEqual((pedido.cliente, pedido.estado), (self.usuario, E.RECEBIDO))
        self.assertEqual((pedido.subtotal, pedido.taxa_entrega, pedido.total), (self.subtotal, TAXA_TESTE, total))
        self.assertEqual((pedido.logradouro, pedido.bairro, pedido.pagamento), (ENTREGA['logradouro'], BAIRRO_TESTE, 'na_entrega'))
        itens = {i.nome_produto: (i.quantidade, i.preco_unitario, i.unidade) for i in pedido.itens.all()}
        self.assertEqual(itens, {
            self.arroz.nome: (2, self.arroz.preco, self.arroz.unidade),
            self.banana.nome: (3, self.banana.preco, self.banana.unidade),
        })
        self.assertNotIn(CHAVE_SESSAO, self.client.session)

        repetido = self.client.post(reverse('principal:checkout'), {**ENTREGA, 'revisao': token})
        self.assertRedirects(repetido, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertEqual(Pedido.objects.count(), 1)

    @checkout_configurado
    def test_endereco_invalido_nao_cria_pedido(self):
        self.preparar_carrinho()
        token = self.client.get(reverse('principal:checkout')).context['token']
        resposta = self.client.post(reverse('principal:checkout'), {**ENTREGA, 'numero': '', 'bairro': 'Bairro não atendido',
                                                                    'revisao': token})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(set(resposta.context['form'].errors), {'numero', 'bairro'})
        self.assertEqual(Pedido.objects.count(), 0)


@checkout_configurado
class Cenario5e6AcompanhamentoEquipeTests(Piloto):
    def comprar(self, usuario):
        self.client.force_login(usuario)
        self.adicionar(self.arroz, 1)
        self.adicionar(self.feijao, 2)
        token = self.client.get(reverse('principal:checkout')).context['token']
        self.client.post(reverse('principal:checkout'), {**ENTREGA, 'revisao': token})
        self.client.logout()
        return Pedido.objects.filter(cliente=usuario).get()

    def test_cliente_acompanha_somente_o_proprio_pedido(self):
        dono, outro = self.cliente(), self.cliente('outro_cliente_piloto')
        pedido = self.comprar(dono)
        self.client.force_login(dono)
        lista = self.client.get(reverse('principal:meus_pedidos'))
        self.assertEqual(list(lista.context['pedidos']), [pedido])
        detalhe = self.client.get(reverse('principal:acompanhamento_pedido', args=[pedido.pk]))
        for texto in (self.arroz.nome, self.feijao.nome, reais(pedido.subtotal), reais(pedido.total), 'Recebido'):
            self.assertContains(detalhe, texto)
        self.client.force_login(outro)
        for pk in (pedido.pk, pedido.pk + 100):
            with self.subTest(pk=pk):
                resposta = self.client.get(reverse('principal:acompanhamento_pedido', args=[pk]))
                self.assertEqual(resposta.status_code, 404)
                self.assertNotContains(resposta, ENTREGA['logradouro'], status_code=404)

    def test_equipe_conduz_o_pedido_ate_a_entrega(self):
        pedido = self.comprar(self.cliente())
        operador = get_user_model().objects.create_user('equipe_piloto', password=None, is_staff=True)
        operador.user_permissions.add(*Permission.objects.filter(codename__in=('view_pedido', 'change_pedido')))
        self.client.force_login(operador)
        self.assertContains(self.client.get(reverse('principal:equipe_pedidos')), f'Pedido {pedido.pk}')
        detalhe = self.client.get(reverse('principal:equipe_pedido_detalhe', args=[pedido.pk]))
        self.assertContains(detalhe, ENTREGA['logradouro'])
        self.assertContains(detalhe, 'Confirmar pedido')

        url = reverse('principal:equipe_alterar_estado', args=[pedido.pk])
        for anterior, novo in ((E.RECEBIDO, E.CONFIRMADO), (E.CONFIRMADO, E.EM_PREPARO),
                               (E.EM_PREPARO, E.SAIU_PARA_ENTREGA), (E.SAIU_PARA_ENTREGA, E.ENTREGUE)):
            resposta = self.client.post(url, {'estado_atual': anterior, 'novo_estado': novo})
            self.assertIn(f'Pedido {pedido.pk}: {E(anterior).label} → {E(novo).label}.', mensagens(resposta))
            pedido.refresh_from_db()
            self.assertEqual(pedido.estado, novo)

        invalida = self.client.post(url, {'estado_atual': E.ENTREGUE, 'novo_estado': E.CANCELADO})
        self.assertIn(servico_pedidos.MENSAGEM_TRANSICAO_INVALIDA, mensagens(invalida))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, E.ENTREGUE)
        self.assertEqual((pedido.subtotal, pedido.total), (self.arroz.preco + self.feijao.preco * 2,
                                                           self.arroz.preco + self.feijao.preco * 2 + TAXA_TESTE))

    def test_cliente_e_equipe_sem_permissao_de_alteracao_sao_bloqueados(self):
        pedido = self.comprar(self.cliente())
        consulta = get_user_model().objects.create_user('equipe_consulta_piloto', password=None, is_staff=True)
        consulta.user_permissions.add(Permission.objects.get(codename='view_pedido'))
        cliente = get_user_model().objects.get(username='cliente_piloto')
        url = reverse('principal:equipe_alterar_estado', args=[pedido.pk])
        for usuario in (cliente, consulta):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                resposta = self.client.post(url, {'estado_atual': E.RECEBIDO, 'novo_estado': E.CONFIRMADO})
                self.assertEqual(resposta.status_code, 403)
                pedido.refresh_from_db()
                self.assertEqual(pedido.estado, E.RECEBIDO)
        self.client.force_login(cliente)
        self.assertEqual(self.client.get(reverse('principal:equipe_pedidos')).status_code, 403)
        self.client.force_login(consulta)
        self.assertNotContains(self.client.get(reverse('principal:equipe_pedido_detalhe', args=[pedido.pk])),
                               'name="novo_estado"')
