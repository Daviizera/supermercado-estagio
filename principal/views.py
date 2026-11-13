from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from .carrinho import (
    Carrinho, ItemAusente, ItemInconsistente, ProdutoIndisponivel, QuantidadeAcimaDoLimite,
    QuantidadeInvalida,
)
from .forms import MENSAGEM_QUANTIDADE_INVALIDA, FiltroCatalogoForm, QuantidadeCarrinhoForm
from .models import Produto

MENSAGEM_PRODUTO_INDISPONIVEL = 'Este produto não está disponível.'
MENSAGEM_ITEM_AUSENTE = 'Este item não está no carrinho.'
MENSAGEM_ITEM_INCONSISTENTE = (
    'A quantidade registrada para este item é inválida. Atualize a quantidade ou remova o item.'
)


def _erro_de_quantidade(form, erro):
    """Leva ao campo do formulário uma recusa de quantidade feita pelo serviço."""
    if isinstance(erro, QuantidadeAcimaDoLimite):
        mensagem = f'A quantidade total no carrinho não pode ultrapassar {erro.limite}.'
    else:
        mensagem = MENSAGEM_QUANTIDADE_INVALIDA
    form.add_error('quantidade', mensagem)


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
    form = QuantidadeCarrinhoForm(initial={'quantidade': 1})
    return render(request, 'principal/detalhe_produto.html', {'produto': produto, 'form': form})


def _form_da_linha(produto_id, **kwargs):
    # IDs distintos por linha mantêm cada label associado ao próprio campo.
    return QuantidadeCarrinhoForm(auto_id=f'id_%s_{produto_id}', **kwargs)


def _render_carrinho(request, linha_com_erro=None, form_com_erro=None):
    resumo = Carrinho(request.session).resumo()
    itens = []
    for linha in resumo.linhas:
        if linha.produto_id == linha_com_erro:
            form = form_com_erro
        else:
            form = _form_da_linha(linha.produto_id, initial={'quantidade': linha.quantidade})
        itens.append({'linha': linha, 'form': form})
    return render(request, 'principal/carrinho.html', {'resumo': resumo, 'itens': itens})


@require_safe
@never_cache
def carrinho(request):
    """Somente lê a sessão: produtos excluídos ou inativos continuam listados até a remoção."""
    return _render_carrinho(request)


@require_POST
def adicionar_ao_carrinho(request, pk):
    # O preço não é recebido: somente o identificador da rota e a quantidade são usados.
    produto = Produto.objects.filter(ativo=True, pk=pk).select_related('categoria').first()
    if produto is None:
        messages.error(request, MENSAGEM_PRODUTO_INDISPONIVEL)
        return redirect('principal:catalogo')
    form = QuantidadeCarrinhoForm(request.POST)
    if form.is_valid():
        try:
            Carrinho(request.session).adicionar(produto, form.cleaned_data['quantidade'])
        except QuantidadeInvalida as erro:
            _erro_de_quantidade(form, erro)
        except ProdutoIndisponivel:
            # O serviço reconfirma no banco: o produto pode ter sido desativado neste intervalo.
            messages.error(request, MENSAGEM_PRODUTO_INDISPONIVEL)
            return redirect('principal:catalogo')
        except ItemInconsistente:
            messages.error(request, MENSAGEM_ITEM_INCONSISTENTE)
            return redirect('principal:carrinho')
        else:
            messages.success(request, f'{produto.nome} adicionado ao carrinho.')
            return redirect('principal:carrinho')
    # Erro de quantidade: o produto é reapresentado com o formulário e o carrinho fica intacto.
    return render(request, 'principal/detalhe_produto.html', {'produto': produto, 'form': form})


@require_POST
def atualizar_item_carrinho(request, pk):
    carrinho_sessao = Carrinho(request.session)
    if not carrinho_sessao.contem(pk):
        messages.error(request, MENSAGEM_ITEM_AUSENTE)
        return redirect('principal:carrinho')
    produto = Produto.objects.filter(ativo=True, pk=pk).first()
    if produto is None:
        # Item indisponível só pode ser removido; sua quantidade não é alterada.
        messages.error(request, f'{MENSAGEM_PRODUTO_INDISPONIVEL} Remova o item do carrinho.')
        return redirect('principal:carrinho')
    form = _form_da_linha(pk, data=request.POST)
    if form.is_valid():
        try:
            carrinho_sessao.definir_quantidade(produto, form.cleaned_data['quantidade'])
        except QuantidadeInvalida as erro:
            _erro_de_quantidade(form, erro)
        except ProdutoIndisponivel:
            messages.error(request, f'{MENSAGEM_PRODUTO_INDISPONIVEL} Remova o item do carrinho.')
            return redirect('principal:carrinho')
        except ItemAusente:
            messages.error(request, MENSAGEM_ITEM_AUSENTE)
            return redirect('principal:carrinho')
        else:
            messages.success(request, 'Quantidade atualizada.')
            return redirect('principal:carrinho')
    # A quantidade anterior permanece na sessão; o erro é exibido na linha do item.
    return _render_carrinho(request, linha_com_erro=pk, form_com_erro=form)


@require_POST
def remover_item_carrinho(request, pk):
    # A remoção não depende do banco, permitindo excluir entradas de produtos apagados.
    if Carrinho(request.session).remover(pk):
        messages.success(request, 'Item removido do carrinho.')
    else:
        messages.error(request, MENSAGEM_ITEM_AUSENTE)
    return redirect('principal:carrinho')
