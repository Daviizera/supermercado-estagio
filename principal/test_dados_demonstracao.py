"""Comando preparar_dados_demonstracao: idempotente, não destrutivo e restrito a development."""
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from .management.commands.preparar_dados_demonstracao import PRODUTOS_DEMONSTRACAO
from .models import Categoria, Pedido, Produto

CATEGORIAS = sorted({item[0] for item in PRODUTOS_DEMONSTRACAO})


def executar():
    saida = StringIO()
    call_command('preparar_dados_demonstracao', stdout=saida)
    return saida.getvalue()


class PrepararDadosDemonstracaoTests(TestCase):
    def test_cria_categorias_e_produtos_previstos(self):
        saida = executar()
        self.assertEqual(sorted(Categoria.objects.values_list('nome', flat=True)), CATEGORIAS)
        self.assertEqual(Produto.objects.count(), len(PRODUTOS_DEMONSTRACAO))
        for nome_categoria, nome, preco, unidade in PRODUTOS_DEMONSTRACAO:
            produto = Produto.objects.get(categoria__nome=nome_categoria, nome=nome)
            self.assertEqual((produto.preco, produto.unidade, produto.ativo), (Decimal(preco), unidade, True))
        self.assertIn(f'Resumo: {len(CATEGORIAS)} categoria(s) e {len(PRODUTOS_DEMONSTRACAO)} produto(s) criados', saida)

    def test_segunda_execucao_nao_duplica(self):
        executar()
        antes = list(Produto.objects.order_by('pk').values_list('pk', 'nome', 'preco'))
        saida = executar()
        self.assertEqual(list(Produto.objects.order_by('pk').values_list('pk', 'nome', 'preco')), antes)
        self.assertEqual(Categoria.objects.count(), len(CATEGORIAS))
        self.assertIn('Resumo: 0 categoria(s) e 0 produto(s) criados', saida)

    def test_registros_existentes_nao_sao_alterados(self):
        mercearia = Categoria.objects.create(nome='Mercearia')
        existente = Produto.objects.create(categoria=mercearia, nome='Arroz branco tipo 1',
                                           preco=Decimal('99.99'), unidade='unidade antiga', ativo=False)
        outro = Produto.objects.create(categoria=mercearia, nome='Produto anterior de teste',
                                       preco=Decimal('1.00'), unidade='un')
        saida = executar()
        existente.refresh_from_db()
        self.assertEqual((existente.preco, existente.unidade, existente.ativo), (Decimal('99.99'), 'unidade antiga', False))
        self.assertTrue(Produto.objects.filter(pk=outro.pk).exists())
        self.assertEqual(Produto.objects.filter(nome='Arroz branco tipo 1').count(), 1)
        self.assertIn('Categorias já existentes (mantidas): 1', saida)
        self.assertIn('Produtos já existentes (mantidos): 1', saida)

    def test_nao_cria_usuarios_nem_pedidos(self):
        executar()
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_recusa_ambiente_diferente_de_development(self):
        for ambiente in ('production', None):
            with self.subTest(ambiente=ambiente), override_settings(AMBIENTE=ambiente):
                with self.assertRaisesMessage(CommandError, 'somente com DJANGO_ENV=development'):
                    executar()
        self.assertEqual(Categoria.objects.count(), 0)
        self.assertEqual(Produto.objects.count(), 0)

    def test_falha_no_meio_nao_deixa_registros_parciais(self):
        original = Produto.full_clean
        chamadas = []

        def falhar_no_quinto(produto, *args, **kwargs):
            chamadas.append(produto.nome)
            if len(chamadas) == 5:
                raise ValidationError('falha simulada')
            return original(produto, *args, **kwargs)

        with mock.patch.object(Produto, 'full_clean', falhar_no_quinto), self.assertRaises(ValidationError):
            executar()
        self.assertEqual(Categoria.objects.count(), 0)
        self.assertEqual(Produto.objects.count(), 0)

    def test_dados_cobrem_os_cenarios_da_demonstracao(self):
        precos = [Decimal(item[2]) for item in PRODUTOS_DEMONSTRACAO]
        nomes = [item[1] for item in PRODUTOS_DEMONSTRACAO]
        self.assertGreaterEqual(len(CATEGORIAS), 4)
        self.assertLess(min(precos), Decimal('5.00'))
        self.assertGreater(max(precos), Decimal('30.00'))
        self.assertTrue(any(len(n) <= 15 for n in nomes) and any(len(n) >= 50 for n in nomes))
        self.assertEqual(len(set(zip((i[0] for i in PRODUTOS_DEMONSTRACAO), nomes))), len(PRODUTOS_DEMONSTRACAO))
        for preco in precos:
            self.assertEqual(preco, preco.quantize(Decimal('0.01')))
