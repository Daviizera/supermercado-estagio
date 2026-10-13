from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from .models import Categoria, EstadoPedido, ItemPedido, Pedido, Produto


class DadosModelosTests(TestCase):
    """Dados artificiais restritos ao banco temporário de testes do Django."""

    @classmethod
    def setUpTestData(cls):
        cls.categoria = Categoria.objects.create(nome='Categoria de teste')
        cls.produto = Produto.objects.create(
            categoria=cls.categoria,
            nome='Produto de teste',
            preco=Decimal('4.50'),
            unidade='pacote de teste',
        )
        cls.cliente = get_user_model().objects.create_user(
            username='cliente_testes_modelos', password=None,
        )
        cls.pedido = Pedido.objects.create(
            cliente=cls.cliente,
            logradouro='Rua de teste',
            numero='s/n',
            complemento='',
            bairro='Bairro de teste',
            telefone='11999990000',
            subtotal=Decimal('9.00'),
            taxa_entrega=Decimal('3.00'),
            total=Decimal('12.00'),
        )
        cls.item = ItemPedido.objects.create(
            pedido=cls.pedido,
            produto=cls.produto,
            nome_produto='Produto de teste',
            unidade='pacote de teste',
            quantidade=2,
            preco_unitario=Decimal('4.50'),
        )

    def assert_campo_invalido(self, objeto, campo, valor):
        setattr(objeto, campo, valor)
        with self.assertRaises(ValidationError) as erro:
            objeto.full_clean()
        self.assertIn(campo, erro.exception.message_dict)

    def assert_banco_rejeita(self, objeto, campo, valor):
        """Isola o erro em um savepoint para manter utilizável a transação do teste."""
        # update() não chama full_clean(): a rejeição deve vir do banco.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                type(objeto).objects.filter(pk=objeto.pk).update(**{campo: valor})


class CategoriaProdutoTests(DadosModelosTests):
    def test_categoria_persistida_pode_ser_recuperada(self):
        categoria = Categoria.objects.get(pk=self.categoria.pk)
        self.assertEqual(categoria.nome, 'Categoria de teste')
        categoria.full_clean()

    def test_categoria_exige_nome_na_validacao_e_no_banco(self):
        self.assert_campo_invalido(self.categoria, 'nome', '')
        self.assert_banco_rejeita(self.categoria, 'nome', '')

    def test_categoria_duplicada_e_rejeitada_na_validacao_e_no_banco(self):
        duplicada = Categoria(nome=self.categoria.nome)
        with self.assertRaises(ValidationError) as erro:
            duplicada.full_clean()
        self.assertIn('nome', erro.exception.message_dict)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicada.save()

    def test_produto_persiste_categoria_preco_unidade_e_disponibilidade(self):
        produto = Produto.objects.get(pk=self.produto.pk)
        self.assertEqual(produto.categoria, self.categoria)
        self.assertEqual(produto.preco, Decimal('4.50'))
        self.assertIsInstance(produto.preco, Decimal)
        self.assertEqual(produto.unidade, 'pacote de teste')
        self.assertTrue(produto.ativo)
        produto.ativo = False
        produto.full_clean()
        produto.save()
        produto.refresh_from_db()
        self.assertFalse(produto.ativo)

    def test_produto_exige_nome_unidade_e_categoria(self):
        for campo, valor in [('nome', ''), ('unidade', ''), ('categoria', None)]:
            with self.subTest(campo=campo):
                self.produto.refresh_from_db()
                self.assert_campo_invalido(self.produto, campo, valor)
                self.assert_banco_rejeita(self.produto, campo, valor)

    def test_preco_produto_invalido_e_rejeitado_por_full_clean(self):
        for valor in [Decimal('-0.01'), Decimal('1.001'), Decimal('100000000.00'), None]:
            with self.subTest(preco=valor):
                self.assert_campo_invalido(self.produto, 'preco', valor)

    def test_banco_rejeita_preco_produto_negativo_ou_nulo(self):
        for valor in [Decimal('-0.01'), None]:
            with self.subTest(preco=valor):
                self.assert_banco_rejeita(self.produto, 'preco', valor)

    def test_categoria_com_produto_nao_pode_ser_excluida(self):
        with self.assertRaises(ProtectedError):
            self.categoria.delete()
        self.assertTrue(Categoria.objects.filter(pk=self.categoria.pk).exists())
        self.assertTrue(Produto.objects.filter(pk=self.produto.pk).exists())


class IntegridadeBancoTests(DadosModelosTests):
    def test_banco_rejeita_referencias_a_registros_inexistentes(self):
        referencias = [
            (self.produto, 'categoria_id', Categoria),
            (self.pedido, 'cliente_id', get_user_model()),
            (self.item, 'pedido_id', Pedido),
            (self.item, 'produto_id', Produto),
        ]
        for objeto, campo, modelo_referenciado in referencias:
            with self.subTest(modelo=type(objeto).__name__, campo=campo):
                id_inexistente = modelo_referenciado.objects.order_by('-pk').first().pk + 1
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        type(objeto).objects.filter(pk=objeto.pk).update(
                            **{campo: id_inexistente}
                        )
                        # SQLite pode adiar a checagem de FK até o commit.
                        connection.check_constraints()

    def test_valores_monetarios_zero_sao_validos_e_persistidos(self):
        campos = [
            (self.produto, 'preco'),
            (self.pedido, 'subtotal'),
            (self.pedido, 'taxa_entrega'),
            (self.pedido, 'total'),
            (self.item, 'preco_unitario'),
        ]
        for objeto, campo in campos:
            with self.subTest(modelo=type(objeto).__name__, campo=campo):
                setattr(objeto, campo, Decimal('0.00'))
                objeto.full_clean()
                objeto.save()
                objeto.refresh_from_db()
                self.assertEqual(getattr(objeto, campo), Decimal('0.00'))


class PedidoTests(DadosModelosTests):
    def test_pedido_persiste_cliente_endereco_valores_e_estado_inicial(self):
        pedido = Pedido.objects.get(pk=self.pedido.pk)
        pedido.full_clean()
        self.assertEqual(pedido.cliente, self.cliente)
        self.assertEqual(pedido.logradouro, 'Rua de teste')
        self.assertEqual(pedido.numero, 's/n')
        self.assertEqual(pedido.complemento, '')
        self.assertEqual(pedido.bairro, 'Bairro de teste')
        self.assertEqual(pedido.telefone, '11999990000')
        self.assertEqual(pedido.subtotal, Decimal('9.00'))
        self.assertEqual(pedido.taxa_entrega, Decimal('3.00'))
        self.assertEqual(pedido.total, Decimal('12.00'))
        self.assertIsInstance(pedido.total, Decimal)
        self.assertEqual(pedido.estado, EstadoPedido.RECEBIDO)
        self.assertEqual(pedido.pagamento, 'na_entrega')
        self.assertIsNotNone(pedido.criado_em)

    def test_pedido_exige_cliente_e_campos_essenciais_da_entrega(self):
        campos = [
            ('cliente', None), ('logradouro', ''), ('numero', ''),
            ('bairro', ''), ('telefone', ''),
        ]
        for campo, valor in campos:
            with self.subTest(campo=campo):
                self.pedido.refresh_from_db()
                self.assert_campo_invalido(self.pedido, campo, valor)
                self.assert_banco_rejeita(self.pedido, campo, valor)

    def test_valores_monetarios_invalidos_do_pedido_falham_na_validacao(self):
        valores = [Decimal('-0.01'), Decimal('1.001'), Decimal('10000000000.00'), None]
        for campo in ['subtotal', 'taxa_entrega', 'total']:
            for valor in valores:
                with self.subTest(campo=campo, valor=valor):
                    self.pedido.refresh_from_db()
                    self.assert_campo_invalido(self.pedido, campo, valor)

    def test_banco_rejeita_valores_monetarios_negativos_ou_nulos_no_pedido(self):
        for campo in ['subtotal', 'taxa_entrega', 'total']:
            for valor in [Decimal('-0.01'), None]:
                with self.subTest(campo=campo, valor=valor):
                    self.assert_banco_rejeita(self.pedido, campo, valor)

    def test_estado_e_pagamento_invalidos_falham_na_validacao_e_no_banco(self):
        for campo, valor in [('estado', 'inexistente'), ('pagamento', 'online')]:
            with self.subTest(campo=campo):
                self.pedido.refresh_from_db()
                self.assert_campo_invalido(self.pedido, campo, valor)
                self.assert_banco_rejeita(self.pedido, campo, valor)

    def test_cliente_com_pedido_nao_pode_ser_excluido(self):
        with self.assertRaises(ProtectedError):
            self.cliente.delete()
        self.assertTrue(get_user_model().objects.filter(pk=self.cliente.pk).exists())
        self.assertTrue(Pedido.objects.filter(pk=self.pedido.pk).exists())


class ItemPedidoTests(DadosModelosTests):
    def test_item_persiste_associacoes_quantidade_e_campos_historicos(self):
        item = ItemPedido.objects.get(pk=self.item.pk)
        item.full_clean()
        self.assertEqual(item.pedido, self.pedido)
        self.assertEqual(item.produto, self.produto)
        self.assertEqual(item.nome_produto, 'Produto de teste')
        self.assertEqual(item.unidade, 'pacote de teste')
        self.assertEqual(item.quantidade, 2)
        self.assertIsInstance(item.quantidade, int)
        self.assertEqual(item.preco_unitario, Decimal('4.50'))
        self.assertIsInstance(item.preco_unitario, Decimal)

    def test_item_exige_relacionamentos_e_textos_historicos(self):
        campos = [
            ('pedido', None), ('produto', None),
            ('nome_produto', ''), ('unidade', ''),
        ]
        for campo, valor in campos:
            with self.subTest(campo=campo):
                self.item.refresh_from_db()
                self.assert_campo_invalido(self.item, campo, valor)
                self.assert_banco_rejeita(self.item, campo, valor)

    def test_quantidade_zero_negativa_ou_nula_falha_na_validacao_e_no_banco(self):
        for valor in [0, -1, None]:
            with self.subTest(quantidade=valor):
                self.assert_campo_invalido(self.item, 'quantidade', valor)
                self.assert_banco_rejeita(self.item, 'quantidade', valor)

    def test_preco_unitario_invalido_falha_na_validacao(self):
        for valor in [Decimal('-0.01'), Decimal('1.001'), Decimal('100000000.00'), None]:
            with self.subTest(preco=valor):
                self.assert_campo_invalido(self.item, 'preco_unitario', valor)

    def test_banco_rejeita_preco_unitario_negativo_ou_nulo(self):
        for valor in [Decimal('-0.01'), None]:
            with self.subTest(preco=valor):
                self.assert_banco_rejeita(self.item, 'preco_unitario', valor)

    def test_produto_e_pedido_referenciados_por_item_nao_podem_ser_excluidos(self):
        for objeto in [self.produto, self.pedido]:
            with self.subTest(modelo=type(objeto).__name__):
                with self.assertRaises(ProtectedError):
                    objeto.delete()
                self.assertTrue(type(objeto).objects.filter(pk=objeto.pk).exists())
        self.assertTrue(ItemPedido.objects.filter(pk=self.item.pk).exists())

    def test_mudar_produto_nao_modifica_historico_do_item_ou_valores_do_pedido(self):
        self.produto.nome = 'Nome atual alterado'
        self.produto.unidade = 'outra unidade de teste'
        self.produto.preco = Decimal('99.90')
        self.produto.ativo = False
        self.produto.save()
        self.item.refresh_from_db()
        self.pedido.refresh_from_db()
        self.assertEqual(self.item.nome_produto, 'Produto de teste')
        self.assertEqual(self.item.unidade, 'pacote de teste')
        self.assertEqual(self.item.preco_unitario, Decimal('4.50'))
        self.assertEqual(self.item.quantidade, 2)
        self.assertEqual(self.pedido.subtotal, Decimal('9.00'))
        self.assertEqual(self.pedido.taxa_entrega, Decimal('3.00'))
        self.assertEqual(self.pedido.total, Decimal('12.00'))
