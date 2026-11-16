"""Carrinho da sessão: guarda somente identificadores e quantidades.

Preços, nomes e disponibilidade são lidos do banco a cada visualização, para que o
navegador nunca determine valores e alterações do Admin apareçam na próxima consulta.
O serviço valida as próprias entradas: as regras não dependem de a chamada ter passado
por um formulário.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, Inexact, localcontext

from django.core.validators import MaxValueValidator

from .models import ItemPedido, Produto

CHAVE_SESSAO = 'carrinho'

# Precisão ampla com Inexact ativo: um arredondamento seria erro, não valor silencioso.
PRECISAO_CALCULO = 100

# Identificador gravado pelo serviço: inteiro positivo em dígitos ASCII, sem zeros à esquerda.
_PADRAO_CHAVE = re.compile(r'[1-9][0-9]*')


class ErroCarrinho(Exception):
    """Operação recusada pelo carrinho; a sessão não é alterada."""


class QuantidadeInvalida(ErroCarrinho):
    """Quantidade que não é um inteiro positivo (bool, float, texto, zero ou negativo)."""


class QuantidadeAcimaDoLimite(QuantidadeInvalida):
    """A quantidade ultrapassaria o limite técnico do item de pedido."""

    def __init__(self, limite):
        super().__init__(limite)
        self.limite = limite


class ProdutoIndisponivel(ErroCarrinho):
    """Produto não persistido, inexistente no banco ou inativo."""


class ItemAusente(ErroCarrinho):
    """O produto informado não está no carrinho."""


class ItemInconsistente(ErroCarrinho):
    """A quantidade já armazenada para o produto é inválida e não pode ser somada."""


def _limite_maximo(campo):
    """Menor MaxValueValidator que o Django associa ao campo no banco configurado."""
    limites = [
        validador.limit_value for validador in campo.validators
        if isinstance(validador, MaxValueValidator)
    ]
    return min(limites) if limites else None


def limite_tecnico_quantidade():
    """Retorna o máximo aceito por ItemPedido.quantidade no banco configurado.

    Não é um limite comercial: vem dos validadores que o Django associa ao campo.
    """
    return _limite_maximo(ItemPedido._meta.get_field('quantidade'))


def validar_quantidade(quantidade):
    """Exige int positivo dentro do limite técnico; bool é recusado apesar de ser int."""
    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or quantidade < 1:
        raise QuantidadeInvalida(quantidade)
    limite = limite_tecnico_quantidade()
    if limite is not None and quantidade > limite:
        raise QuantidadeAcimaDoLimite(limite)
    return quantidade


def _quantidade_valida(quantidade):
    try:
        validar_quantidade(quantidade)
    except QuantidadeInvalida:
        return False
    return True


def _chave_produto(produto_id):
    """Normaliza um identificador para a chave da sessão; None quando é inválido.

    Aceita int positivo (exceto bool) ou texto no formato gravado pelo serviço, dentro
    da faixa da chave primária de Produto. Nunca converte textos fora do padrão.
    """
    if isinstance(produto_id, bool):
        return None
    if isinstance(produto_id, int):
        texto = str(produto_id) if produto_id > 0 else None
    elif isinstance(produto_id, str) and _PADRAO_CHAVE.fullmatch(produto_id):
        texto = produto_id
    else:
        return None
    if texto is None:
        return None
    maximo = _limite_maximo(Produto._meta.pk)
    # O comprimento é conferido antes de int() para evitar converter textos enormes.
    if maximo is not None and (len(texto) > len(str(maximo)) or int(texto) > maximo):
        return None
    return texto


def _chave_reconhecida(chave):
    """Somente a forma gravada pelo serviço identifica um produto; '07' ou 7 (int) não."""
    chave_valida = _chave_produto(chave)
    return chave_valida is not None and chave_valida == chave


def _confirmar_produto_ativo(produto):
    """Confirma no banco que o produto persistido existe e continua ativo."""
    if not isinstance(produto, Produto) or produto.pk is None:
        raise ProdutoIndisponivel(produto)
    chave = _chave_produto(produto.pk)
    if chave is None or not Produto.objects.filter(pk=produto.pk, ativo=True).exists():
        raise ProdutoIndisponivel(produto)
    return chave


@dataclass(frozen=True)
class LinhaCarrinho:
    produto_id: int
    # None quando a quantidade armazenada é inválida; nunca é exibida nem calculada.
    quantidade: int | None
    # None quando o produto foi excluído do banco depois de entrar no carrinho.
    produto: Produto | None
    valor: Decimal | None

    @property
    def encontrado(self):
        return self.produto is not None

    @property
    def disponivel(self):
        return self.produto is not None and self.produto.ativo

    @property
    def consistente(self):
        return self.quantidade is not None


@dataclass(frozen=True)
class ResumoCarrinho:
    linhas: list
    subtotal: Decimal
    # Entradas cujo identificador não pôde ser reconhecido; não viram linhas.
    entradas_ignoradas: int = 0

    @property
    def vazio(self):
        return not self.linhas

    @property
    def possui_indisponivel(self):
        return any(not linha.disponivel for linha in self.linhas)

    @property
    def possui_inconsistencia(self):
        return self.entradas_ignoradas > 0 or any(not linha.consistente for linha in self.linhas)


class Carrinho:
    """Opera sobre request.session; somente os métodos de alteração gravam na sessão.

    Toda validação acontece antes da gravação: uma operação recusada lança ErroCarrinho
    e deixa a sessão intacta. Entradas malformadas de outros produtos são preservadas.
    """

    def __init__(self, sessao):
        self.sessao = sessao

    def _itens(self):
        itens = self.sessao.get(CHAVE_SESSAO)
        return itens if isinstance(itens, dict) else {}

    def _gravar(self, itens):
        # Uma nova atribuição marca a sessão como modificada.
        self.sessao[CHAVE_SESSAO] = itens

    def contem(self, produto_id):
        chave = _chave_produto(produto_id)
        return chave is not None and chave in self._itens()

    def quantidade(self, produto_id):
        """Quantidade válida armazenada, ou None se ausente ou inconsistente."""
        chave = _chave_produto(produto_id)
        quantidade = self._itens().get(chave) if chave is not None else None
        return quantidade if _quantidade_valida(quantidade) else None

    def adicionar(self, produto, quantidade):
        """Soma a quantidade à linha existente ou cria a linha do produto ativo."""
        validar_quantidade(quantidade)
        chave = _confirmar_produto_ativo(produto)
        itens = dict(self._itens())
        atual = itens.get(chave, 0)
        if chave in itens and not _quantidade_valida(atual):
            raise ItemInconsistente(produto)
        nova_quantidade = validar_quantidade(atual + quantidade)
        itens[chave] = nova_quantidade
        self._gravar(itens)
        return nova_quantidade

    def definir_quantidade(self, produto, quantidade):
        """Substitui a quantidade de um item já presente cujo produto continua ativo.

        Uma quantidade armazenada inconsistente pode ser substituída por uma válida.
        """
        validar_quantidade(quantidade)
        chave = _confirmar_produto_ativo(produto)
        itens = dict(self._itens())
        if chave not in itens:
            raise ItemAusente(produto)
        itens[chave] = quantidade
        self._gravar(itens)
        return quantidade

    def remover(self, produto_id):
        """Remove somente a linha indicada, mesmo inconsistente; não consulta o banco."""
        chave = _chave_produto(produto_id)
        itens = dict(self._itens())
        if chave is None or chave not in itens:
            return False
        del itens[chave]
        self._gravar(itens)
        return True

    def remover_entradas_nao_identificadas(self):
        """Remove somente os registros que não correspondem a um produto identificável.

        Itens identificáveis, inclusive com quantidade inconsistente, são preservados e
        continuam sujeitos à remoção individual. Retorna quantos registros foram removidos.
        """
        if CHAVE_SESSAO not in self.sessao:
            return 0
        bruto = self.sessao[CHAVE_SESSAO]
        if not isinstance(bruto, dict):
            # Estrutura inteira inválida: não há item identificável a preservar.
            self._gravar({})
            return 1
        itens = {chave: valor for chave, valor in bruto.items() if _chave_reconhecida(chave)}
        removidas = len(bruto) - len(itens)
        if removidas:
            self._gravar(itens)
        return removidas

    def esvaziar(self):
        """Remove somente a chave do carrinho; autenticação e demais dados da sessão ficam."""
        self.sessao.pop(CHAVE_SESSAO, None)

    def resumo(self):
        """Monta as linhas com os dados atuais do banco em uma única consulta, sem gravar.

        Entradas malformadas não causam erro e não entram no subtotal: identificador
        inválido é apenas contado; quantidade inválida gera linha sem quantidade e sem valor.
        """
        entradas = []
        # Uma estrutura gravada que não é dicionário conta como um registro não identificável.
        ignoradas = int(CHAVE_SESSAO in self.sessao and not isinstance(self.sessao[CHAVE_SESSAO], dict))
        for chave, quantidade in self._itens().items():
            if not _chave_reconhecida(chave):
                ignoradas += 1
                continue
            quantidade_valida = quantidade if _quantidade_valida(quantidade) else None
            entradas.append((int(chave), quantidade_valida))

        produtos = Produto.objects.in_bulk([produto_id for produto_id, _ in entradas])
        linhas = []
        with localcontext(prec=PRECISAO_CALCULO) as contexto:
            contexto.traps[Inexact] = True
            subtotal = Decimal('0.00')
            for produto_id, quantidade in entradas:
                produto = produtos.get(produto_id)
                valor = None
                if produto is not None and quantidade is not None:
                    valor = produto.preco * quantidade
                    subtotal += valor
                linhas.append(LinhaCarrinho(produto_id, quantidade, produto, valor))
        return ResumoCarrinho(linhas, subtotal, ignoradas)
