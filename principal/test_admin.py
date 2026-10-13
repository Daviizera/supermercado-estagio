from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from .models import Categoria, Produto


class CadastroAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        usuario = get_user_model()
        cls.administrador = usuario.objects.create_superuser(
            username='administrador_teste', password=None,
        )
        cls.cliente = usuario.objects.create_user(
            username='cliente_teste', password=None,
        )
        cls.equipe_sem_permissoes = usuario.objects.create_user(
            username='equipe_teste', password=None, is_staff=True,
        )
        cls.equipe_consulta = usuario.objects.create_user(
            username='consulta_teste', password=None, is_staff=True,
        )
        cls.equipe_consulta.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label='principal',
                codename__in=('view_categoria', 'view_produto'),
            )
        )
        cls.categoria = Categoria.objects.create(nome='Categoria de teste Alfa')
        cls.outra_categoria = Categoria.objects.create(nome='Categoria de teste Beta')
        cls.produto = Produto.objects.create(
            categoria=cls.categoria,
            nome='Produto de teste Alfa',
            preco=Decimal('10.50'),
            unidade='unidade de teste',
            ativo=True,
        )
        cls.outro_produto = Produto.objects.create(
            categoria=cls.outra_categoria,
            nome='Produto de teste Beta',
            preco=Decimal('20.00'),
            unidade='pacote de teste',
            ativo=False,
        )

    def setUp(self):
        # Os usuários temporários têm senha inutilizável; force_login() permite
        # testar autorização sem passar pela autenticação por senha.
        self.client.force_login(self.administrador)

    def dados_produto(self, **alteracoes):
        dados = {
            'categoria': self.categoria.pk,
            'nome': 'Novo produto de teste',
            'preco': '12.50',
            'unidade': 'unidade de teste',
            'ativo': 'on',
            '_save': 'Salvar',
        }
        dados.update(alteracoes)
        return dados

    def test_visitante_e_redirecionado_e_pagina_de_login_disponivel(self):
        self.client.logout()

        resposta = self.client.get(reverse('admin:index'))

        self.assertRedirects(
            resposta,
            reverse('admin:login') + '?next=' + reverse('admin:index'),
        )
        login = self.client.get(reverse('admin:login'))
        self.assertEqual(login.status_code, 200)
        self.assertTemplateUsed(login, 'admin/login.html')

    def test_superusuario_acessa_cadastros_e_pedidos_nao_sao_expostos(self):
        resposta = self.client.get(reverse('admin:index'))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, reverse('admin:principal_categoria_changelist'))
        self.assertContains(resposta, reverse('admin:principal_produto_changelist'))
        for modelo in ('pedido', 'itempedido'):
            with self.subTest(modelo=modelo):
                self.assertNotContains(resposta, '/admin/principal/' + modelo + '/')
                with self.assertRaises(NoReverseMatch):
                    reverse('admin:principal_' + modelo + '_changelist')

    def test_cliente_sem_staff_nao_acessa_nem_altera_cadastros(self):
        self.client.force_login(self.cliente)
        for modelo, objeto, dados in (
            ('categoria', self.categoria, {'nome': 'Alteracao sem permissao'}),
            ('produto', self.produto, self.dados_produto()),
        ):
            for operacao in ('changelist', 'add', 'change', 'delete'):
                argumentos = (objeto.pk,) if operacao in ('change', 'delete') else ()
                url = reverse('admin:principal_' + modelo + '_' + operacao, args=argumentos)
                with self.subTest(modelo=modelo, operacao=operacao):
                    self.assertEqual(self.client.get(url).status_code, 302)
                    if operacao != 'changelist':
                        self.assertEqual(self.client.post(url, dados).status_code, 302)

        self.assertEqual(Categoria.objects.count(), 2)
        self.assertEqual(Produto.objects.count(), 2)
        self.categoria.refresh_from_db()
        self.produto.refresh_from_db()
        self.assertEqual(self.categoria.nome, 'Categoria de teste Alfa')
        self.assertEqual(self.produto.nome, 'Produto de teste Alfa')

    def test_staff_sem_permissoes_recebe_403_nos_cadastros(self):
        self.client.force_login(self.equipe_sem_permissoes)
        for modelo, objeto, dados in (
            ('categoria', self.categoria, {'nome': 'Alteracao sem permissao'}),
            ('produto', self.produto, self.dados_produto()),
        ):
            for operacao in ('changelist', 'add', 'change', 'delete'):
                argumentos = (objeto.pk,) if operacao in ('change', 'delete') else ()
                url = reverse('admin:principal_' + modelo + '_' + operacao, args=argumentos)
                with self.subTest(modelo=modelo, operacao=operacao):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    if operacao != 'changelist':
                        self.assertEqual(self.client.post(url, dados).status_code, 403)

        self.assertEqual(Categoria.objects.count(), 2)
        self.assertEqual(Produto.objects.count(), 2)
        self.categoria.refresh_from_db()
        self.produto.refresh_from_db()
        self.assertEqual(self.categoria.nome, 'Categoria de teste Alfa')
        self.assertEqual(self.produto.nome, 'Produto de teste Alfa')

    def test_permissao_de_consulta_nao_permite_escrita(self):
        self.client.force_login(self.equipe_consulta)
        for modelo, objeto, dados in (
            ('categoria', self.categoria, {'nome': 'Alteracao sem permissao'}),
            ('produto', self.produto, self.dados_produto()),
        ):
            with self.subTest(modelo=modelo):
                lista = reverse('admin:principal_' + modelo + '_changelist')
                edicao = reverse('admin:principal_' + modelo + '_change', args=(objeto.pk,))
                cadastro = reverse('admin:principal_' + modelo + '_add')
                exclusao = reverse('admin:principal_' + modelo + '_delete', args=(objeto.pk,))
                self.assertEqual(self.client.get(lista).status_code, 200)
                self.assertEqual(self.client.get(edicao).status_code, 200)
                self.assertEqual(self.client.get(cadastro).status_code, 403)
                self.assertEqual(self.client.get(exclusao).status_code, 403)
                for url in (cadastro, edicao, exclusao):
                    self.assertEqual(self.client.post(url, dados).status_code, 403)

        self.assertEqual(Categoria.objects.count(), 2)
        self.assertEqual(Produto.objects.count(), 2)
        self.categoria.refresh_from_db()
        self.produto.refresh_from_db()
        self.assertEqual(self.categoria.nome, 'Categoria de teste Alfa')
        self.assertEqual(self.produto.nome, 'Produto de teste Alfa')

    def test_cadastro_consulta_e_edicao_de_categoria(self):
        lista = reverse('admin:principal_categoria_changelist')
        resposta = self.client.post(
            reverse('admin:principal_categoria_add'),
            {'nome': 'Nova categoria de teste', '_save': 'Salvar'},
        )

        self.assertRedirects(resposta, lista)
        categoria = Categoria.objects.get(nome='Nova categoria de teste')
        self.assertContains(self.client.get(lista), categoria.nome)
        edicao = reverse('admin:principal_categoria_change', args=(categoria.pk,))
        self.assertEqual(self.client.get(edicao).status_code, 200)
        resposta = self.client.post(edicao, {'nome': 'Categoria renomeada', '_save': 'Salvar'})
        self.assertRedirects(resposta, lista)
        categoria.refresh_from_db()
        self.assertEqual(categoria.nome, 'Categoria renomeada')
        self.assertEqual(Categoria.objects.count(), 3)

    def test_categoria_duplicada_nao_e_cadastrada(self):
        resposta = self.client.post(
            reverse('admin:principal_categoria_add'),
            {'nome': self.categoria.nome, '_save': 'Salvar'},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn('nome', resposta.context['adminform'].form.errors)
        self.assertEqual(Categoria.objects.count(), 2)

    def test_cadastro_consulta_e_edicao_de_produto(self):
        lista = reverse('admin:principal_produto_changelist')
        resposta = self.client.post(reverse('admin:principal_produto_add'), self.dados_produto())

        self.assertRedirects(resposta, lista)
        produto = Produto.objects.get(nome='Novo produto de teste')
        self.assertEqual(produto.categoria, self.categoria)
        self.assertEqual(produto.preco, Decimal('12.50'))
        self.assertEqual(produto.unidade, 'unidade de teste')
        self.assertTrue(produto.ativo)
        self.assertContains(self.client.get(lista), produto.nome)
        edicao = reverse('admin:principal_produto_change', args=(produto.pk,))
        self.assertEqual(self.client.get(edicao).status_code, 200)
        dados = self.dados_produto(nome='Produto atualizado', preco='15.75', unidade='pacote')
        dados.pop('ativo')
        resposta = self.client.post(edicao, dados)
        self.assertRedirects(resposta, lista)
        produto.refresh_from_db()
        self.assertEqual(produto.nome, 'Produto atualizado')
        self.assertEqual(produto.preco, Decimal('15.75'))
        self.assertEqual(produto.unidade, 'pacote')
        self.assertFalse(produto.ativo)
        self.assertEqual(Produto.objects.count(), 3)

    def test_precos_invalidos_nao_sao_cadastrados(self):
        for preco in ('-0.01', '1.234', 'invalido'):
            with self.subTest(preco=preco):
                resposta = self.client.post(
                    reverse('admin:principal_produto_add'), self.dados_produto(preco=preco),
                )

                self.assertEqual(resposta.status_code, 200)
                self.assertIn('preco', resposta.context['adminform'].form.errors)
                self.assertEqual(Produto.objects.count(), 2)

    def test_pesquisa_por_nome_nos_cadastros(self):
        for modelo, objeto in (('categoria', self.categoria), ('produto', self.produto)):
            with self.subTest(modelo=modelo):
                resposta = self.client.get(
                    reverse('admin:principal_' + modelo + '_changelist'), {'q': objeto.nome},
                )

                self.assertEqual(resposta.status_code, 200)
                self.assertQuerySetEqual(
                    resposta.context['cl'].queryset, [objeto.pk], transform=lambda registro: registro.pk,
                )

    def test_filtros_de_categoria_e_atividade(self):
        for parametros, esperado in (
            ({'categoria__id__exact': self.categoria.pk}, self.produto),
            ({'ativo__exact': '0'}, self.outro_produto),
            ({'ativo__exact': '1'}, self.produto),
        ):
            with self.subTest(parametros=parametros):
                resposta = self.client.get(reverse('admin:principal_produto_changelist'), parametros)

                self.assertEqual(resposta.status_code, 200)
                self.assertQuerySetEqual(
                    resposta.context['cl'].queryset, [esperado.pk], transform=lambda registro: registro.pk,
                )

    def test_listagens_ordenadas_por_nome(self):
        for modelo in ('categoria', 'produto'):
            with self.subTest(modelo=modelo):
                resposta = self.client.get(reverse('admin:principal_' + modelo + '_changelist'))

                self.assertEqual(resposta.status_code, 200)
                nomes = list(resposta.context['cl'].queryset.values_list('nome', flat=True))
                self.assertEqual(nomes, sorted(nomes))

    def test_categoria_com_produto_nao_pode_ser_excluida(self):
        url = reverse('admin:principal_categoria_delete', args=(self.categoria.pk,))
        confirmacao = self.client.get(url)

        self.assertEqual(confirmacao.status_code, 200)
        self.assertTrue(confirmacao.context['protected'])
        resposta = self.client.post(url, {'post': 'yes'})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(Categoria.objects.filter(pk=self.categoria.pk).exists())
        self.assertTrue(Produto.objects.filter(pk=self.produto.pk, categoria=self.categoria).exists())
