"""Gerenciamento de pedidos pela equipe: permissões e transições de estado.

Requisitos: RF-022 a RF-024; RN-017 a RN-019 e RN-021. As views apenas convertem as
exceções deste módulo em respostas; permissões e transições são verificadas aqui.
"""
from dataclasses import dataclass

from django.db import DatabaseError

from .models import EstadoPedido, Pedido

PERMISSAO_CONSULTA = 'principal.view_pedido'
PERMISSAO_ALTERACAO = 'principal.change_pedido'

# RN-018: única fonte das transições. Entregue e Cancelado são terminais.
TRANSICOES = {
    EstadoPedido.RECEBIDO: (EstadoPedido.CONFIRMADO, EstadoPedido.CANCELADO),
    EstadoPedido.CONFIRMADO: (EstadoPedido.EM_PREPARO, EstadoPedido.CANCELADO),
    EstadoPedido.EM_PREPARO: (EstadoPedido.SAIU_PARA_ENTREGA, EstadoPedido.CANCELADO),
    EstadoPedido.SAIU_PARA_ENTREGA: (EstadoPedido.ENTREGUE,),
    EstadoPedido.ENTREGUE: (),
    EstadoPedido.CANCELADO: (),
}

MENSAGEM_SEM_PERMISSAO = 'Você não tem permissão para acessar esta área.'
MENSAGEM_TRANSICAO_INVALIDA = 'Esta alteração não é permitida para o estado atual.'
MENSAGEM_ESTADO_ALTERADO = 'O estado do pedido mudou. Atualize a consulta.'
MENSAGEM_FALHA = 'Não foi possível salvar a alteração.'


class ErroPedido(Exception):
    """Operação recusada; o pedido não é alterado."""

    mensagem = MENSAGEM_FALHA

    def __init__(self):
        super().__init__(self.mensagem)


class SemPermissao(ErroPedido):
    mensagem = MENSAGEM_SEM_PERMISSAO


class TransicaoInvalida(ErroPedido):
    mensagem = MENSAGEM_TRANSICAO_INVALIDA


class EstadoAlterado(ErroPedido):
    """O pedido não está mais no estado exibido na página usada para a ação."""

    mensagem = MENSAGEM_ESTADO_ALTERADO


class FalhaAoAlterar(ErroPedido):
    mensagem = MENSAGEM_FALHA


def _integrante_com_permissao(usuario, permissao):
    """Área interna: autenticado, ativo, is_staff e permissão nativa do Django."""
    return bool(
        getattr(usuario, 'is_authenticated', False) and usuario.is_active
        and usuario.is_staff and usuario.has_perm(permissao)
    )


def pode_consultar(usuario):
    return _integrante_com_permissao(usuario, PERMISSAO_CONSULTA)


def pode_alterar(usuario):
    return _integrante_com_permissao(usuario, PERMISSAO_ALTERACAO)


def transicoes_permitidas(estado):
    """Próximos estados aceitos a partir de um estado; vazio para terminais ou desconhecidos."""
    return TRANSICOES.get(estado, ())


@dataclass(frozen=True)
class ResultadoTransicao:
    pedido: Pedido
    anterior: str
    novo: str


def alterar_estado(*, usuario, pedido_id, estado_esperado, novo_estado):
    """Aplica uma transição da tabela, alterando somente o campo estado.

    O estado esperado vem da página usada pela equipe e serve apenas como pré-condição:
    a autorização é a permissão do usuário mais a tabela TRANSICOES. A atualização é uma
    única instrução SQL condicional; se o pedido já não estiver no estado esperado, nenhum
    registro é alterado, o que impede páginas antigas e ações repetidas de avançarem o
    pedido duas vezes. Não há outra gravação, então nenhuma transação adicional é necessária.
    """
    if not pode_alterar(usuario):
        raise SemPermissao()
    try:
        if not Pedido.objects.filter(pk=pedido_id).exists():
            raise Pedido.DoesNotExist()
    except DatabaseError:
        raise FalhaAoAlterar() from None
    if novo_estado not in transicoes_permitidas(estado_esperado):
        raise TransicaoInvalida()
    try:
        alterados = Pedido.objects.filter(pk=pedido_id, estado=estado_esperado).update(
            estado=novo_estado,
        )
    except DatabaseError:
        raise FalhaAoAlterar() from None
    if alterados == 0:
        raise EstadoAlterado()
    return ResultadoTransicao(Pedido.objects.get(pk=pedido_id), estado_esperado, novo_estado)
