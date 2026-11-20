from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from . import checkout as servico_checkout
from . import pedidos as servico_pedidos
from .busca import Normalizado, normalizar_texto
from .carrinho import (
    Carrinho, ItemAusente, ItemInconsistente, ProdutoIndisponivel, QuantidadeAcimaDoLimite,
    QuantidadeInvalida,
)
from .forms import (
    MENSAGEM_QUANTIDADE_INVALIDA, EntregaForm, FiltroCatalogoForm, FormularioLogin,
    QuantidadeCarrinhoForm,
)
from .models import EstadoPedido, Pedido, Produto

# Verbos exibidos nos botões do painel; o valor enviado continua sendo o estado de destino.
ROTULOS_ACOES_EQUIPE = {
    EstadoPedido.CONFIRMADO: 'Confirmar pedido',
    EstadoPedido.EM_PREPARO: 'Iniciar preparo',
    EstadoPedido.SAIU_PARA_ENTREGA: 'Registrar saída para entrega',
    EstadoPedido.ENTREGUE: 'Concluir entrega',
    EstadoPedido.CANCELADO: 'Cancelar pedido',
}

MENSAGEM_PEDIDO_NAO_ENCONTRADO = 'Pedido não encontrado ou acesso não permitido.'
MENSAGEM_ENTRE_PARA_PEDIDOS = 'Entre para consultar seus pedidos.'
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


class EntrarView(LoginView):
    """Login nativo; acrescenta a mensagem da Tela 6 quando o destino é Meus pedidos.

    O destino comparado é o já validado pelo Django (get_redirect_url aplica
    url_has_allowed_host_and_scheme): um next externo resulta em '' e não exibe a mensagem.
    A mensagem vai no contexto, não no framework de mensagens, para não se acumular.
    O formulário acrescenta a limitação de tentativas (principal/limite_login.py).
    """

    authentication_form = FormularioLogin

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        if self.get_redirect_url() == reverse('principal:meus_pedidos'):
            contexto['aviso_destino'] = MENSAGEM_ENTRE_PARA_PEDIDOS
        return contexto


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
    # Ordem alfabética sem distinção de caixa e acentos (F-02); nome e pk desempatam nomes
    # equivalentes de forma estável.
    produtos = (
        Produto.objects.filter(ativo=True).select_related('categoria')
        .annotate(nome_normalizado=Normalizado('nome'))
        .order_by('nome_normalizado', 'nome', 'pk')
    )
    filtros_ativos = False
    if form.is_valid():
        categoria = form.cleaned_data['categoria']
        pesquisa = form.cleaned_data['q']
        if categoria:
            produtos = produtos.filter(categoria=categoria)
        if pesquisa:
            # Busca parcial comparando textos normalizados: 'agua' encontra 'Água' (F-01).
            produtos = produtos.filter(nome_normalizado__contains=normalizar_texto(pesquisa))
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


@require_POST
def remover_entradas_nao_identificadas(request):
    """Remove apenas registros sem produto identificável; itens válidos são preservados."""
    removidas = Carrinho(request.session).remover_entradas_nao_identificadas()
    if removidas:
        messages.success(request, f'{removidas} registro(s) não identificado(s) removido(s) do carrinho.')
    else:
        messages.info(request, 'Não há registros não identificados no carrinho.')
    return redirect('principal:carrinho')


def _render_checkout(request, *, form=None, base=None, revisao=None, conteudo_anterior=None):
    """Apresenta a revisão com valores do servidor; nunca grava pedido nem sessão."""
    contexto = {'bloqueio': None, 'revisao': None, 'token': None, 'form': form}
    try:
        configuracao = servico_checkout.obter_configuracao()
        if revisao is None:
            revisao = servico_checkout.montar_revisao(request.session, configuracao)
    except servico_checkout.ErroCheckout as erro:
        contexto['bloqueio'] = erro.mensagem
        return render(request, 'principal/checkout.html', contexto)
    if conteudo_anterior is not None and revisao.conteudo() != conteudo_anterior:
        messages.warning(request, servico_checkout.RevisaoDesatualizada.mensagem)
    if contexto['form'] is None:
        contexto['form'] = EntregaForm(configuracao=configuracao)
    contexto['revisao'] = revisao
    # Reapresentações mantêm a base recebida; uma nova abertura usa o último pedido atual.
    if base is None:
        base = servico_checkout.pedido_base(request.user)
    contexto['token'] = servico_checkout.assinar_revisao(revisao, base, request.user)
    return render(request, 'principal/checkout.html', contexto)


def _entrega_enviada(request):
    """Formulário vinculado aos dados de entrega do POST, ou None se a entrega não está disponível.

    Contém somente os campos de endereço; valores e revisão continuam calculados no servidor.
    """
    try:
        configuracao = servico_checkout.obter_configuracao()
    except servico_checkout.CheckoutIndisponivel:
        return None
    return EntregaForm(request.POST, configuracao=configuracao)


@login_required
@never_cache
@require_http_methods(['GET', 'HEAD', 'POST'])
def checkout(request):
    if request.method != 'POST':
        return _render_checkout(request)

    try:
        # A chave é derivada no servidor a partir do usuário e da base assinada.
        lida = servico_checkout.ler_revisao(request.POST.get('revisao'), request.user)
        # Reenvio de uma tentativa já concluída devolve o mesmo pedido, sem tocar no carrinho;
        # sem pedido, a base precisa ser o último pedido atual do usuário.
        existente = servico_checkout.pedido_da_tentativa(request.user, lida.base, lida.chave)
    except servico_checkout.ErroCheckout as erro:
        messages.error(request, erro.mensagem)
        # Nova revisão calculada no servidor, preservando o endereço digitado (RNF-005).
        return _render_checkout(request, form=_entrega_enviada(request))
    if existente is not None:
        return redirect('principal:confirmacao_pedido', pk=existente.pk)

    try:
        configuracao = servico_checkout.obter_configuracao()
    except servico_checkout.CheckoutIndisponivel:
        return _render_checkout(request)
    form = EntregaForm(request.POST, configuracao=configuracao)
    if not form.is_valid():
        return _render_checkout(
            request, form=form, base=lida.base, conteudo_anterior=lida.conteudo,
        )

    try:
        resultado = servico_checkout.registrar_pedido(
            usuario=request.user, sessao=request.session, base=lida.base,
            conteudo_revisado=lida.conteudo, entrega=form.cleaned_data,
        )
    except servico_checkout.RevisaoDesatualizada as erro:
        messages.warning(request, erro.mensagem)
        return _render_checkout(request, form=form, base=lida.base, revisao=erro.revisao)
    except servico_checkout.LimiteExcedido as erro:
        return _render_checkout(request, form=form, base=lida.base, revisao=erro.revisao)
    except (servico_checkout.ChaveDeOutroCliente, servico_checkout.BaseDesatualizada) as erro:
        # Nova revisão com a base atual; a base recusada não é reaproveitada.
        messages.error(request, erro.mensagem)
        return _render_checkout(request, form=form)
    except servico_checkout.ErroCheckout as erro:
        messages.error(request, erro.mensagem)
        return _render_checkout(request, form=form, base=lida.base)

    if resultado.criado:
        # Somente depois da transação confirmada; remove apenas a chave do carrinho.
        Carrinho(request.session).esvaziar()
        messages.success(request, 'Pedido registrado com sucesso.')
    return redirect('principal:confirmacao_pedido', pk=resultado.pedido.pk)


def _itens_com_valor(pedido):
    """Itens com o valor da linha calculado a partir dos dados históricos registrados."""
    return [
        {'item': item, 'valor': item.quantidade * item.preco_unitario}
        for item in pedido.itens.all()
    ]


def _render_pedido_do_cliente(request, pk, titulo):
    # A consulta filtra pelo usuário da sessão. Pedido inexistente ou de outro cliente recebe a
    # mesma resposta 404, sem dados e sem distinguir os dois casos (Tela 6).
    pedido = Pedido.objects.prefetch_related('itens').filter(pk=pk, cliente=request.user).first()
    if pedido is None:
        return render(
            request, 'principal/pedido_nao_encontrado.html',
            {'mensagem': MENSAGEM_PEDIDO_NAO_ENCONTRADO}, status=404,
        )
    return render(request, 'principal/confirmacao_pedido.html', {
        'pedido': pedido, 'itens': _itens_com_valor(pedido), 'titulo': titulo,
    })


@login_required
@never_cache
@require_safe
def confirmacao_pedido(request, pk):
    """Confirmação do pedido recém-registrado, restrita ao próprio cliente (RF-025)."""
    return _render_pedido_do_cliente(request, pk, 'Pedido registrado')


@login_required
@never_cache
@require_safe
def meus_pedidos(request):
    """Lista somente os pedidos do usuário da sessão, do mais recente ao mais antigo (RF-008)."""
    pedidos_do_cliente = Pedido.objects.filter(cliente=request.user).order_by('-criado_em', '-pk')
    return render(request, 'principal/meus_pedidos.html', {'pedidos': pedidos_do_cliente})


@login_required
@never_cache
@require_safe
def acompanhamento_pedido(request, pk):
    """Estado persistido no momento da consulta; sem atualização em tempo real (RF-026)."""
    return _render_pedido_do_cliente(request, pk, 'Acompanhamento do pedido')


# Área interna da equipe (RF-022 a RF-024)

def _acesso_negado(request):
    return render(
        request, 'principal/acesso_negado.html',
        {'mensagem': servico_pedidos.MENSAGEM_SEM_PERMISSAO}, status=403,
    )


def _area_interna(verificar):
    """Visitante vai ao login; autenticado sem is_staff e permissão recebe HTTP 403."""
    def decorador(view):
        @wraps(view)
        @login_required
        def protegida(request, *args, **kwargs):
            if not verificar(request.user):
                return _acesso_negado(request)
            return view(request, *args, **kwargs)
        return protegida
    return decorador


@require_safe
@never_cache
@_area_interna(servico_pedidos.pode_consultar)
def equipe_pedidos(request):
    pedidos_recebidos = Pedido.objects.select_related('cliente').order_by('-criado_em', '-pk')
    return render(request, 'principal/equipe_pedidos.html', {'pedidos': pedidos_recebidos})


@require_safe
@never_cache
@_area_interna(servico_pedidos.pode_consultar)
def equipe_pedido_detalhe(request, pk):
    pedido = get_object_or_404(
        Pedido.objects.select_related('cliente').prefetch_related('itens'), pk=pk,
    )
    acoes = []
    # Os botões são conveniência; a rota de alteração revalida permissão e transição.
    if servico_pedidos.pode_alterar(request.user):
        acoes = [
            {
                'estado': estado, 'rotulo': ROTULOS_ACOES_EQUIPE[estado],
                'perigo': estado == EstadoPedido.CANCELADO,
            }
            for estado in servico_pedidos.transicoes_permitidas(pedido.estado)
        ]
    return render(request, 'principal/equipe_pedido_detalhe.html', {
        'pedido': pedido, 'itens': _itens_com_valor(pedido), 'acoes': acoes,
        'terminal': not servico_pedidos.transicoes_permitidas(pedido.estado),
    })


@require_POST
@_area_interna(servico_pedidos.pode_alterar)
def equipe_alterar_estado(request, pk):
    try:
        resultado = servico_pedidos.alterar_estado(
            usuario=request.user, pedido_id=pk,
            estado_esperado=request.POST.get('estado_atual'),
            novo_estado=request.POST.get('novo_estado'),
        )
    except Pedido.DoesNotExist:
        raise Http404 from None
    except servico_pedidos.SemPermissao:
        return _acesso_negado(request)
    except servico_pedidos.ErroPedido as erro:
        messages.error(request, erro.mensagem)
    else:
        messages.success(request, (
            f'Pedido {pk}: {EstadoPedido(resultado.anterior).label} → '
            f'{EstadoPedido(resultado.novo).label}.'
        ))
    return redirect('principal:equipe_pedido_detalhe', pk=pk)
