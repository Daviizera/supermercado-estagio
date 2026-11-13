from django import forms

from .models import Categoria


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
