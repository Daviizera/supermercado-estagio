"""Configuração demonstrativa de entrega (D-001/D-002, somente para a demonstração acadêmica).

Os testes desta classe NÃO sobrescrevem CHECKOUT_*: usam a configuração real do ambiente de
desenvolvimento (bairro fictício e taxa de R$ 5,00). A produção é verificada em outro processo,
com DJANGO_ENV=production.
"""
import json
import os
import subprocess
import sys
from decimal import Decimal
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import checkout as servico_checkout
from .carrinho import CHAVE_SESSAO
from .models import Categoria, Pedido, Produto
from .test_configuracao import BASE, ENDERECO_CACHE_TESTE, HOST_TESTE, REDIS, chave_teste

BAIRRO_DEMONSTRATIVO = 'Bairro Ficticio de Teste'
TAXA_DEMONSTRATIVA = Decimal('5.00')
ENTREGA = {'logradouro': 'Rua Fictícia da Demonstração', 'numero': '100', 'complemento': '',
           'bairro': BAIRRO_DEMONSTRATIVO, 'telefone': 'telefone fictício'}


def reais(valor):
    return 'R$ ' + f'{valor:.2f}'.replace('.', ',')


class ConfiguracaoDesenvolvimentoTests(SimpleTestCase):
    def test_valores_demonstrativos_centralizados_e_aplicados_em_development(self):
        self.assertEqual(settings.AMBIENTE, 'development')
        self.assertEqual(settings.CHECKOUT_DEMONSTRACAO_BAIRROS, (BAIRRO_DEMONSTRATIVO,))
        self.assertEqual(settings.CHECKOUT_DEMONSTRACAO_TAXA_ENTREGA, TAXA_DEMONSTRATIVA)
        self.assertEqual(settings.CHECKOUT_BAIRROS_ATENDIDOS, settings.CHECKOUT_DEMONSTRACAO_BAIRROS)
        self.assertEqual(settings.CHECKOUT_TAXA_ENTREGA, settings.CHECKOUT_DEMONSTRACAO_TAXA_ENTREGA)
        configuracao = servico_checkout.obter_configuracao()
        self.assertEqual(configuracao.bairros, (BAIRRO_DEMONSTRATIVO,))
        self.assertEqual(configuracao.taxa_entrega, TAXA_DEMONSTRATIVA)
        self.assertEqual(configuracao.valor_maximo, Decimal('5000.00'))


class ProducaoSemValoresDemonstrativosTests(SimpleTestCase):
    """Carrega as configurações reais com DJANGO_ENV=production em outro processo."""

    def test_producao_nao_herda_bairro_nem_taxa_e_bloqueia_o_checkout(self):
        codigo = (
            'import json, django; django.setup(); from django.conf import settings as s; '
            'from principal import checkout as c\n'
            'try:\n    c.obter_configuracao(); bloqueado = False\n'
            'except c.CheckoutIndisponivel:\n    bloqueado = True\n'
            'print(json.dumps({"bairros": list(s.CHECKOUT_BAIRROS_ATENDIDOS), "taxa": s.CHECKOUT_TAXA_ENTREGA, '
            '"bloqueado": bloqueado}))'
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
        env.update({
            'DJANGO_SETTINGS_MODULE': 'supermercado.settings', 'DJANGO_ENV': 'production',
            'DJANGO_SECRET_KEY': chave_teste(), 'DJANGO_ALLOWED_HOSTS': HOST_TESTE,
            'DJANGO_LIMITE_LOGIN_CACHE_BACKEND': REDIS, 'DJANGO_LIMITE_LOGIN_CACHE_LOCATION': ENDERECO_CACHE_TESTE,
        })
        processo = subprocess.run([sys.executable, '-c', codigo], cwd=BASE, env=env, capture_output=True,
                                  text=True, timeout=120)
        self.assertEqual(processo.returncode, 0, processo.stderr[-800:])
        self.assertEqual(json.loads(processo.stdout), {'bairros': [], 'taxa': None, 'bloqueado': True})


class CheckoutDemonstrativoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('preparar_dados_demonstracao', stdout=StringIO())
        cls.arroz = Produto.objects.get(nome='Arroz branco tipo 1')
        cls.oleo = Produto.objects.get(nome='Óleo de soja')
        cls.usuario = get_user_model().objects.create_user('cliente_demonstrativo', password=None)

    def setUp(self):
        self.client.force_login(self.usuario)
        for produto, quantidade in ((self.arroz, 2), (self.oleo, 3)):
            self.client.post(reverse('principal:adicionar_ao_carrinho', args=[produto.pk]), {'quantidade': str(quantidade)})
        self.subtotal = self.arroz.preco * 2 + self.oleo.preco * 3

    def test_bairro_demonstrativo_e_a_opcao_valida_e_a_taxa_e_cinco_reais(self):
        resposta = self.client.get(reverse('principal:checkout'))
        self.assertIsNone(resposta.context['bloqueio'])
        self.assertContains(resposta, f'<option value="{BAIRRO_DEMONSTRATIVO}">{BAIRRO_DEMONSTRATIVO}</option>', html=True)
        self.assertEqual(resposta.context['revisao'].taxa_entrega, TAXA_DEMONSTRATIVA)
        for valor in (self.subtotal, TAXA_DEMONSTRATIVA, self.subtotal + TAXA_DEMONSTRATIVA):
            self.assertContains(resposta, reais(valor))

    def test_compra_com_configuracao_demonstrativa_e_valores_do_servidor(self):
        token = self.client.get(reverse('principal:checkout')).context['token']
        manipulados = {'taxa_entrega': '0.00', 'total': '0.01', 'subtotal': '0.01', 'taxa': '0'}
        resposta = self.client.post(reverse('principal:checkout'), {**ENTREGA, **manipulados, 'revisao': token})
        pedido = Pedido.objects.get()
        self.assertRedirects(resposta, reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertEqual((pedido.subtotal, pedido.taxa_entrega, pedido.total),
                         (self.subtotal, TAXA_DEMONSTRATIVA, self.subtotal + TAXA_DEMONSTRATIVA))
        self.assertEqual((pedido.bairro, pedido.cliente, pedido.estado), (BAIRRO_DEMONSTRATIVO, self.usuario, 'recebido'))
        self.assertNotIn(CHAVE_SESSAO, self.client.session)
        confirmacao = self.client.get(reverse('principal:confirmacao_pedido', args=[pedido.pk]))
        self.assertContains(confirmacao, reais(self.subtotal + TAXA_DEMONSTRATIVA))

    def test_bairro_fora_da_lista_e_recusado(self):
        token = self.client.get(reverse('principal:checkout')).context['token']
        resposta = self.client.post(reverse('principal:checkout'), {**ENTREGA, 'bairro': 'Centro', 'revisao': token})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('bairro', resposta.context['form'].errors)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_busca_filtros_e_ordenacao_com_acentos_continuam_funcionando(self):
        mercearia = Categoria.objects.get(nome='Mercearia')
        busca = self.client.get(reverse('principal:catalogo'), {'q': 'OLEO', 'categoria': mercearia.pk})
        self.assertEqual([p.nome for p in busca.context['produtos']], ['Óleo de soja'])
        nomes = [p.nome for p in self.client.get(reverse('principal:catalogo')).context['produtos']]
        self.assertEqual(nomes[:3], ['Açúcar cristal', 'Água mineral sem gás', 'Água sanitária'])
        self.assertLess(nomes.index('Macarrão espaguete'), nomes.index('Óleo de soja'))
        self.assertLess(nomes.index('Óleo de soja'), nomes.index('Refrigerante sabor cola'))
