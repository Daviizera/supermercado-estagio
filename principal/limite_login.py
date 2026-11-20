"""Limitação de tentativas de login (SEG-01), para o login do cliente e o do admin.

Usa somente a API de cache do Django (settings.LIMITE_LOGIN). Há dois contadores:

* usuário + IP: poucas falhas para o mesmo nome de usuário a partir do mesmo endereço;
* IP: limite mais amplo para um endereço que testa muitos nomes diferentes.

Ao atingir um limite, a combinação fica bloqueada por um período fixo e depois volta a ser
aceita; nenhuma conta é bloqueada permanentemente. Como o primeiro contador inclui o IP,
falhas enviadas de um endereço não impedem o acesso à mesma conta a partir de outro.

As chaves de cache contêm apenas resumos HMAC: nem nomes de usuário nem IPs ficam em texto.
"""
import unicodedata

from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.utils.crypto import salted_hmac

MENSAGEM_BLOQUEIO = 'Muitas tentativas de acesso. Aguarde alguns minutos e tente novamente.'
CODIGO_BLOQUEIO = 'tentativas_excedidas'
# Falhas de credencial do AuthenticationForm (usuário inexistente, senha errada, conta
# inativa ou, no admin, conta sem acesso à equipe). Erros de CSRF nem chegam ao formulário.
CODIGOS_DE_FALHA = frozenset({'invalid_login', 'inactive'})
_SAL = 'principal.limite_login'


def normalizar_usuario(nome):
    """Mesma chave para variações de maiúsculas, minúsculas e formas Unicode equivalentes."""
    return unicodedata.normalize('NFKC', nome or '').strip().casefold()


def ip_da_requisicao(request):
    # Somente REMOTE_ADDR: X-Forwarded-For pode ser enviado pelo próprio cliente e só seria
    # confiável atrás de um proxy configurado explicitamente, o que não existe neste projeto.
    meta = getattr(request, 'META', {}) if request is not None else {}
    return meta.get('REMOTE_ADDR') or 'sem-endereco'


def _resumo(*partes):
    return salted_hmac(_SAL, '\x00'.join(partes), algorithm='sha256').hexdigest()


class ControleDeTentativas:
    def __init__(self, request, usuario):
        configuracao = settings.LIMITE_LOGIN
        self.cache = caches[configuracao['CACHE']]
        self.janela = configuracao['JANELA_SEGUNDOS']
        self.duracao_bloqueio = configuracao['BLOQUEIO_SEGUNDOS']
        ip = ip_da_requisicao(request)
        par = _resumo('usuario-ip', normalizar_usuario(usuario), ip)
        endereco = _resumo('ip', ip)
        self.par = (f'login:falhas:par:{par}', f'login:bloqueio:par:{par}',
                    configuracao['FALHAS_POR_USUARIO_E_IP'])
        self.endereco = (f'login:falhas:ip:{endereco}', f'login:bloqueio:ip:{endereco}',
                         configuracao['FALHAS_POR_IP'])

    def bloqueado(self):
        return any(self.cache.get(bloqueio) for _, bloqueio, _ in (self.par, self.endereco))

    def registrar_falha(self):
        for falhas, bloqueio, limite in (self.par, self.endereco):
            # add() cria o contador só se ele não existir, abrindo a janela; incr() mantém a
            # expiração original, então a janela não é prorrogada a cada falha.
            self.cache.add(falhas, 0, timeout=self.janela)
            try:
                total = self.cache.incr(falhas)
            except ValueError:
                # O contador expirou entre add() e incr(): começa uma nova janela.
                self.cache.set(falhas, 1, timeout=self.janela)
                total = 1
            if total >= limite:
                self.cache.set(bloqueio, True, timeout=self.duracao_bloqueio)
                self.cache.delete(falhas)

    def registrar_sucesso(self):
        # Só o par usuário/IP é zerado. Zerar o contador do IP permitiria a quem tem uma
        # conta reiniciar o limite por endereço entrando na própria conta entre tentativas.
        self.cache.delete(self.par[0])


class LimiteDeTentativasMixin:
    """Para formulários derivados de AuthenticationForm (login do site e do admin)."""

    def clean(self):
        controle = ControleDeTentativas(self.request, self.cleaned_data.get('username'))
        if controle.bloqueado():
            # A senha nem é verificada; a resposta é a mesma para contas existentes ou não.
            raise ValidationError(MENSAGEM_BLOQUEIO, code=CODIGO_BLOQUEIO)
        try:
            dados = super().clean()
        except ValidationError as erro:
            if {getattr(e, 'code', None) for e in erro.error_list} & CODIGOS_DE_FALHA:
                controle.registrar_falha()
            raise
        if self.get_user() is not None:
            controle.registrar_sucesso()
        return dados
