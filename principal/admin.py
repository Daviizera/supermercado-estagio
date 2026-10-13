from django.contrib import admin

from .models import Categoria, Produto


# Pedidos e itens ficam fora do Admin; sua operação pertence à Semana 8.
@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome')
    search_fields = ('nome',)
    ordering = ('nome',)


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome', 'categoria', 'preco', 'unidade', 'ativo')
    search_fields = ('nome',)
    list_filter = ('categoria', 'ativo')
    ordering = ('nome',)
    list_select_related = ('categoria',)
