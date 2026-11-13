from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Categoria, Produto


class CatalogoTests(TestCase):
    """Consulta as rotas públicas com cadastros restritos ao banco de testes."""

    @classmethod
    def setUpTestData(cls):
        cls.alimentos = Categoria.objects.create(nome='Alimentos de teste')
        cls.bebidas = Categoria.objects.create(nome='Bebidas de teste')
        cls.vazia = Categoria.objects.create(nome='Categoria vazia de teste')
        cls.somente_inativos = Categoria.objects.create(nome='Categoria sem ativos de teste')
        cls.arroz = Produto.objects.create(
            categoria=cls.alimentos, nome='Arroz de teste',
            preco=Decimal('12.50'), unidade='pacote de teste',
        )
        cls.outro_arroz = Produto.objects.create(
            categoria=cls.alimentos, nome='Arroz de teste',
            preco=Decimal('20.25'), unidade='pacote maior de teste',
        )
        cls.leite = Produto.objects.create(
            categoria=cls.bebidas, nome='Leite de teste',
            preco=Decimal('6.70'), unidade='caixa de teste',
        )
        cls.leite_em_po = Produto.objects.create(
            categoria=cls.alimentos, nome='Leite em po de teste',
            preco=Decimal('15.80'), unidade='lata de teste',
        )
        cls.inativo = Produto.objects.create(
            categoria=cls.bebidas, nome='Leite indisponivel de teste',
            preco=Decimal('9.90'), unidade='embalagem oculta de teste', ativo=False,
        )
        cls.outro_inativo = Produto.objects.create(
            categoria=cls.somente_inativos, nome='Produto oculto de teste',
            preco=Decimal('3.00'), unidade='unidade oculta de teste', ativo=False,
        )
        cls.cliente = get_user_model().objects.create_user(
            username='cliente_catalogo_testes', password=None,
        )

    def assert_produtos(self, resposta, esperados):
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            [produto.pk for produto in resposta.context['produtos']],
            [produto.pk for produto in esperados],
        )

    def test_visitante_consulta_catalogo_com_dados_e_links_dos_produtos_ativos(self):
        resposta = self.client.get(reverse('principal:catalogo'))

        self.assert_produtos(resposta, [self.arroz, self.outro_arroz, self.leite, self.leite_em_po])
        self.assertTemplateUsed(resposta, 'principal/catalogo.html')
        self.assertTemplateUsed(resposta, 'base.html')
        for texto in (self.arroz.nome, 'R$ 12,50', self.arroz.unidade, self.alimentos.nome):
            self.assertContains(resposta, texto)
        self.assertContains(resposta, reverse('principal:detalhe_produto', args=[self.arroz.pk]))
        self.assertNotContains(resposta, self.inativo.nome)
        self.assertNotContains(resposta, self.outro_inativo.nome)
        self.assertNotContains(resposta, reverse('principal:detalhe_produto', args=[self.inativo.pk]))

    def test_cliente_autenticado_consulta_catalogo_sem_receber_privilegios(self):
        self.client.force_login(self.cliente)
        resposta = self.client.get(reverse('principal:catalogo'))

        self.assert_produtos(resposta, [self.arroz, self.outro_arroz, self.leite, self.leite_em_po])
        self.assertEqual(resposta.wsgi_request.user.pk, self.cliente.pk)
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.is_staff)
        self.assertFalse(self.cliente.is_superuser)
        self.assertFalse(self.cliente.user_permissions.exists())

    def test_catalogo_sem_produtos_exibe_mensagem(self):
        Produto.objects.all().delete()
        resposta = self.client.get(reverse('principal:catalogo'))

        self.assert_produtos(resposta, [])
        self.assertContains(resposta, 'Nenhum produto disponível no momento.')

    def test_catalogo_somente_com_inativos_exibe_mensagem_sem_expor_dados(self):
        Produto.objects.update(ativo=False)
        resposta = self.client.get(reverse('principal:catalogo'))

        self.assert_produtos(resposta, [])
        self.assertContains(resposta, 'Nenhum produto disponível no momento.')
        self.assertNotContains(resposta, self.arroz.nome)
        self.assertNotContains(resposta, self.inativo.nome)

    def test_ordenacao_por_nome_desempata_pelo_identificador(self):
        primeiro_por_nome = Produto.objects.create(
            categoria=self.alimentos, nome='Abacate de teste',
            preco=Decimal('2.00'), unidade='unidade de teste',
        )
        resposta = self.client.get(reverse('principal:catalogo'))

        self.assert_produtos(
            resposta, [primeiro_por_nome, self.arroz, self.outro_arroz, self.leite, self.leite_em_po],
        )

    def test_formulario_exibe_labels_e_categorias_inclusive_as_sem_produtos(self):
        resposta = self.client.get(reverse('principal:catalogo'))
        formulario = resposta.context['form']

        for nome in ('q', 'categoria'):
            self.assertContains(resposta, f'name="{nome}"')
            self.assertContains(resposta, f'for="{formulario[nome].id_for_label}"')
        for categoria in (self.alimentos, self.bebidas, self.vazia, self.somente_inativos):
            self.assertContains(resposta, f'value="{categoria.pk}"')
            self.assertContains(resposta, categoria.nome)
        self.assertContains(resposta, 'method="get"')

    def test_categoria_selecionada_restringe_a_produtos_ativos_dessa_categoria(self):
        resposta = self.client.get(
            reverse('principal:catalogo'), {'categoria': self.bebidas.pk},
        )

        self.assert_produtos(resposta, [self.leite])
        self.assertNotContains(resposta, self.leite_em_po.nome)
        self.assertNotContains(resposta, self.inativo.nome)
        self.assertEqual(resposta.context['form']['categoria'].value(), str(self.bebidas.pk))
        self.assertInHTML(
            f'<option value="{self.bebidas.pk}" selected>{self.bebidas.nome}</option>',
            resposta.content.decode(),
        )

    def test_categoria_sem_produtos_ativos_exibe_resultado_vazio(self):
        for categoria in (self.vazia, self.somente_inativos):
            with self.subTest(categoria=categoria.nome):
                resposta = self.client.get(
                    reverse('principal:catalogo'), {'categoria': categoria.pk},
                )
                self.assert_produtos(resposta, [])
                self.assertFalse(resposta.context['form'].errors)
                self.assertContains(resposta, 'Nenhum produto encontrado para os filtros informados.')
                self.assertNotContains(resposta, self.outro_inativo.nome)

    def test_categoria_invalida_nao_causa_erro_interno_nem_libera_catalogo_completo(self):
        for valor in ('inexistente', '0', '-1', str(self.somente_inativos.pk + 100), '9' * 80):
            with self.subTest(categoria=valor):
                resposta = self.client.get(reverse('principal:catalogo'), {'categoria': valor})

                self.assert_produtos(resposta, [])
                self.assertIn('categoria', resposta.context['form'].errors)
                self.assertContains(resposta, 'Corrija os filtros para consultar os produtos.')
                self.assertNotContains(resposta, self.arroz.nome)

    def test_remover_categoria_preserva_a_pesquisa(self):
        resposta = self.client.get(
            reverse('principal:catalogo'), {'q': 'leite', 'categoria': ''},
        )

        self.assert_produtos(resposta, [self.leite, self.leite_em_po])
        self.assertEqual(resposta.context['form']['q'].value(), 'leite')
        self.assertIsNone(resposta.context['form'].cleaned_data['categoria'])

    def test_pesquisa_parcial_ignora_caixa_ascii_e_espacos_externos(self):
        for termo in ('arro', 'ARRO', ' aRrO '):
            with self.subTest(termo=termo):
                resposta = self.client.get(reverse('principal:catalogo'), {'q': termo})
                self.assert_produtos(resposta, [self.arroz, self.outro_arroz])

    def test_pesquisa_aceita_150_caracteres_e_rejeita_excesso_sem_alterar_dados(self):
        produto = Produto.objects.create(
            categoria=self.alimentos, nome='A' * 150,
            preco=Decimal('1.00'), unidade='unidade de teste',
        )
        produtos_antes = list(Produto.objects.order_by('pk').values())
        url = reverse('principal:catalogo')

        valida = self.client.get(url, {'q': 'A' * 150})
        self.assert_produtos(valida, [produto])
        invalida = self.client.get(url, {'q': 'A' * 151, 'categoria': self.alimentos.pk})
        self.assert_produtos(invalida, [])
        self.assertIn('q', invalida.context['form'].errors)
        self.assertEqual(invalida.context['form']['categoria'].value(), str(self.alimentos.pk))
        self.assertContains(invalida, 'Corrija os filtros para consultar os produtos.')
        self.assertNotContains(invalida, self.arroz.nome)
        self.assertEqual(list(Produto.objects.order_by('pk').values()), produtos_antes)

    def test_pesquisa_sem_resultados_exibe_mensagem(self):
        resposta = self.client.get(reverse('principal:catalogo'), {'q': 'inexistente'})

        self.assert_produtos(resposta, [])
        self.assertContains(resposta, 'Nenhum produto encontrado para os filtros informados.')

    def test_pesquisa_vazia_retorna_todos_os_ativos(self):
        for termo in ('', '   '):
            with self.subTest(termo=termo):
                resposta = self.client.get(reverse('principal:catalogo'), {'q': termo})
                self.assert_produtos(resposta, [self.arroz, self.outro_arroz, self.leite, self.leite_em_po])

    def test_pesquisa_nao_expoe_produto_inativo_mesmo_com_nome_correspondente(self):
        resposta = self.client.get(reverse('principal:catalogo'), {'q': 'indisponivel'})

        self.assert_produtos(resposta, [])
        self.assertNotContains(resposta, self.inativo.nome)
        self.assertNotContains(resposta, self.inativo.unidade)

    def test_pesquisa_e_categoria_sao_combinadas_e_preservadas_no_formulario(self):
        resposta = self.client.get(
            reverse('principal:catalogo'), {'q': 'leite', 'categoria': self.bebidas.pk},
        )

        self.assert_produtos(resposta, [self.leite])
        self.assertNotContains(resposta, self.leite_em_po.nome)
        self.assertNotContains(resposta, self.inativo.nome)
        self.assertContains(resposta, 'value="leite"')
        self.assertInHTML(
            f'<option value="{self.bebidas.pk}" selected>{self.bebidas.nome}</option>',
            resposta.content.decode(),
        )

    def test_remover_apenas_pesquisa_mantem_categoria_selecionada(self):
        resposta = self.client.get(
            reverse('principal:catalogo'), {'q': '', 'categoria': self.alimentos.pk},
        )

        self.assert_produtos(resposta, [self.arroz, self.outro_arroz, self.leite_em_po])
        self.assertEqual(resposta.context['form']['categoria'].value(), str(self.alimentos.pk))
        self.assertEqual(resposta.context['form'].cleaned_data['q'], '')

    def test_limpeza_completa_dos_filtros_retorna_ao_catalogo_sem_query(self):
        url = reverse('principal:catalogo')
        filtrada = self.client.get(url, {'q': 'leite', 'categoria': self.bebidas.pk})

        self.assertContains(filtrada, 'Limpar filtros')
        self.assertContains(filtrada, f'href="{url}"')
        resposta = self.client.get(url)
        self.assert_produtos(resposta, [self.arroz, self.outro_arroz, self.leite, self.leite_em_po])
        self.assertFalse(resposta.context['filtros_ativos'])

    def test_detalhes_publicos_exibem_nome_categoria_preco_e_unidade(self):
        resposta = self.client.get(reverse('principal:detalhe_produto', args=[self.arroz.pk]))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'principal/detalhe_produto.html')
        self.assertTemplateUsed(resposta, 'base.html')
        self.assertEqual(resposta.context['produto'].pk, self.arroz.pk)
        for texto in (self.arroz.nome, self.alimentos.nome, 'R$ 12,50', self.arroz.unidade):
            self.assertContains(resposta, texto)
        self.assertContains(resposta, reverse('principal:catalogo'))

    def test_detalhes_de_inativo_ou_inexistente_retornam_404_sem_expor_dados(self):
        for pk in (self.inativo.pk, self.outro_inativo.pk + 100):
            with self.subTest(pk=pk):
                resposta = self.client.get(reverse('principal:detalhe_produto', args=[pk]))
                self.assertEqual(resposta.status_code, 404)
                self.assertNotContains(resposta, self.inativo.nome, status_code=404)
                self.assertNotContains(resposta, self.inativo.unidade, status_code=404)

    def test_consultas_nao_alteram_registros_e_post_nao_e_aceito(self):
        produtos_antes = list(Produto.objects.order_by('pk').values())
        categorias_antes = list(Categoria.objects.order_by('pk').values())
        for url in (
            reverse('principal:catalogo'),
            reverse('principal:detalhe_produto', args=[self.arroz.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, {'ativo': 'false'}).status_code, 200)
                self.assertEqual(self.client.head(url).status_code, 200)
                self.assertEqual(self.client.post(url, {'ativo': 'false'}).status_code, 405)
        self.assertEqual(list(Produto.objects.order_by('pk').values()), produtos_antes)
        self.assertEqual(list(Categoria.objects.order_by('pk').values()), categorias_antes)

    def test_navegacao_oferece_catalogo_e_preserva_autenticacao(self):
        url_catalogo = reverse('principal:catalogo')
        visitante = self.client.get(reverse('principal:inicio'))
        self.assertContains(visitante, f'href="{url_catalogo}"')
        self.assertContains(visitante, reverse('principal:login'))
        self.assertContains(visitante, reverse('principal:cadastro'))

        self.client.force_login(self.cliente)
        resposta = self.client.get(url_catalogo)
        self.assertContains(resposta, reverse('principal:minha_conta'))
        self.assertContains(resposta, 'action="' + reverse('principal:logout') + '"')
        detalhe = self.client.get(reverse('principal:detalhe_produto', args=[self.arroz.pk]))
        self.assertEqual(detalhe.status_code, 200)
        self.assertEqual(detalhe.wsgi_request.user.pk, self.cliente.pk)

    def test_mudancas_nos_modelos_atualizam_dados_e_disponibilidade_publicos(self):
        self.arroz.nome = 'Nome alterado de teste'
        self.arroz.preco = Decimal('23.40')
        self.arroz.unidade = 'nova unidade de teste'
        self.arroz.categoria = self.bebidas
        self.arroz.save()
        self.bebidas.nome = 'Categoria renomeada de teste'
        self.bebidas.save()

        url_catalogo = reverse('principal:catalogo')
        self.assert_produtos(
            self.client.get(url_catalogo, {'categoria': self.alimentos.pk}),
            [self.outro_arroz, self.leite_em_po],
        )
        self.assert_produtos(
            self.client.get(url_catalogo, {'categoria': self.bebidas.pk}),
            [self.leite, self.arroz],
        )

        for url in (
            reverse('principal:catalogo'),
            reverse('principal:detalhe_produto', args=[self.arroz.pk]),
        ):
            resposta = self.client.get(url)
            for texto in (self.arroz.nome, 'R$ 23,40', self.arroz.unidade, self.bebidas.nome):
                self.assertContains(resposta, texto)
        self.arroz.ativo = False
        self.arroz.save(update_fields=['ativo'])
        self.assertNotContains(self.client.get(reverse('principal:catalogo')), self.arroz.nome)
        self.assertEqual(
            self.client.get(reverse('principal:detalhe_produto', args=[self.arroz.pk])).status_code, 404,
        )
        self.inativo.ativo = True
        self.inativo.save(update_fields=['ativo'])
        self.assertContains(self.client.get(reverse('principal:catalogo')), self.inativo.nome)
        self.assertEqual(
            self.client.get(reverse('principal:detalhe_produto', args=[self.inativo.pk])).status_code, 200,
        )

    def test_cadastro_e_edicao_no_admin_refletem_no_catalogo_publico(self):
        administrador = get_user_model().objects.create_superuser(
            username='administrador_catalogo_testes', password=None,
        )
        cliente_admin = Client()
        cliente_admin.force_login(administrador)
        cadastro_categoria = cliente_admin.post(
            reverse('admin:principal_categoria_add'),
            {'nome': 'Categoria criada no Admin de teste', '_save': 'Salvar'},
        )
        self.assertRedirects(cadastro_categoria, reverse('admin:principal_categoria_changelist'))
        categoria = Categoria.objects.get(nome='Categoria criada no Admin de teste')
        dados = {
            'categoria': categoria.pk, 'nome': 'Produto criado no Admin de teste',
            'preco': '31.20', 'unidade': 'unidade admin de teste',
            'ativo': 'on', '_save': 'Salvar',
        }
        cadastro_produto = cliente_admin.post(reverse('admin:principal_produto_add'), dados)
        self.assertRedirects(cadastro_produto, reverse('admin:principal_produto_changelist'))
        produto = Produto.objects.get(nome=dados['nome'])
        self.assertContains(self.client.get(reverse('principal:catalogo')), produto.nome)

        dados.update(nome='Produto editado no Admin de teste', preco='32.30')
        edicao_produto = cliente_admin.post(
            reverse('admin:principal_produto_change', args=[produto.pk]), dados,
        )
        self.assertRedirects(edicao_produto, reverse('admin:principal_produto_changelist'))
        edicao_categoria = cliente_admin.post(
            reverse('admin:principal_categoria_change', args=[categoria.pk]),
            {'nome': 'Categoria editada no Admin de teste', '_save': 'Salvar'},
        )
        self.assertRedirects(edicao_categoria, reverse('admin:principal_categoria_changelist'))
        for url in (
            reverse('principal:catalogo'), reverse('principal:detalhe_produto', args=[produto.pk]),
        ):
            resposta = self.client.get(url)
            for texto in (dados['nome'], 'R$ 32,30', 'Categoria editada no Admin de teste'):
                self.assertContains(resposta, texto)

        dados.pop('ativo')
        inativacao = cliente_admin.post(
            reverse('admin:principal_produto_change', args=[produto.pk]), dados,
        )
        self.assertRedirects(inativacao, reverse('admin:principal_produto_changelist'))
        self.assertNotContains(self.client.get(reverse('principal:catalogo')), dados['nome'])
        self.assertEqual(
            self.client.get(reverse('principal:detalhe_produto', args=[produto.pk])).status_code, 404,
        )

    def test_quantidade_de_consultas_nao_cresce_ao_exibir_mais_produtos(self):
        Produto.objects.exclude(pk=self.arroz.pk).update(ativo=False)
        url = reverse('principal:catalogo')
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(url)
        self.assert_produtos(resposta, [self.arroz])

        Produto.objects.bulk_create([
            Produto(
                categoria=self.alimentos, nome=f'Produto adicional de teste {indice}',
                preco=Decimal('1.00'), unidade='unidade de teste',
            )
            for indice in range(5)
        ])
        # Aumentar a lista não deve disparar uma consulta por categoria de produto.
        with self.assertNumQueries(len(consultas)):
            resposta = self.client.get(url)
        self.assertEqual(len(resposta.context['produtos']), 6)
