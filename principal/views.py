from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

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
