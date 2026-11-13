from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_safe

from .forms import FiltroCatalogoForm
from .models import Produto

def inicio(request):
    return render(request, 'principal/inicio.html')


@sensitive_post_parameters('password1', 'password2')
@require_http_methods(['GET', 'POST'])
def cadastro(request):
    """Cria uma conta comum e exige login explícito após o cadastro."""
    form = UserCreationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Cadastro realizado com sucesso. Entre com seu usuário e senha.')
        return redirect('principal:login')
    return render(request, 'registration/cadastro.html', {'form': form})


@login_required
@never_cache
def minha_conta(request):
    """Identifica o cliente pela sessão, sem aceitar outro usuário por parâmetro."""
    return render(request, 'principal/minha_conta.html')


@require_safe
def catalogo(request):
    form = FiltroCatalogoForm(request.GET)
    produtos = Produto.objects.filter(ativo=True).select_related('categoria').order_by('nome', 'pk')
    filtros_ativos = False
    if form.is_valid():
        categoria = form.cleaned_data['categoria']
        pesquisa = form.cleaned_data['q']
        if categoria:
            produtos = produtos.filter(categoria=categoria)
        if pesquisa:
            produtos = produtos.filter(nome__icontains=pesquisa)
        filtros_ativos = bool(categoria or pesquisa)
    else:
        # Um filtro inválido não deve liberar a listagem sem o filtro solicitado.
        produtos = produtos.none()
    return render(request, 'principal/catalogo.html', {
        'form': form, 'produtos': produtos, 'filtros_ativos': filtros_ativos,
    })


@require_safe
def detalhe_produto(request, pk):
    # Aplicar a disponibilidade na consulta também protege o acesso direto pela URL.
    produto = get_object_or_404(
        Produto.objects.filter(ativo=True).select_related('categoria'), pk=pk,
    )
    return render(request, 'principal/detalhe_produto.html', {'produto': produto})
