import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator

from .carrinho import limite_tecnico_quantidade
from .models import Categoria

MENSAGEM_QUANTIDADE_INVALIDA = 'Informe uma quantidade inteira maior que zero.'


class FiltroCatalogoForm(forms.Form):
    """Valida os filtros GET antes de consultar os produtos disponíveis."""

    q = forms.CharField(
        label='Pesquisar por nome', required=False, max_length=150,
        widget=forms.TextInput(attrs={'type': 'search'}),
    )
    categoria = forms.ModelChoiceField(
        label='Categoria', required=False,
        queryset=Categoria.objects.order_by('nome', 'pk'),
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
