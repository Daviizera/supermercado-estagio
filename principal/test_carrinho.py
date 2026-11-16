import copy
from decimal import Decimal
from importlib import import_module

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .carrinho import (
    CHAVE_SESSAO, Carrinho, ItemAusente, ItemInconsistente, ProdutoIndisponivel,
    QuantidadeAcimaDoLimite, QuantidadeInvalida, limite_tecnico_quantidade,
)
from .forms import MENSAGEM_QUANTIDADE_INVALIDA, QuantidadeCarrinhoForm, QuantidadeInteiraField
from .models import Categoria, ItemPedido, Pedido, Produto

MENSAGEM_INDISPONIVEL_NO_CARRINHO = 'Há produto indisponível no carrinho. Remova o item para continuar.'

# Representações que não são inteiros positivos escritos somente com dígitos.
QUANTIDADES_INVALIDAS = (
    '0', '00', '-1', '1.5', '1,5', '2.0', '2.00', 'abc', '', '   ',
    '+2', '1_000', '1e3', '٣', '0x10',
)


class QuantidadeCarrinhoFormTests(SimpleTestCase):
    """Valida o formulário isoladamente, sem banco nem sessão."""

    def test_inteiros_positivos_sao_aceitos(self):
        for valor, esperado in (('1', 1), ('7', 7), ('120', 120), (' 3 ', 3)):
            with self.subTest(valor=valor):
                form = QuantidadeCarrinhoForm({'quantidade': valor})
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data['quantidade'], esperado)

    def test_representacoes_invalidas_sao_rejeitadas(self):
        for valor in QUANTIDADES_INVALIDAS:
            with self.subTest(valor=valor):
                form = QuantidadeCarrinhoForm({'quantidade': valor})
                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors['quantidade'], [MENSAGEM_QUANTIDADE_INVALIDA])

    def test_campo_ausente_e_rejeitado(self):
        form = QuantidadeCarrinhoForm({})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['quantidade'], [MENSAGEM_QUANTIDADE_INVALIDA])

    def test_limite_superior_e_o_tecnico_do_item_de_pedido(self):
        campo = ItemPedido._meta.get_field('quantidade')
        limites = [v.limit_value for v in campo.validators if isinstance(v, MaxValueValidator)]
        self.assertEqual(limite_tecnico_quantidade(), min(limites))

        limite = limite_tecnico_quantidade()
        self.assertTrue(QuantidadeCarrinhoForm({'quantidade': str(limite)}).is_valid())
        excedente = QuantidadeCarrinhoForm({'quantidade': str(limite + 1)})
        self.assertFalse(excedente.is_valid())
        self.assertIn(str(limite), excedente.errors['quantidade'][0])


class CarrinhoTests(TestCase):
    """Exercita as rotas reais com produtos e usuários do banco temporário de testes."""

    senha = 'Chuva!Telhado42Mar'

    @classmethod
    def setUpTestData(cls):
        cls.categoria = Categoria.objects.create(nome='Mercearia de teste')
        cls.arroz = Produto.objects.create(
            categoria=cls.categoria, nome='Arroz de teste',
            preco=Decimal('12.50'), unidade='pacote de teste',
        )
        cls.leite = Produto.objects.create(
            categoria=cls.categoria, nome='Leite de teste',
            preco=Decimal('6.70'), unidade='caixa de teste',
        )
        cls.cafe = Produto.objects.create(
            categoria=cls.categoria, nome='Cafe de teste',
            preco=Decimal('18.35'), unidade='pacote de cafe de teste',
        )
        cls.inativo = Produto.objects.create(
            categoria=cls.categoria, nome='Produto inativo de teste',
            preco=Decimal('9.90'), unidade='unidade oculta de teste', ativo=False,
        )
        cls.cliente = get_user_model().objects.create_user(
            username='cliente_carrinho_testes', password=cls.senha,
        )

    # Auxiliares

    def adicionar(self, produto_id, quantidade='1', cliente=None, **dados):
        cliente = cliente or self.client
        return cliente.post(
            reverse('principal:adicionar_ao_carrinho', args=[produto_id]),
            {'quantidade': quantidade, **dados},
        )

    def atualizar(self, produto_id, quantidade, cliente=None, **dados):
        cliente = cliente or self.client
        return cliente.post(
            reverse('principal:atualizar_item_carrinho', args=[produto_id]),
            {'quantidade': quantidade, **dados},
        )

    def remover(self, produto_id, cliente=None):
        cliente = cliente or self.client
        return cliente.post(reverse('principal:remover_item_carrinho', args=[produto_id]))

    def itens_sessao(self, cliente=None):
        return (cliente or self.client).session.get(CHAVE_SESSAO, {})

    def preencher(self, *itens, cliente=None):
        """Grava diretamente a estrutura da sessão para preparar cenários."""
        sessao = (cliente or self.client).session
        sessao[CHAVE_SESSAO] = {str(produto.pk): quantidade for produto, quantidade in itens}
        sessao.save()

    def mensagens(self, resposta):
        return [str(mensagem) for mensagem in get_messages(resposta.wsgi_request)]

    def ver_carrinho(self, cliente=None):
        resposta = (cliente or self.client).get(reverse('principal:carrinho'))
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'principal/carrinho.html')
        return resposta

    def linhas(self, resposta):
        return {
            linha.produto_id: linha for linha in resposta.context['resumo'].linhas
        }

    # Adição

    def test_visitante_adiciona_produto_e_e_redirecionado_ao_carrinho(self):
        resposta = self.adicionar(self.arroz.pk, '2')

        self.assertRedirects(resposta, reverse('principal:carrinho'))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertIn('Arroz de teste adicionado ao carrinho.', self.mensagens(resposta))
        carrinho = self.ver_carrinho()
        for texto in (self.arroz.nome, self.arroz.unidade, 'R$ 12,50', 'R$ 25,00'):
            self.assertContains(carrinho, texto)

    def test_cliente_autenticado_adiciona_produto(self):
        self.client.force_login(self.cliente)
        resposta = self.adicionar(self.leite.pk, '3')

        self.assertRedirects(resposta, reverse('principal:carrinho'))
        self.assertEqual(self.itens_sessao(), {str(self.leite.pk): 3})
        self.assertEqual(self.client.session[SESSION_KEY], str(self.cliente.pk))

    def test_adicao_repetida_soma_quantidades_na_mesma_linha(self):
        self.adicionar(self.arroz.pk, '2')
        self.adicionar(self.leite.pk, '1')
        self.adicionar(self.arroz.pk, '3')

        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 5, str(self.leite.pk): 1})
        resposta = self.ver_carrinho()
        self.assertEqual(
            [linha.produto_id for linha in resposta.context['resumo'].linhas],
            [self.arroz.pk, self.leite.pk],
        )
        self.assertEqual(resposta.content.decode().count(self.arroz.unidade), 1)

    def test_produto_inativo_nao_pode_ser_adicionado(self):
        resposta = self.adicionar(self.inativo.pk, '1')

        self.assertRedirects(resposta, reverse('principal:catalogo'))
        self.assertIn('Este produto não está disponível.', self.mensagens(resposta))
        self.assertEqual(self.itens_sessao(), {})

    def test_produto_inexistente_nao_pode_ser_adicionado(self):
        for produto_id in (self.inativo.pk + 1000, 10 ** 30):
            with self.subTest(produto_id=produto_id):
                resposta = self.adicionar(produto_id, '1')
                self.assertRedirects(resposta, reverse('principal:catalogo'))
                self.assertIn('Este produto não está disponível.', self.mensagens(resposta))
                self.assertEqual(self.itens_sessao(), {})

    def test_get_e_head_nao_alteram_o_carrinho(self):
        self.preencher((self.arroz, 2))
        for nome in ('adicionar_ao_carrinho', 'atualizar_item_carrinho', 'remover_item_carrinho'):
            url = reverse(f'principal:{nome}', args=[self.arroz.pk])
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, {'quantidade': '9'}).status_code, 405)
                self.assertEqual(self.client.head(url).status_code, 405)
                self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        self.assertEqual(self.client.head(reverse('principal:carrinho')).status_code, 200)
        self.ver_carrinho()
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_visualizar_carrinho_sem_itens_nao_cria_sessao(self):
        resposta = self.ver_carrinho()

        self.assertContains(resposta, 'Seu carrinho está vazio.')
        self.assertNotIn('sessionid', resposta.cookies)
        self.assertIn('no-cache', resposta['Cache-Control'])

    def test_post_sem_csrf_e_rejeitado_e_com_token_e_aceito(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.get(reverse('principal:catalogo'))
        token = cliente.cookies['csrftoken'].value

        self.assertEqual(self.adicionar(self.arroz.pk, '2', cliente=cliente).status_code, 403)
        self.assertEqual(self.itens_sessao(cliente), {})

        resposta = self.adicionar(self.arroz.pk, '2', cliente=cliente, csrfmiddlewaretoken=token)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.itens_sessao(cliente), {str(self.arroz.pk): 2})

        self.assertEqual(self.atualizar(self.arroz.pk, '5', cliente=cliente).status_code, 403)
        self.assertEqual(self.remover(self.arroz.pk, cliente=cliente).status_code, 403)
        self.assertEqual(self.itens_sessao(cliente), {str(self.arroz.pk): 2})

    def test_catalogo_e_detalhes_oferecem_formulario_post_com_quantidade_inicial_1(self):
        url_adicionar = reverse('principal:adicionar_ao_carrinho', args=[self.arroz.pk])
        for url in (
            reverse('principal:catalogo'),
            reverse('principal:detalhe_produto', args=[self.arroz.pk]),
        ):
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertContains(resposta, f'action="{url_adicionar}"')
                self.assertContains(resposta, 'method="post"')
                self.assertContains(resposta, 'name="csrfmiddlewaretoken"')
                self.assertContains(resposta, 'name="quantidade"')
                self.assertContains(resposta, 'value="1"')
                self.assertContains(resposta, 'Adicionar ao carrinho')
                self.assertNotContains(resposta, 'name="preco"')
        catalogo = self.client.get(reverse('principal:catalogo'))
        self.assertContains(catalogo, f'for="id_quantidade_{self.arroz.pk}"')
        self.assertNotContains(
            catalogo, reverse('principal:adicionar_ao_carrinho', args=[self.inativo.pk]),
        )

    # Quantidades

    def test_quantidade_positiva_e_aceita_na_atualizacao(self):
        self.preencher((self.arroz, 2))
        resposta = self.atualizar(self.arroz.pk, '7')

        self.assertRedirects(resposta, reverse('principal:carrinho'))
        self.assertIn('Quantidade atualizada.', self.mensagens(resposta))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 7})

    def test_quantidades_invalidas_na_adicao_preservam_o_carrinho(self):
        self.preencher((self.arroz, 3))
        for valor in QUANTIDADES_INVALIDAS:
            with self.subTest(valor=valor):
                resposta = self.adicionar(self.arroz.pk, valor)
                self.assertEqual(resposta.status_code, 200)
                self.assertTemplateUsed(resposta, 'principal/detalhe_produto.html')
                self.assertContains(resposta, MENSAGEM_QUANTIDADE_INVALIDA)
                self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 3})
        sem_campo = self.client.post(reverse('principal:adicionar_ao_carrinho', args=[self.arroz.pk]))
        self.assertContains(sem_campo, MENSAGEM_QUANTIDADE_INVALIDA)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 3})

    def test_quantidades_invalidas_na_atualizacao_preservam_a_anterior(self):
        self.preencher((self.arroz, 3), (self.leite, 1))
        for valor in QUANTIDADES_INVALIDAS:
            with self.subTest(valor=valor):
                resposta = self.atualizar(self.arroz.pk, valor)
                self.assertEqual(resposta.status_code, 200)
                self.assertTemplateUsed(resposta, 'principal/carrinho.html')
                self.assertContains(resposta, MENSAGEM_QUANTIDADE_INVALIDA)
                self.assertContains(resposta, 'Quantidade mantida: 3')
                self.assertEqual(
                    self.itens_sessao(), {str(self.arroz.pk): 3, str(self.leite.pk): 1},
                )
                # O erro pertence somente ao item enviado.
                self.assertEqual(resposta.content.decode().count(MENSAGEM_QUANTIDADE_INVALIDA), 1)

    def test_zero_nao_remove_o_item(self):
        self.preencher((self.arroz, 2))
        resposta = self.atualizar(self.arroz.pk, '0')

        self.assertContains(resposta, MENSAGEM_QUANTIDADE_INVALIDA)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        self.assertIn(self.arroz.pk, self.linhas(self.ver_carrinho()))

    def test_soma_acima_do_limite_tecnico_e_rejeitada_sem_perder_a_quantidade(self):
        limite = limite_tecnico_quantidade()
        self.preencher((self.arroz, limite - 1))

        self.assertRedirects(self.adicionar(self.arroz.pk, '1'), reverse('principal:carrinho'))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): limite})
        resposta = self.adicionar(self.arroz.pk, '1')
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f'não pode ultrapassar {limite}')
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): limite})

    # Remoção

    def test_remover_um_item_preserva_os_demais(self):
        self.preencher((self.arroz, 2), (self.leite, 1), (self.cafe, 4))
        resposta = self.remover(self.leite.pk)

        self.assertRedirects(resposta, reverse('principal:carrinho'))
        self.assertIn('Item removido do carrinho.', self.mensagens(resposta))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2, str(self.cafe.pk): 4})

    def test_remover_o_ultimo_item_exibe_carrinho_vazio(self):
        self.preencher((self.arroz, 2))
        self.remover(self.arroz.pk)

        resposta = self.ver_carrinho()
        self.assertEqual(self.itens_sessao(), {})
        self.assertContains(resposta, 'Seu carrinho está vazio.')
        self.assertNotContains(resposta, 'Subtotal')

    def test_remover_item_ausente_informa_sem_alterar(self):
        self.preencher((self.arroz, 2))
        resposta = self.remover(self.leite.pk)

        self.assertIn('Este item não está no carrinho.', self.mensagens(resposta))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        self.assertIn('Este item não está no carrinho.', self.mensagens(self.atualizar(self.leite.pk, '2')))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_produto_excluido_permanece_identificado_ate_remocao_explicita(self):
        excluido = Produto.objects.create(
            categoria=self.categoria, nome='Produto excluido de teste',
            preco=Decimal('4.44'), unidade='unidade excluida de teste',
        )
        excluido_id = excluido.pk
        self.preencher((self.arroz, 1), (excluido, 2))
        excluido.delete()

        resposta = self.ver_carrinho()
        linha = self.linhas(resposta)[excluido_id]
        self.assertFalse(linha.encontrado)
        self.assertFalse(linha.disponivel)
        self.assertIsNone(linha.valor)
        self.assertContains(resposta, f'Produto não encontrado (código {excluido_id})')
        self.assertContains(resposta, MENSAGEM_INDISPONIVEL_NO_CARRINHO)
        for texto in ('Produto excluido de teste', 'unidade excluida de teste', '4,44', '8,88'):
            self.assertNotContains(resposta, texto)
        self.assertEqual(resposta.context['resumo'].subtotal, Decimal('12.50'))
        # A visualização não remove a entrada da sessão.
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 1, str(excluido_id): 2})

        self.atualizar(excluido_id, '5')
        self.assertEqual(self.itens_sessao()[str(excluido_id)], 2)
        self.assertRedirects(self.remover(excluido_id), reverse('principal:carrinho'))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 1})
        self.assertNotContains(self.ver_carrinho(), MENSAGEM_INDISPONIVEL_NO_CARRINHO)

    # Cálculos

    def test_valores_das_linhas_e_subtotal_em_decimal(self):
        self.preencher((self.arroz, 3), (self.leite, 2), (self.cafe, 1))
        resposta = self.ver_carrinho()
        linhas = self.linhas(resposta)
        resumo = resposta.context['resumo']

        self.assertEqual(linhas[self.arroz.pk].valor, Decimal('37.50'))
        self.assertEqual(linhas[self.leite.pk].valor, Decimal('13.40'))
        self.assertEqual(linhas[self.cafe.pk].valor, Decimal('18.35'))
        self.assertEqual(resumo.subtotal, Decimal('69.25'))
        self.assertIsInstance(resumo.subtotal, Decimal)
        for linha in linhas.values():
            self.assertIsInstance(linha.valor, Decimal)
        for texto in ('R$ 37,50', 'R$ 13,40', 'R$ 18,35', 'R$ 69,25', 'Taxa de entrega informada na etapa de endereço.'):
            self.assertContains(resposta, texto)

    def test_recalculo_apos_adicao_atualizacao_e_remocao(self):
        self.adicionar(self.arroz.pk, '1')
        self.assertEqual(self.ver_carrinho().context['resumo'].subtotal, Decimal('12.50'))
        self.adicionar(self.leite.pk, '2')
        self.assertEqual(self.ver_carrinho().context['resumo'].subtotal, Decimal('25.90'))

        self.atualizar(self.arroz.pk, '4')
        resposta = self.ver_carrinho()
        self.assertEqual(self.linhas(resposta)[self.arroz.pk].valor, Decimal('50.00'))
        self.assertEqual(resposta.context['resumo'].subtotal, Decimal('63.40'))
        self.assertContains(resposta, 'R$ 63,40')

        self.remover(self.arroz.pk)
        resposta = self.ver_carrinho()
        self.assertEqual(resposta.context['resumo'].subtotal, Decimal('13.40'))
        self.assertContains(resposta, 'R$ 13,40')

    def test_alteracao_de_preco_e_nome_no_banco_aparece_na_proxima_visualizacao(self):
        self.preencher((self.arroz, 2))
        self.assertEqual(self.ver_carrinho().context['resumo'].subtotal, Decimal('25.00'))

        Produto.objects.filter(pk=self.arroz.pk).update(preco=Decimal('13.15'), nome='Arroz renomeado de teste')
        resposta = self.ver_carrinho()
        self.assertEqual(resposta.context['resumo'].subtotal, Decimal('26.30'))
        for texto in ('Arroz renomeado de teste', 'R$ 13,15', 'R$ 26,30'):
            self.assertContains(resposta, texto)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_alteracao_de_preco_pelo_admin_aparece_no_carrinho(self):
        administrador = get_user_model().objects.create_superuser(
            username='administrador_carrinho_testes', password=None,
        )
        cliente_admin = Client()
        cliente_admin.force_login(administrador)
        self.preencher((self.leite, 3))

        edicao = cliente_admin.post(
            reverse('admin:principal_produto_change', args=[self.leite.pk]),
            {
                'categoria': self.categoria.pk, 'nome': self.leite.nome, 'preco': '7.10',
                'unidade': self.leite.unidade, 'ativo': 'on', '_save': 'Salvar',
            },
        )
        self.assertRedirects(edicao, reverse('admin:principal_produto_changelist'))
        resposta = self.ver_carrinho()
        self.assertEqual(resposta.context['resumo'].subtotal, Decimal('21.30'))
        self.assertContains(resposta, 'R$ 21,30')

    def test_precos_enviados_pelo_navegador_sao_ignorados(self):
        valores_forjados = {'preco': '0.01', 'valor': '0.01', 'subtotal': '0.01', 'preco_unitario': '0.01'}
        self.adicionar(self.arroz.pk, '2', **valores_forjados)
        self.atualizar(self.arroz.pk, '3', **valores_forjados)

        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 3})
        resposta = self.ver_carrinho()
        self.assertEqual(resposta.context['resumo'].subtotal, Decimal('37.50'))
        self.assertNotContains(resposta, '0,01')
        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.preco, Decimal('12.50'))

    def test_sessao_guarda_somente_identificadores_e_quantidades(self):
        self.adicionar(self.arroz.pk, '2')
        self.adicionar(self.leite.pk, '1')

        itens = self.itens_sessao()
        self.assertEqual(itens, {str(self.arroz.pk): 2, str(self.leite.pk): 1})
        for chave, quantidade in itens.items():
            self.assertTrue(chave.isdigit())
            self.assertIs(type(quantidade), int)

    def test_calculo_exato_no_limite_tecnico_sem_arredondamento(self):
        limite = limite_tecnico_quantidade()
        caro = Produto.objects.create(
            categoria=self.categoria, nome='Produto de preco maximo de teste',
            preco=Decimal('99999999.99'), unidade='unidade de teste',
        )
        self.preencher((caro, limite), (self.arroz, limite))
        resposta = self.ver_carrinho()
        resumo = resposta.context['resumo']

        # Esperados calculados com inteiros em centavos e conferidos pelos dígitos, pois
        # qualquer operação no contexto padrão de 28 dígitos arredondaria estes valores.
        def centavos(valor):
            sinal, digitos, expoente = valor.as_tuple()
            self.assertEqual((sinal, expoente), (0, -2))
            return int(''.join(map(str, digitos)))

        centavos_caro = limite * 9999999999
        self.assertGreater(len(str(centavos_caro)), 28)
        self.assertEqual(centavos(self.linhas(resposta)[caro.pk].valor), centavos_caro)
        self.assertEqual(centavos(resumo.subtotal), centavos_caro + limite * 1250)

    # Disponibilidade

    def test_produto_desativado_permanece_identificado_e_pode_ser_removido(self):
        self.adicionar(self.arroz.pk, '2')
        self.adicionar(self.leite.pk, '1')
        Produto.objects.filter(pk=self.arroz.pk).update(ativo=False)

        resposta = self.ver_carrinho()
        linha = self.linhas(resposta)[self.arroz.pk]
        self.assertTrue(linha.encontrado)
        self.assertFalse(linha.disponivel)
        self.assertTrue(self.linhas(resposta)[self.leite.pk].disponivel)
        self.assertTrue(resposta.context['resumo'].possui_indisponivel)
        self.assertContains(resposta, MENSAGEM_INDISPONIVEL_NO_CARRINHO)
        self.assertContains(resposta, 'Indisponível')
        self.assertContains(resposta, self.arroz.nome)
        self.assertNotContains(
            resposta, reverse('principal:atualizar_item_carrinho', args=[self.arroz.pk]),
        )
        self.assertContains(resposta, reverse('principal:remover_item_carrinho', args=[self.arroz.pk]))
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2, str(self.leite.pk): 1})

        self.assertRedirects(self.remover(self.arroz.pk), reverse('principal:carrinho'))
        resposta = self.ver_carrinho()
        self.assertEqual(self.itens_sessao(), {str(self.leite.pk): 1})
        self.assertNotContains(resposta, MENSAGEM_INDISPONIVEL_NO_CARRINHO)

    def test_produto_desativado_no_carrinho_nao_e_readicionado_nem_atualizado(self):
        self.preencher((self.arroz, 2))
        Produto.objects.filter(pk=self.arroz.pk).update(ativo=False)

        adicao = self.adicionar(self.arroz.pk, '1')
        self.assertRedirects(adicao, reverse('principal:catalogo'))
        self.assertIn('Este produto não está disponível.', self.mensagens(adicao))
        atualizacao = self.atualizar(self.arroz.pk, '5')
        self.assertRedirects(atualizacao, reverse('principal:carrinho'))
        self.assertIn(
            'Este produto não está disponível. Remova o item do carrinho.', self.mensagens(atualizacao),
        )
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

    def test_subtotal_provisorio_inclui_inativo_existente_e_exclui_excluido(self):
        excluido = Produto.objects.create(
            categoria=self.categoria, nome='Outro excluido de teste',
            preco=Decimal('3.00'), unidade='unidade de teste',
        )
        self.preencher((self.arroz, 2), (self.leite, 1), (excluido, 1))
        excluido.delete()
        Produto.objects.filter(pk=self.arroz.pk).update(ativo=False)

        resumo = self.ver_carrinho().context['resumo']
        self.assertEqual(resumo.subtotal, Decimal('25.00') + Decimal('6.70'))

    def test_produto_reativado_volta_a_ser_disponivel(self):
        self.preencher((self.inativo, 1))
        self.assertTrue(self.ver_carrinho().context['resumo'].possui_indisponivel)

        Produto.objects.filter(pk=self.inativo.pk).update(ativo=True)
        resposta = self.ver_carrinho()
        self.assertFalse(resposta.context['resumo'].possui_indisponivel)
        self.assertRedirects(self.atualizar(self.inativo.pk, '2'), reverse('principal:carrinho'))
        self.assertEqual(self.itens_sessao(), {str(self.inativo.pk): 2})

    # Sessão e autenticação

    def test_duas_sessoes_nao_compartilham_o_carrinho(self):
        primeiro, segundo = Client(), Client()
        self.adicionar(self.arroz.pk, '2', cliente=primeiro)
        self.adicionar(self.leite.pk, '5', cliente=segundo)

        self.assertNotEqual(primeiro.session.session_key, segundo.session.session_key)
        self.assertEqual(self.itens_sessao(primeiro), {str(self.arroz.pk): 2})
        self.assertEqual(self.itens_sessao(segundo), {str(self.leite.pk): 5})
        self.remover(self.arroz.pk, cliente=segundo)
        self.assertEqual(self.itens_sessao(primeiro), {str(self.arroz.pk): 2})
        self.assertNotContains(self.ver_carrinho(segundo), self.arroz.nome)

    def test_login_preserva_o_carrinho_da_sessao(self):
        self.adicionar(self.arroz.pk, '2')
        chave_anterior = self.client.session.session_key

        login = self.client.post(
            reverse('principal:login'),
            {'username': self.cliente.username, 'password': self.senha},
        )
        self.assertRedirects(login, reverse('principal:minha_conta'))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.cliente.pk))
        self.assertNotEqual(self.client.session.session_key, chave_anterior)
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})
        self.assertContains(self.ver_carrinho(), self.arroz.nome)

    def test_logout_limpa_o_carrinho(self):
        self.client.force_login(self.cliente)
        self.adicionar(self.arroz.pk, '2')
        self.assertEqual(self.itens_sessao(), {str(self.arroz.pk): 2})

        self.assertRedirects(self.client.post(reverse('principal:logout')), reverse('principal:inicio'))
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.itens_sessao(), {})
        self.assertContains(self.ver_carrinho(), 'Seu carrinho está vazio.')

    # Escopo, navegação e consultas

    def test_navegacao_oferece_carrinho_para_visitante_e_cliente(self):
        url = reverse('principal:carrinho')
        self.assertContains(self.client.get(reverse('principal:inicio')), f'href="{url}"')
        self.client.force_login(self.cliente)
        resposta = self.client.get(reverse('principal:inicio'))
        self.assertContains(resposta, f'href="{url}"')
        self.assertContains(resposta, reverse('principal:minha_conta'))

    def test_carrinho_nao_cria_pedidos_e_so_oferece_link_para_finalizacao(self):
        # Semana 7: o carrinho passou a oferecer acesso ao checkout (antes T-607 o omitia),
        # mas somente como link GET; nenhuma ação do carrinho cria pedido.
        produtos_antes = list(Produto.objects.order_by('pk').values())
        self.adicionar(self.arroz.pk, '2')
        self.atualizar(self.arroz.pk, '3')
        self.adicionar(self.leite.pk, '1')
        self.remover(self.leite.pk)

        resposta = self.ver_carrinho()
        url_checkout = reverse('principal:checkout')
        self.assertContains(resposta, f'<a href="{url_checkout}">Finalizar compra</a>', html=True)
        self.assertNotContains(resposta, f'action="{url_checkout}"')
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(ItemPedido.objects.count(), 0)
        self.assertEqual(list(Produto.objects.order_by('pk').values()), produtos_antes)

    def test_formulario_da_linha_tem_label_proprio(self):
        self.preencher((self.arroz, 2), (self.leite, 1))
        resposta = self.ver_carrinho()

        for produto in (self.arroz, self.leite):
            self.assertContains(resposta, f'for="id_quantidade_{produto.pk}"')
            self.assertContains(resposta, f'id="id_quantidade_{produto.pk}"')
        self.assertContains(resposta, 'value="2"')

    def test_quantidade_de_consultas_nao_cresce_com_mais_itens(self):
        self.preencher((self.arroz, 1))
        url = reverse('principal:carrinho')
        with CaptureQueriesContext(connection) as consultas:
            self.client.get(url)

        adicionais = Produto.objects.bulk_create([
            Produto(
                categoria=self.categoria, nome=f'Produto adicional de teste {indice}',
                preco=Decimal('1.00'), unidade='unidade de teste',
            )
            for indice in range(5)
        ])
        self.preencher((self.arroz, 1), (self.inativo, 1), *[(produto, 2) for produto in adicionais])
        with self.assertNumQueries(len(consultas)):
            resposta = self.client.get(url)
        self.assertEqual(len(resposta.context['resumo'].linhas), 7)

    def test_servico_le_sem_gravar_e_resumo_vazio(self):
        sessao = import_module(settings.SESSION_ENGINE).SessionStore()
        carrinho = Carrinho(sessao)
        with self.assertNumQueries(0):
            resumo = carrinho.resumo()
        self.assertTrue(resumo.vazio)
        self.assertEqual(resumo.subtotal, Decimal('0.00'))
        self.assertFalse(sessao.modified)


SessionStore = import_module(settings.SESSION_ENGINE).SessionStore

MENSAGEM_INCONSISTENCIA = 'Alguns dados do carrinho estão inconsistentes e não entram no subtotal.'


class QuantidadeComMuitosDigitosTests(TestCase):
    """M-1: textos acima de 4300 dígitos não podem escapar como ValueError (HTTP 500)."""

    @classmethod
    def setUpTestData(cls):
        categoria = Categoria.objects.create(nome='Categoria digitos de teste')
        cls.produto = Produto.objects.create(
            categoria=categoria, nome='Produto digitos de teste',
            preco=Decimal('2.00'), unidade='unidade de teste',
        )

    def setUp(self):
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = {str(self.produto.pk): 3}
        sessao.save()

    def itens(self):
        return self.client.session[CHAVE_SESSAO]

    def test_adicao_com_4300_e_4301_digitos_vira_erro_de_validacao(self):
        url = reverse('principal:adicionar_ao_carrinho', args=[self.produto.pk])
        for digitos in (4300, 4301, 10000):
            with self.subTest(digitos=digitos):
                resposta = self.client.post(url, {'quantidade': '9' * digitos})
                self.assertEqual(resposta.status_code, 200)
                self.assertTemplateUsed(resposta, 'principal/detalhe_produto.html')
                self.assertContains(resposta, 'Informe uma quantidade de no máximo')
                self.assertEqual(self.itens(), {str(self.produto.pk): 3})

    def test_atualizacao_com_4301_digitos_preserva_quantidade(self):
        url = reverse('principal:atualizar_item_carrinho', args=[self.produto.pk])
        for digitos in (4300, 4301, 10000):
            with self.subTest(digitos=digitos):
                resposta = self.client.post(url, {'quantidade': '1' * digitos})
                self.assertEqual(resposta.status_code, 200)
                self.assertTemplateUsed(resposta, 'principal/carrinho.html')
                self.assertContains(resposta, 'Informe uma quantidade de no máximo')
                self.assertContains(resposta, 'Quantidade mantida: 3')
                self.assertEqual(self.itens(), {str(self.produto.pk): 3})

    def test_zeros_a_esquerda_nao_contam_para_o_comprimento(self):
        url = reverse('principal:adicionar_ao_carrinho', args=[self.produto.pk])
        resposta = self.client.post(url, {'quantidade': '0' * 5000 + '2'})

        self.assertRedirects(resposta, reverse('principal:carrinho'))
        self.assertEqual(self.itens(), {str(self.produto.pk): 5})

    def test_campo_sem_limite_tambem_nao_propaga_value_error(self):
        campo = QuantidadeInteiraField(min_value=1)
        with self.assertRaises(ValidationError) as contexto:
            campo.clean('9' * 5000)
        self.assertEqual(contexto.exception.code, 'invalid')
        self.assertEqual(campo.clean('0' * 5000 + '7'), 7)


class CarrinhoServicoTests(TestCase):
    """M-2: chamadas diretas ao serviço, sem formulários nem views."""

    @classmethod
    def setUpTestData(cls):
        cls.categoria = Categoria.objects.create(nome='Categoria servico de teste')
        cls.ativo = Produto.objects.create(
            categoria=cls.categoria, nome='Ativo servico de teste',
            preco=Decimal('3.00'), unidade='unidade de teste',
        )
        cls.outro = Produto.objects.create(
            categoria=cls.categoria, nome='Outro servico de teste',
            preco=Decimal('4.00'), unidade='unidade de teste',
        )
        cls.inativo = Produto.objects.create(
            categoria=cls.categoria, nome='Inativo servico de teste',
            preco=Decimal('5.00'), unidade='unidade de teste', ativo=False,
        )

    def setUp(self):
        gravada = SessionStore()
        gravada[CHAVE_SESSAO] = {str(self.ativo.pk): 2, str(self.inativo.pk): 1}
        gravada.save()
        # Sessão recarregada: começa sem modificações pendentes.
        self.sessao = SessionStore(gravada.session_key)
        self.carrinho = Carrinho(self.sessao)
        self.original = copy.deepcopy(self.sessao[CHAVE_SESSAO])

    def assert_sessao_intacta(self):
        self.assertEqual(self.sessao[CHAVE_SESSAO], self.original)
        self.assertFalse(self.sessao.modified)

    def quantidades_invalidas(self):
        limite = limite_tecnico_quantidade()
        return (
            (0, QuantidadeInvalida), (-1, QuantidadeInvalida), (1.5, QuantidadeInvalida),
            (2.0, QuantidadeInvalida), (Decimal('2'), QuantidadeInvalida),
            ('2', QuantidadeInvalida), ('abc', QuantidadeInvalida), (None, QuantidadeInvalida),
            (True, QuantidadeInvalida), (False, QuantidadeInvalida),
            (limite + 1, QuantidadeAcimaDoLimite), (10 ** 30, QuantidadeAcimaDoLimite),
        )

    def test_adicionar_recusa_quantidades_invalidas_sem_alterar_a_sessao(self):
        for quantidade, excecao in self.quantidades_invalidas():
            with self.subTest(quantidade=quantidade):
                with self.assertRaises(excecao):
                    self.carrinho.adicionar(self.outro, quantidade)
                self.assert_sessao_intacta()

    def test_definir_quantidade_recusa_quantidades_invalidas_sem_alterar_a_sessao(self):
        for quantidade, excecao in self.quantidades_invalidas():
            with self.subTest(quantidade=quantidade):
                with self.assertRaises(excecao):
                    self.carrinho.definir_quantidade(self.ativo, quantidade)
                self.assert_sessao_intacta()

    def test_soma_acima_do_limite_e_recusada(self):
        limite = limite_tecnico_quantidade()
        self.carrinho.definir_quantidade(self.ativo, limite - 1)
        estado = copy.deepcopy(self.sessao[CHAVE_SESSAO])

        with self.assertRaises(QuantidadeAcimaDoLimite) as contexto:
            self.carrinho.adicionar(self.ativo, 2)
        self.assertEqual(contexto.exception.limite, limite)
        self.assertEqual(self.sessao[CHAVE_SESSAO], estado)

    def test_produtos_invalidos_sao_recusados_sem_alterar_a_sessao(self):
        excluido = Produto.objects.create(
            categoria=self.categoria, nome='Excluido servico de teste',
            preco=Decimal('1.00'), unidade='unidade de teste',
        )
        Produto.objects.filter(pk=excluido.pk).delete()
        nao_persistido = Produto(
            categoria=self.categoria, nome='Nao persistido de teste',
            preco=Decimal('1.00'), unidade='unidade de teste',
        )
        # Instância carregada como ativa e desativada depois diretamente no banco.
        desatualizado = Produto.objects.get(pk=self.outro.pk)
        Produto.objects.filter(pk=self.outro.pk).update(ativo=False)

        for produto in (self.inativo, excluido, nao_persistido, desatualizado, self.ativo.pk, 'x', None):
            with self.subTest(produto=produto):
                with self.assertRaises(ProdutoIndisponivel):
                    self.carrinho.adicionar(produto, 1)
                with self.assertRaises(ProdutoIndisponivel):
                    self.carrinho.definir_quantidade(produto, 1)
                self.assert_sessao_intacta()

    def test_definir_quantidade_exige_item_presente_e_produto_ativo(self):
        with self.assertRaises(ItemAusente):
            self.carrinho.definir_quantidade(self.outro, 1)
        with self.assertRaises(ProdutoIndisponivel):
            self.carrinho.definir_quantidade(self.inativo, 3)
        self.assert_sessao_intacta()

    def test_remover_e_contem_recusam_identificadores_invalidos(self):
        for identificador in (True, False, 0, -1, 1.0, None, '07', ' 1', 'abc', '9' * 5000):
            with self.subTest(identificador=identificador):
                self.assertFalse(self.carrinho.contem(identificador))
                self.assertFalse(self.carrinho.remover(identificador))
                self.assert_sessao_intacta()
        self.assertTrue(self.carrinho.contem(str(self.ativo.pk)))
        self.assertTrue(self.carrinho.contem(self.ativo.pk))

    def test_operacoes_validas_continuam_funcionando(self):
        self.assertEqual(self.carrinho.adicionar(self.ativo, 3), 5)
        self.assertEqual(self.carrinho.adicionar(self.outro, 1), 1)
        self.assertEqual(self.carrinho.definir_quantidade(self.outro, 4), 4)
        self.assertTrue(self.carrinho.remover(self.inativo.pk))
        self.assertEqual(
            self.sessao[CHAVE_SESSAO], {str(self.ativo.pk): 5, str(self.outro.pk): 4},
        )
        self.assertEqual(self.carrinho.quantidade(self.ativo.pk), 5)

    def test_quantidade_inconsistente_nao_e_somada_mas_pode_ser_substituida_ou_removida(self):
        self.sessao[CHAVE_SESSAO] = {str(self.ativo.pk): '3', str(self.outro.pk): None}
        estado = copy.deepcopy(self.sessao[CHAVE_SESSAO])

        with self.assertRaises(ItemInconsistente):
            self.carrinho.adicionar(self.ativo, 1)
        self.assertEqual(self.sessao[CHAVE_SESSAO], estado)
        self.assertIsNone(self.carrinho.quantidade(self.ativo.pk))

        self.carrinho.definir_quantidade(self.ativo, 6)
        # Mesmo com valor None armazenado, a remoção explícita elimina a entrada.
        self.assertTrue(self.carrinho.remover(self.outro.pk))
        self.assertEqual(self.sessao[CHAVE_SESSAO], {str(self.ativo.pk): 6})


class SessaoMalformadaTests(TestCase):
    """B-1: o resumo tolera entradas malformadas sem HTTP 500 e sem reescrever a sessão."""

    @classmethod
    def setUpTestData(cls):
        categoria = Categoria.objects.create(nome='Categoria sessao malformada de teste')
        produtos = {}
        for nome, preco in (
            ('valido', '12.50'), ('texto', '1.00'), ('float', '1.00'), ('nulo', '1.00'),
            ('zero', '1.00'), ('negativo', '1.00'), ('booleano', '1.00'), ('outro', '6.70'),
        ):
            produtos[nome] = Produto.objects.create(
                categoria=categoria, nome=f'Produto {nome} de teste',
                preco=Decimal(preco), unidade='unidade de teste',
            )
        cls.produtos = produtos

    def setUp(self):
        p = self.produtos
        self.malformada = {
            str(p['valido'].pk): 2,
            str(p['texto'].pk): '3',
            str(p['float'].pk): 2.5,
            str(p['nulo'].pk): None,
            str(p['zero'].pk): 0,
            str(p['negativo'].pk): -4,
            str(p['booleano'].pk): True,
            str(p['outro'].pk): 1,
            'abc': 1,
            '07': 3,
            '-5': 1,
            '9' * 5000: 1,
        }
        self.gravar(self.malformada)

    def gravar(self, valor):
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = valor
        sessao.save()

    def itens(self):
        return self.client.session[CHAVE_SESSAO]

    def test_get_responde_sem_erro_e_subtotal_usa_somente_entradas_validas(self):
        resposta = self.client.get(reverse('principal:carrinho'))
        self.assertEqual(resposta.status_code, 200)
        resumo = resposta.context['resumo']
        p = self.produtos

        self.assertEqual(resumo.subtotal, Decimal('25.00') + Decimal('6.70'))
        self.assertEqual(resumo.entradas_ignoradas, 4)
        self.assertTrue(resumo.possui_inconsistencia)
        linhas = {linha.produto_id: linha for linha in resumo.linhas}
        self.assertEqual(linhas[p['valido'].pk].quantidade, 2)
        self.assertEqual(linhas[p['outro'].pk].valor, Decimal('6.70'))
        for nome in ('texto', 'float', 'nulo', 'zero', 'negativo', 'booleano'):
            with self.subTest(nome=nome):
                linha = linhas[p[nome].pk]
                self.assertFalse(linha.consistente)
                self.assertIsNone(linha.quantidade)
                self.assertIsNone(linha.valor)
        for texto in (
            MENSAGEM_INCONSISTENCIA, '4 registro(s) do carrinho não puderam ser identificados.',
            'Quantidade inválida', p['valido'].nome, 'R$ 25,00', 'R$ 31,70',
        ):
            self.assertContains(resposta, texto)
        for texto in ('R$ -', 'R$ 0,00', '2.5', 'Traceback', 'ValueError'):
            self.assertNotContains(resposta, texto)

    def test_get_e_head_nao_reescrevem_a_sessao(self):
        original = copy.deepcopy(self.malformada)
        self.client.get(reverse('principal:carrinho'))
        self.client.head(reverse('principal:carrinho'))

        self.assertEqual(self.itens(), original)

    def test_estruturas_que_nao_sao_dicionario_geram_aviso_sem_reescrita(self):
        for valor in ([1, 2], 'texto', None, 5):
            with self.subTest(valor=valor):
                self.gravar(valor)
                resposta = self.client.get(reverse('principal:carrinho'))
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, 'Seu carrinho está vazio.')
                self.assertContains(resposta, MENSAGEM_INCONSISTENCIA)
                self.assertContains(resposta, '1 registro(s) do carrinho não puderam ser identificados.')
                self.assertEqual(resposta.context['resumo'].subtotal, Decimal('0.00'))
                self.assertEqual(self.itens(), valor)

    def test_post_valido_substitui_estrutura_que_nao_e_dicionario(self):
        self.gravar('texto')
        url = reverse('principal:adicionar_ao_carrinho', args=[self.produtos['valido'].pk])
        self.assertRedirects(self.client.post(url, {'quantidade': '1'}), reverse('principal:carrinho'))

        self.assertEqual(self.itens(), {str(self.produtos['valido'].pk): 1})
        self.assertNotContains(self.client.get(reverse('principal:carrinho')), MENSAGEM_INCONSISTENCIA)

    def test_operacoes_normais_continuam_sobre_itens_validos(self):
        p = self.produtos
        url_atualizar = reverse('principal:atualizar_item_carrinho', args=[p['valido'].pk])
        self.assertRedirects(
            self.client.post(url_atualizar, {'quantidade': '5'}), reverse('principal:carrinho'),
        )
        url_adicionar = reverse('principal:adicionar_ao_carrinho', args=[p['outro'].pk])
        self.assertRedirects(
            self.client.post(url_adicionar, {'quantidade': '2'}), reverse('principal:carrinho'),
        )
        url_remover = reverse('principal:remover_item_carrinho', args=[p['nulo'].pk])
        self.assertRedirects(self.client.post(url_remover), reverse('principal:carrinho'))

        esperado = dict(self.malformada)
        esperado[str(p['valido'].pk)] = 5
        esperado[str(p['outro'].pk)] = 3
        del esperado[str(p['nulo'].pk)]
        self.assertEqual(self.itens(), esperado)
        resposta = self.client.get(reverse('principal:carrinho'))
        self.assertEqual(resposta.context['resumo'].subtotal, Decimal('62.50') + Decimal('20.10'))

    def test_item_inconsistente_pode_ser_corrigido_mas_nao_somado(self):
        p = self.produtos
        adicao = self.client.post(
            reverse('principal:adicionar_ao_carrinho', args=[p['texto'].pk]), {'quantidade': '1'},
        )
        self.assertRedirects(adicao, reverse('principal:carrinho'))
        self.assertIn(
            'A quantidade registrada para este item é inválida. Atualize a quantidade ou remova o item.',
            [str(mensagem) for mensagem in get_messages(adicao.wsgi_request)],
        )
        self.assertEqual(self.itens()[str(p['texto'].pk)], '3')

        correcao = self.client.post(
            reverse('principal:atualizar_item_carrinho', args=[p['texto'].pk]), {'quantidade': '4'},
        )
        self.assertRedirects(correcao, reverse('principal:carrinho'))
        self.assertEqual(self.itens()[str(p['texto'].pk)], 4)
