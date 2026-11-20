import re

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator

from . import checkout
from .busca import Normalizado
from .carrinho import limite_tecnico_quantidade
from .limite_login import LimiteDeTentativasMixin
from .models import Categoria, Pedido

MENSAGEM_QUANTIDADE_INVALIDA = 'Informe uma quantidade inteira maior que zero.'


class FiltroCatalogoForm(forms.Form):
    """Valida os filtros GET antes de consultar os produtos disponíveis."""

    q = forms.CharField(
        label='Pesquisar por nome', required=False, max_length=150,
        widget=forms.TextInput(attrs={'type': 'search'}),
    )
    categoria = forms.ModelChoiceField(
        label='Categoria', required=False,
        queryset=Categoria.objects.annotate(nome_normalizado=Normalizado('nome')).order_by(
            'nome_normalizado', 'nome', 'pk',
        ),
        empty_label='Todas as categorias',
        error_messages={'invalid_choice': 'Selecione uma categoria válida.'},
    )


class QuantidadeInteiraField(forms.IntegerField):
    """Aceita somente dígitos ASCII.

    O IntegerField nativo converte '2.0', '+2', '1_000' e dígitos não ASCII; aqui
    essas representações são rejeitadas antes da conversão.
    """

    def to_python(self, value):
        if value in self.empty_values:
            return None
        texto = str(value).strip()
        if not re.fullmatch(r'[0-9]+', texto):
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        # Zeros à esquerda não alteram o valor e não contam para o comprimento.
        texto = texto.lstrip('0') or '0'
        # Mais dígitos que o máximo já excede o limite; recusar antes de converter evita o
        # ValueError do Python para textos com mais de 4300 dígitos.
        if self.max_value is not None and len(texto) > len(str(self.max_value)):
            raise ValidationError(
                self.error_messages.get('max_value', MaxValueValidator.message),
                code='max_value', params={'limit_value': self.max_value},
            )
        # Conversão nativa do Django: ValueError/TypeError viram erro de validação.
        return super().to_python(texto)


class QuantidadeCarrinhoForm(forms.Form):
    """Valida a quantidade enviada para adicionar ou atualizar um item do carrinho."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O máximo vem do campo ItemPedido.quantidade, não de uma regra comercial.
        self.fields['quantidade'] = QuantidadeInteiraField(
            label='Quantidade', min_value=1, max_value=limite_tecnico_quantidade(),
            error_messages={
                'required': MENSAGEM_QUANTIDADE_INVALIDA,
                'invalid': MENSAGEM_QUANTIDADE_INVALIDA,
                'min_value': MENSAGEM_QUANTIDADE_INVALIDA,
                'max_value': 'Informe uma quantidade de no máximo %(limit_value)s.',
            },
        )


def _tamanho_entrega(campo):
    return Pedido._meta.get_field(campo).max_length


class EntregaForm(forms.Form):
    """Dados de entrega nos campos existentes de Pedido.

    As regras ficam em checkout.validar_entrega, também aplicada pelo serviço no registro;
    o formulário apenas associa os erros aos campos.
    """

    # Os atributos de preenchimento automático só auxiliam o navegador; a validação não muda.
    logradouro = forms.CharField(
        label='Logradouro', max_length=_tamanho_entrega('logradouro'),
        widget=forms.TextInput(attrs={'autocomplete': 'address-line1'}),
    )
    numero = forms.CharField(label='Número', max_length=_tamanho_entrega('numero'))
    complemento = forms.CharField(
        label='Complemento (opcional)', required=False, max_length=_tamanho_entrega('complemento'),
        widget=forms.TextInput(attrs={'autocomplete': 'address-line2'}),
    )
    bairro = forms.CharField(
        label='Bairro', max_length=_tamanho_entrega('bairro'), widget=forms.Select,
    )
    telefone = forms.CharField(
        label='Telefone', max_length=_tamanho_entrega('telefone'),
        widget=forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
    )

    def __init__(self, *args, configuracao=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuracao = configuracao
        bairros = configuracao.bairros if configuracao is not None else ()
        # A lista exibida vem da configuração central; o servidor revalida o valor enviado.
        self.fields['bairro'].widget.choices = (
            [('', 'Selecione um bairro atendido')] + [(bairro, bairro) for bairro in bairros]
        )
        for campo in self.fields.values():
            campo.error_messages['required'] = checkout.MENSAGEM_CAMPO_OBRIGATORIO

    def clean(self):
        dados = super().clean()
        if self.configuracao is None:
            raise ValidationError(checkout.CheckoutIndisponivel.mensagem)
        try:
            limpos = checkout.validar_entrega(dados, self.configuracao)
        except checkout.EntregaInvalida as erro:
            for campo, mensagem in erro.erros.items():
                if campo not in self.errors:
                    self.add_error(campo, mensagem)
            return dados
        dados.update(limpos)
        return dados


class FormularioLogin(LimiteDeTentativasMixin, AuthenticationForm):
    """Login do cliente: formulário nativo com limitação de tentativas (SEG-01)."""


class FormularioLoginAdmin(LimiteDeTentativasMixin, AdminAuthenticationForm):
    """Login do admin: mantém as regras nativas (is_staff, mensagens) e acrescenta o limite."""
