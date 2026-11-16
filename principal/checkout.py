"""Finalização da compra: configuração, revisão assinada e registro atômico do pedido.

Requisitos: RF-007, RF-013 a RF-018 e RF-025; RN-008 a RN-017; RNF-004.
Bairros, taxa e limite vêm exclusivamente de supermercado/settings.py. As views apenas
convertem as exceções deste módulo em mensagens; as regras não dependem delas.
"""
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, Inexact, InvalidOperation, localcontext

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction

from .carrinho import PRECISAO_CALCULO, Carrinho
from .models import ItemPedido, Pedido, Produto

SAL_REVISAO = 'principal.checkout.revisao'
# Versão 2: revisão completa (nome, unidade, valores e bairros) e chave derivada da base.
VERSAO_REVISAO = 2

# Namespace fixo para derivar as chaves de idempotência com uuid5; não deve ser alterado,
# pois mudaria as chaves das tentativas em andamento.
NAMESPACE_CHAVES_PEDIDO = uuid.UUID('3554929d-94a5-4dd2-9d7d-3b7a43c00a4a')

# Após um erro de trava, nova consulta por até ~0,75 s (0,05 + 0,1 + 0,2 + 0,4).
TENTATIVAS_APOS_TRAVA = 5
ESPERA_INICIAL_APOS_TRAVA = 0.05

CAMPOS_ENTREGA = ('logradouro', 'numero', 'complemento', 'bairro', 'telefone')
CAMPOS_ENTREGA_OPCIONAIS = frozenset({'complemento'})

MENSAGEM_CAMPO_OBRIGATORIO = 'Preencha este campo obrigatório.'
MENSAGEM_BAIRRO_NAO_ATENDIDO = 'Bairro não atendido. Selecione um bairro da lista.'
MENSAGEM_CARRINHO_INCONSISTENTE = (
    'Há dados inconsistentes no carrinho. Corrija o carrinho para continuar.'
)
MENSAGEM_PRODUTO_INDISPONIVEL = 'Há produto indisponível no carrinho. Remova o item para continuar.'


class ErroCheckout(Exception):
    """Finalização recusada; nenhum pedido é criado e o carrinho não é alterado."""

    mensagem = 'Não foi possível finalizar a compra.'

    def __init__(self, mensagem=None):
        if mensagem is not None:
            self.mensagem = mensagem
        super().__init__(self.mensagem)


class CheckoutIndisponivel(ErroCheckout):
    """Bairros, taxa ou limite ausentes ou inválidos na configuração central."""

    mensagem = 'A entrega ainda não está disponível. Não é possível finalizar a compra no momento.'


class IdentificacaoNecessaria(ErroCheckout):
    mensagem = 'Entre na sua conta para finalizar a compra.'


class CarrinhoVazio(ErroCheckout):
    mensagem = 'Seu carrinho está vazio.'


class CarrinhoComProblemas(ErroCheckout):
    """Produto inativo, excluído ou entrada malformada no carrinho."""


class EntregaInvalida(ErroCheckout):
    mensagem = 'Corrija os dados de entrega.'

    def __init__(self, erros):
        super().__init__()
        self.erros = erros


class LimiteExcedido(ErroCheckout):
    def __init__(self, revisao):
        self.revisao = revisao
        super().__init__('O valor total do pedido ultrapassa o limite permitido.')


class RevisaoInvalida(ErroCheckout):
    mensagem = (
        'Não foi possível validar a revisão do pedido. Confira os valores e confirme novamente.'
    )


class RevisaoDesatualizada(ErroCheckout):
    """Preço, quantidade, itens ou taxa mudaram desde a revisão apresentada."""

    mensagem = 'Os valores foram atualizados. Confira antes de confirmar novamente.'

    def __init__(self, revisao):
        super().__init__()
        self.revisao = revisao


class BaseDesatualizada(RevisaoInvalida):
    """A base do token não é o último pedido atual do usuário e não gerou pedido."""

    mensagem = (
        'Esta revisão do pedido não é mais válida para suas compras. '
        'Confira os valores e confirme novamente.'
    )


class ChaveDeOutroCliente(ErroCheckout):
    """A chave pertence a pedido de outro usuário; nenhum dado dele é revelado."""

    mensagem = 'Não foi possível confirmar este pedido. Confira os valores e confirme novamente.'


class FalhaAoRegistrar(ErroCheckout):
    mensagem = 'Não foi possível registrar o pedido. Seu carrinho foi mantido.'


# Configuração central

def normalizar_bairro(texto):
    """Compara bairros sem diferenciar espaços repetidos ou maiúsculas; acentos são mantidos."""
    return ' '.join(texto.split()).casefold()


@dataclass(frozen=True)
class ConfiguracaoCheckout:
    bairros: tuple
    taxa_entrega: Decimal
    valor_maximo: Decimal

    def bairro_atendido(self, texto):
        """Nome configurado correspondente ao texto informado, ou None se não atendido."""
        if not isinstance(texto, str):
            return None
        procurado = normalizar_bairro(texto)
        for bairro in self.bairros:
            if normalizar_bairro(bairro) == procurado:
                return bairro
        return None


def _valor_monetario(valor, campo):
    """Decimal finito e não negativo que cabe no DecimalField indicado, sem arredondar.

    Zeros finais excedentes são aceitos ('1.000' equivale a '1.00'); qualquer outro dígito
    além das casas do campo exigiria arredondamento e torna o valor inválido.
    """
    if isinstance(valor, bool) or not isinstance(valor, Decimal):
        return None
    if not valor.is_finite() or valor < 0:
        return None
    try:
        with localcontext(prec=PRECISAO_CALCULO):
            normalizado = valor.quantize(Decimal(1).scaleb(-campo.decimal_places))
    except InvalidOperation:
        return None
    if normalizado != valor or len(normalizado.as_tuple().digits) > campo.max_digits:
        return None
    return normalizado


def _bairros_configurados(bruto):
    if not isinstance(bruto, (list, tuple, set, frozenset)):
        return None
    limite = Pedido._meta.get_field('bairro').max_length
    itens = sorted(bruto, key=str) if isinstance(bruto, (set, frozenset)) else bruto
    bairros, vistos = [], set()
    for bairro in itens:
        if not isinstance(bairro, str):
            return None
        nome = ' '.join(bairro.split())
        if not nome or len(nome) > limite:
            return None
        if nome.casefold() not in vistos:
            vistos.add(nome.casefold())
            bairros.append(nome)
    return tuple(bairros)


def obter_configuracao():
    """Lê e valida a configuração central a cada chamada; inválida ou ausente bloqueia."""
    bairros = _bairros_configurados(getattr(settings, 'CHECKOUT_BAIRROS_ATENDIDOS', None))
    taxa = _valor_monetario(
        getattr(settings, 'CHECKOUT_TAXA_ENTREGA', None), Pedido._meta.get_field('taxa_entrega'),
    )
    maximo = _valor_monetario(
        getattr(settings, 'CHECKOUT_VALOR_MAXIMO_PEDIDO', None), Pedido._meta.get_field('total'),
    )
    if not bairros or taxa is None or maximo is None or maximo <= 0:
        raise CheckoutIndisponivel()
    return ConfiguracaoCheckout(bairros, taxa, maximo)


# Entrega

def validar_entrega(dados, configuracao):
    """Valida os campos existentes em Pedido; o bairro é trocado pelo nome configurado."""
    erros, limpos = {}, {}
    for campo in CAMPOS_ENTREGA:
        valor = dados.get(campo)
        if valor is None:
            valor = ''
        if not isinstance(valor, str):
            erros[campo] = 'Informe um texto válido.'
            continue
        valor = valor.strip()
        maximo = Pedido._meta.get_field(campo).max_length
        if not valor and campo not in CAMPOS_ENTREGA_OPCIONAIS:
            erros[campo] = MENSAGEM_CAMPO_OBRIGATORIO
        elif len(valor) > maximo:
            erros[campo] = f'Informe no máximo {maximo} caracteres.'
        else:
            limpos[campo] = valor
    if 'bairro' in limpos:
        bairro = configuracao.bairro_atendido(limpos['bairro'])
        if bairro is None:
            erros['bairro'] = MENSAGEM_BAIRRO_NAO_ATENDIDO
        else:
            limpos['bairro'] = bairro
    if erros:
        raise EntregaInvalida(erros)
    return limpos


# Revisão

@dataclass(frozen=True)
class LinhaRevisao:
    produto: Produto
    quantidade: int
    valor: Decimal

    @property
    def preco(self):
        return self.produto.preco


@dataclass(frozen=True)
class Revisao:
    linhas: tuple
    subtotal: Decimal
    taxa_entrega: Decimal
    total: Decimal
    valor_maximo: Decimal
    # Bairros oferecidos no formulário; mudar a lista exige nova revisão.
    bairros: tuple

    @property
    def excede_limite(self):
        return self.total > self.valor_maximo

    def conteudo(self):
        """Tudo o que é apresentado ao cliente; valores como texto de Decimal, nunca float.

        Qualquer diferença entre o conteúdo assinado na revisão e o recalculado na
        confirmação exige nova confirmação.
        """
        return {
            'itens': [
                [
                    linha.produto.pk, linha.produto.nome, linha.produto.unidade,
                    linha.quantidade, str(linha.produto.preco), str(linha.valor),
                ]
                for linha in self.linhas
            ],
            'subtotal': str(self.subtotal),
            'taxa_entrega': str(self.taxa_entrega),
            'total': str(self.total),
            'bairros': list(self.bairros),
        }


def montar_revisao(sessao, configuracao):
    """Recalcula a compra com os produtos e preços atuais do banco, sem gravar na sessão."""
    resumo = Carrinho(sessao).resumo()
    if resumo.possui_inconsistencia:
        raise CarrinhoComProblemas(MENSAGEM_CARRINHO_INCONSISTENTE)
    if resumo.vazio:
        raise CarrinhoVazio()
    if resumo.possui_indisponivel:
        raise CarrinhoComProblemas(MENSAGEM_PRODUTO_INDISPONIVEL)
    with localcontext(prec=PRECISAO_CALCULO) as contexto:
        contexto.traps[Inexact] = True
        linhas = tuple(
            LinhaRevisao(linha.produto, linha.quantidade, linha.produto.preco * linha.quantidade)
            for linha in resumo.linhas
        )
        subtotal = sum((linha.valor for linha in linhas), Decimal('0.00'))
        total = subtotal + configuracao.taxa_entrega
    return Revisao(
        linhas, subtotal, configuracao.taxa_entrega, total, configuracao.valor_maximo,
        configuracao.bairros,
    )


# Idempotência determinística

def pedido_base(usuario):
    """Identificador do último pedido do usuário, ou 0: muda a cada compra concluída."""
    ultimo = (
        Pedido.objects.filter(cliente=usuario).order_by('-pk').values_list('pk', flat=True).first()
    )
    return ultimo or 0


def chave_da_tentativa(usuario, base):
    """Chave derivada no servidor; o navegador nunca informa a chave.

    Todas as páginas de checkout abertas pelo mesmo usuário antes de uma compra concluída
    compartilham a mesma base e, portanto, a mesma chave: a restrição UNIQUE do banco
    permite no máximo um pedido por tentativa. O usuário faz parte da derivação, então um
    token forjado não alcança chaves de outros clientes.
    """
    return uuid.uuid5(NAMESPACE_CHAVES_PEDIDO, f'{usuario.pk}:{base}')


def _base_valida(base):
    return isinstance(base, int) and not isinstance(base, bool) and base >= 0


@dataclass(frozen=True)
class RevisaoLida:
    base: int
    chave: uuid.UUID
    conteudo: dict


def assinar_revisao(revisao, base, usuario):
    """Token assinado pelo servidor com a base, o usuário e o conteúdo apresentado."""
    return signing.dumps(
        {
            'v': VERSAO_REVISAO, 'base': base, 'usuario': usuario.pk,
            'conteudo': revisao.conteudo(),
        },
        salt=SAL_REVISAO, compress=True,
    )


def ler_revisao(token, usuario):
    """Lê um token íntegro emitido para este usuário e deriva a chave no servidor."""
    if not isinstance(token, str) or not token:
        raise RevisaoInvalida()
    try:
        dados = signing.loads(token, salt=SAL_REVISAO)
    except (signing.BadSignature, ValueError):
        raise RevisaoInvalida() from None
    if (
        not isinstance(dados, dict) or dados.get('v') != VERSAO_REVISAO
        or dados.get('usuario') != usuario.pk or not isinstance(dados.get('conteudo'), dict)
        or not _base_valida(dados.get('base'))
    ):
        raise RevisaoInvalida()
    return RevisaoLida(dados['base'], chave_da_tentativa(usuario, dados['base']), dados['conteudo'])


# Registro

@dataclass(frozen=True)
class ResultadoRegistro:
    pedido: Pedido
    # False quando a chave já havia gerado o pedido: nada novo foi gravado.
    criado: bool


def _pedido_por_chave(chave):
    return Pedido.objects.filter(chave_idempotencia=chave).first()


def localizar_pedido_da_chave(chave, usuario):
    """Pedido já criado com a chave, se for do usuário; de outro cliente é recusado."""
    pedido = _pedido_por_chave(chave)
    if pedido is not None and pedido.cliente_id != usuario.pk:
        raise ChaveDeOutroCliente()
    return pedido


def pedido_da_tentativa(usuario, base, chave):
    """Pedido já registrado pela tentativa, ou None se ela ainda pode criar um pedido.

    A assinatura do token não basta para aceitar a base (a SECRET_KEY de desenvolvimento
    é pública). Uma base sem pedido só é aceita se for o último pedido atual do usuário;
    assim um token com base arbitrária não gera uma chave nova.
    """
    existente = localizar_pedido_da_chave(chave, usuario)
    if existente is not None:
        return existente
    if pedido_base(usuario) != base:
        # O último pedido pode ser o desta própria tentativa, confirmado por uma requisição
        # concorrente depois da primeira consulta: consulta novamente antes de recusar.
        existente = localizar_pedido_da_chave(chave, usuario)
        if existente is None:
            raise BaseDesatualizada()
    return existente


def _resultado_de_conflito(chave, usuario, erro, *, aguardar):
    """Executado depois do rollback: devolve o pedido gravado com a mesma chave, se houver.

    Uma violação de unicidade já indica um pedido confirmado. Um erro de trava, como
    'database is locked' no SQLite, pode ocorrer enquanto a outra transação ainda não foi
    confirmada; nesse caso a consulta é repetida por um intervalo curto e limitado antes de
    concluir que nenhum pedido foi registrado.
    """
    tentativas = TENTATIVAS_APOS_TRAVA if aguardar else 1
    espera = ESPERA_INICIAL_APOS_TRAVA
    for tentativa in range(tentativas):
        try:
            existente = localizar_pedido_da_chave(chave, usuario)
        except ChaveDeOutroCliente:
            raise
        except DatabaseError:
            existente = None
        if existente is not None:
            return ResultadoRegistro(existente, criado=False)
        if tentativa + 1 < tentativas:
            time.sleep(espera)
            espera *= 2
    raise FalhaAoRegistrar() from erro


def registrar_pedido(*, usuario, sessao, base, conteudo_revisado, entrega):
    """Revalida tudo e cria Pedido e ItemPedido em uma transação, ou nada.

    A chave é sempre derivada aqui, de usuário e base. A unicidade de chave_idempotencia
    no banco é a garantia final contra duplicidade: a consulta prévia apenas evita
    trabalho e devolve o pedido já existente.
    """
    if not getattr(usuario, 'is_authenticated', False) or not usuario.is_active:
        raise IdentificacaoNecessaria()
    if not _base_valida(base) or not isinstance(conteudo_revisado, dict):
        raise RevisaoInvalida()
    chave = chave_da_tentativa(usuario, base)

    existente = pedido_da_tentativa(usuario, base, chave)
    if existente is not None:
        return ResultadoRegistro(existente, criado=False)

    configuracao = obter_configuracao()
    dados_entrega = validar_entrega(entrega, configuracao)
    try:
        with transaction.atomic():
            revisao = montar_revisao(sessao, configuracao)
            if revisao.conteudo() != conteudo_revisado:
                raise RevisaoDesatualizada(revisao)
            if revisao.excede_limite:
                raise LimiteExcedido(revisao)
            pedido = Pedido(
                cliente=usuario, chave_idempotencia=chave, subtotal=revisao.subtotal,
                taxa_entrega=revisao.taxa_entrega, total=revisao.total, **dados_entrega,
            )
            # save() não chama full_clean(); sem ela o SQLite arredondaria ou corromperia
            # valores fora de max_digits/decimal_places.
            pedido.full_clean()
            pedido.save()
            for linha in revisao.linhas:
                # Cópia histórica: alterações futuras no produto não mudam o pedido.
                item = ItemPedido(
                    pedido=pedido, produto=linha.produto, nome_produto=linha.produto.nome,
                    unidade=linha.produto.unidade, quantidade=linha.quantidade,
                    preco_unitario=linha.produto.preco,
                )
                item.full_clean()
                item.save()
    # As exceções abaixo são tratadas fora do bloco atomic: a transação já foi desfeita,
    # então as consultas seguintes não ocorrem dentro de uma transação com erro.
    except ValidationError as erro:
        if 'chave_idempotencia' in getattr(erro, 'error_dict', {}):
            return _resultado_de_conflito(chave, usuario, erro, aguardar=False)
        raise FalhaAoRegistrar() from erro
    except IntegrityError as erro:
        return _resultado_de_conflito(chave, usuario, erro, aguardar=False)
    except DatabaseError as erro:
        return _resultado_de_conflito(chave, usuario, erro, aguardar=True)
    return ResultadoRegistro(pedido, criado=True)
