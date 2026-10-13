from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Categoria(models.Model):
    nome = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'categoria'
        verbose_name_plural = 'categorias'
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(nome=''),
                name='categoria_nome_preenchido',
            ),
        ]

    def __str__(self):
        return self.nome


class Produto(models.Model):
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name='produtos'
    )
    nome = models.CharField(max_length=150)
    preco = models.DecimalField(
        'preço', max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    unidade = models.CharField(max_length=30)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'produto'
        verbose_name_plural = 'produtos'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(preco__gte=0),
                name='produto_preco_nao_negativo',
            ),
            models.CheckConstraint(
                condition=~models.Q(nome='') & ~models.Q(unidade=''),
                name='produto_textos_preenchidos',
            ),
        ]

    def __str__(self):
        return self.nome


class EstadoPedido(models.TextChoices):
    RECEBIDO = 'recebido', 'Recebido'
    CONFIRMADO = 'confirmado', 'Confirmado'
    EM_PREPARO = 'em_preparo', 'Em preparo'
    SAIU_PARA_ENTREGA = 'saiu_para_entrega', 'Saiu para entrega'
    ENTREGUE = 'entregue', 'Entregue'
    CANCELADO = 'cancelado', 'Cancelado'


class Pedido(models.Model):
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pedidos'
    )
    # Estrutura mínima provisória; formatos comerciais dependem de D-004.
    logradouro = models.CharField(max_length=200)
    numero = models.CharField('número', max_length=20)
    complemento = models.CharField(max_length=150, blank=True)
    bairro = models.CharField(max_length=100)
    telefone = models.CharField(max_length=30)
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    taxa_entrega = models.DecimalField(
        'taxa de entrega', max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    pagamento = models.CharField(
        max_length=20,
        choices=[('na_entrega', 'Na entrega')],
        default='na_entrega',
    )
    estado = models.CharField(
        max_length=20,
        choices=EstadoPedido.choices,
        default=EstadoPedido.RECEBIDO,
    )
    criado_em = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        ordering = ['-criado_em', '-id']
        verbose_name = 'pedido'
        verbose_name_plural = 'pedidos'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0, taxa_entrega__gte=0, total__gte=0),
                name='pedido_valores_nao_negativos',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(logradouro='') & ~models.Q(numero='')
                    & ~models.Q(bairro='') & ~models.Q(telefone='')
                ),
                name='pedido_entrega_preenchida',
            ),
            models.CheckConstraint(
                condition=models.Q(pagamento='na_entrega'),
                name='pedido_pagamento_na_entrega',
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=EstadoPedido.values),
                name='pedido_estado_valido',
            ),
        ]

    def __str__(self):
        return f'Pedido {self.pk}'


class ItemPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido, on_delete=models.PROTECT, related_name='itens'
    )
    produto = models.ForeignKey(
        Produto, on_delete=models.PROTECT, related_name='itens_pedido'
    )
    # Valores históricos preenchidos explicitamente; captura automática na Semana 7.
    nome_produto = models.CharField('nome do produto', max_length=150)
    unidade = models.CharField(max_length=30)
    quantidade = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    preco_unitario = models.DecimalField(
        'preço unitário', max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )

    class Meta:
        ordering = ['id']
        verbose_name = 'item de pedido'
        verbose_name_plural = 'itens de pedido'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__gte=1),
                name='item_quantidade_positiva',
            ),
            models.CheckConstraint(
                condition=models.Q(preco_unitario__gte=0),
                name='item_preco_nao_negativo',
            ),
            models.CheckConstraint(
                condition=~models.Q(nome_produto='') & ~models.Q(unidade=''),
                name='item_historico_preenchido',
            ),
        ]

    def __str__(self):
        return f'{self.quantidade} × {self.nome_produto}'
