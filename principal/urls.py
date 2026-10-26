from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

app_name = 'principal'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('cadastro/', views.cadastro, name='cadastro'),
    path('login/', LoginView.as_view(), name='login'),
    # O logout retorna ao início, sem aceitar destino enviado pelo cliente.
    path('logout/', LogoutView.as_view(redirect_field_name=None), name='logout'),
    path('minha-conta/', views.minha_conta, name='minha_conta'),
]
