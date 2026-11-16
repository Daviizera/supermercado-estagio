from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'principal'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('catalogo/', views.catalogo, name='catalogo'),
    path('produtos/<int:pk>/', views.detalhe_produto, name='detalhe_produto'),
    path('carrinho/', views.carrinho, name='carrinho'),
    path('carrinho/adicionar/<int:pk>/', views.adicionar_ao_carrinho, name='adicionar_ao_carrinho'),
    path('carrinho/atualizar/<int:pk>/', views.atualizar_item_carrinho, name='atualizar_item_carrinho'),
    path('carrinho/remover/<int:pk>/', views.remover_item_carrinho, name='remover_item_carrinho'),
    path(
        'carrinho/remover-nao-identificados/', views.remover_entradas_nao_identificadas,
        name='remover_entradas_nao_identificadas',
    ),
    path('checkout/', views.checkout, name='checkout'),
    path('pedidos/<int:pk>/confirmacao/', views.confirmacao_pedido, name='confirmacao_pedido'),
    path('pedidos/', views.meus_pedidos, name='meus_pedidos'),
    path('pedidos/<int:pk>/', views.acompanhamento_pedido, name='acompanhamento_pedido'),
    path('equipe/pedidos/', views.equipe_pedidos, name='equipe_pedidos'),
    path('equipe/pedidos/<int:pk>/', views.equipe_pedido_detalhe, name='equipe_pedido_detalhe'),
    path(
        'equipe/pedidos/<int:pk>/estado/', views.equipe_alterar_estado,
        name='equipe_alterar_estado',
    ),
    path('cadastro/', views.cadastro, name='cadastro'),
    path('login/', views.EntrarView.as_view(), name='login'),
    # O logout retorna ao início, sem aceitar destino enviado pelo cliente.
    path('logout/', LogoutView.as_view(redirect_field_name=None), name='logout'),
    path('minha-conta/', views.minha_conta, name='minha_conta'),
]
