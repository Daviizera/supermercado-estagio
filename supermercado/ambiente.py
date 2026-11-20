"""Configuração por ambiente (SEG-02 e SEG-03): desenvolvimento ou produção.

Os valores vêm de variáveis de ambiente. Nenhum segredo fica em arquivo versionado e
nenhuma mensagem de erro inclui o valor de uma chave.

Variáveis:
    DJANGO_ENV                   obrigatória: exatamente "development" ou "production".
    DJANGO_SECRET_KEY            obrigatória em produção; opcional em desenvolvimento.
    DJANGO_ALLOWED_HOSTS         produção: hosts separados por vírgula, sem curingas.
    DJANGO_CSRF_TRUSTED_ORIGINS  produção: origens https:// separadas por vírgula (opcional).
    DJANGO_SECURE_HSTS_SECONDS   produção: duração do HSTS em segundos (padrão conservador).
    DJANGO_SECURE_SSL_REDIRECT   produção: "true" (padrão) ou "false".
    DJANGO_LIMITE_LOGIN_CACHE_BACKEND   produção: backend compartilhado do limitador de login.
    DJANGO_LIMITE_LOGIN_CACHE_LOCATION  produção: endereço desse cache (pode conter credenciais;
                                        nunca aparece em mensagens).
"""
import hashlib
import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

DESENVOLVIMENTO = 'development'
PRODUCAO = 'production'

# SHA-256 das chaves expostas no histórico público do Git. Elas são recusadas em qualquer
# ambiente; guardar somente o resumo permite a comparação sem manter a chave no código.
CHAVES_COMPROMETIDAS_SHA256 = frozenset({
    '01273a573c52792b4d7494b1d52d8f1c35a1085411d622264a5e814c8d973a95',
})
# Mesmos critérios da verificação security.W009 do Django.
TAMANHO_MINIMO_CHAVE = 50
CARACTERES_DISTINTOS_MINIMOS = 5
PREFIXO_INSEGURO = 'django-insecure'

# Desenvolvimento: chave aleatória da própria máquina, criada uma única vez e ignorada pelo Git.
ARQUIVO_CHAVE_LOCAL = '.chave-secreta-local'

# Uma hora: período inicial conservador; aumentar só depois de validar o HTTPS da hospedagem.
HSTS_PADRAO_SEGUNDOS = 3600

VERDADEIROS = frozenset({'1', 'true', 'yes', 'on', 'sim'})
FALSOS = frozenset({'0', 'false', 'no', 'off', 'nao', 'não'})


INSTRUCAO_AMBIENTE = (
    'Defina a variável antes de iniciar o projeto. PowerShell: $env:DJANGO_ENV = "development" '
    '(ou "production" na hospedagem).'
)


def ambiente(environ):
    """Ambiente declarado explicitamente; nunca é deduzido de DEBUG, da chave ou da máquina."""
    if 'DJANGO_ENV' not in environ:
        raise ImproperlyConfigured(f'DJANGO_ENV não está definida. {INSTRUCAO_AMBIENTE}')
    valor = environ['DJANGO_ENV']
    if not valor.strip():
        raise ImproperlyConfigured(f'DJANGO_ENV está vazia. {INSTRUCAO_AMBIENTE}')
    if valor not in (DESENVOLVIMENTO, PRODUCAO):
        raise ImproperlyConfigured(
            f'DJANGO_ENV deve ser exatamente "{DESENVOLVIMENTO}" ou "{PRODUCAO}" '
            f'(recebido: {valor!r}). {INSTRUCAO_AMBIENTE}'
        )
    return valor


def problema_da_chave(chave):
    """Motivo pelo qual a chave não pode ser usada, ou None. Nunca inclui o valor da chave."""
    if not chave:
        return 'está vazia'
    if hashlib.sha256(chave.encode('utf-8')).hexdigest() in CHAVES_COMPROMETIDAS_SHA256:
        return 'é uma chave comprometida (exposta no histórico do Git) e não pode ser reutilizada'
    if chave.startswith(PREFIXO_INSEGURO):
        return f'usa o prefixo "{PREFIXO_INSEGURO}"'
    if len(chave) < TAMANHO_MINIMO_CHAVE:
        return f'tem menos de {TAMANHO_MINIMO_CHAVE} caracteres'
    if len(set(chave)) < CARACTERES_DISTINTOS_MINIMOS:
        return f'tem menos de {CARACTERES_DISTINTOS_MINIMOS} caracteres distintos'
    return None


def gerar_chave():
    """Chave criptograficamente aleatória (86 caracteres URL-safe)."""
    return secrets.token_urlsafe(64)


def chave_secreta(environ, nome_ambiente, base_dir):
    """DJANGO_SECRET_KEY; em desenvolvimento, sem a variável, usa o arquivo local da máquina."""
    if 'DJANGO_SECRET_KEY' in environ:
        chave = environ['DJANGO_SECRET_KEY'].strip()
        problema = problema_da_chave(chave)
        if problema:
            raise ImproperlyConfigured(f'DJANGO_SECRET_KEY inválida: a chave {problema}.')
        return chave
    if nome_ambiente == PRODUCAO:
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY é obrigatória em produção. Gere uma chave com '
            '"python -c \\"import secrets; print(secrets.token_urlsafe(64))\\"" e forneça-a '
            'pela variável de ambiente da hospedagem, nunca em arquivo versionado.'
        )
    return chave_local(Path(base_dir) / ARQUIVO_CHAVE_LOCAL)


def chave_local(caminho):
    """Lê a chave local; se o arquivo não existir, cria-o uma vez sem sobrescrever outro."""
    caminho = Path(caminho)
    if not caminho.exists():
        _criar_sem_sobrescrever(caminho, gerar_chave())
    chave = caminho.read_text(encoding='utf-8').strip()
    problema = problema_da_chave(chave)
    if problema:
        raise ImproperlyConfigured(
            f'O arquivo {caminho.name} contém uma chave inválida: a chave {problema}. '
            'Apague o arquivo para que uma nova chave local seja gerada.'
        )
    return chave


def _criar_sem_sobrescrever(caminho, conteudo):
    # O conteúdo é gravado em um arquivo temporário e publicado com os.link, que falha se o
    # destino já existir: processos simultâneos nunca leem um arquivo pela metade nem
    # sobrescrevem uma chave já criada.
    temporario = caminho.with_name(f'{caminho.name}.tmp-{secrets.token_hex(8)}')
    descritor = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descritor, 'w', encoding='utf-8') as arquivo:
            arquivo.write(conteudo)
        try:
            os.link(temporario, caminho)
        except FileExistsError:
            pass
    finally:
        temporario.unlink(missing_ok=True)


def lista(environ, nome):
    return [item.strip() for item in environ.get(nome, '').split(',') if item.strip()]


def hosts_de_producao(environ):
    hosts = lista(environ, 'DJANGO_ALLOWED_HOSTS')
    if not hosts:
        raise ImproperlyConfigured(
            'DJANGO_ALLOWED_HOSTS é obrigatória em produção: informe os domínios separados por vírgula.'
        )
    for host in hosts:
        if '*' in host or host.startswith('.'):
            raise ImproperlyConfigured(f'DJANGO_ALLOWED_HOSTS não aceita curingas: {host!r}.')
    return hosts


def origens_csrf(environ):
    origens = lista(environ, 'DJANGO_CSRF_TRUSTED_ORIGINS')
    for origem in origens:
        if not origem.startswith('https://') or '*' in origem:
            raise ImproperlyConfigured(
                f'DJANGO_CSRF_TRUSTED_ORIGINS aceita somente origens https:// sem curingas: {origem!r}.'
            )
    return origens


def booleano(environ, nome, padrao):
    if nome not in environ:
        return padrao
    valor = environ[nome].strip().lower()
    if valor in VERDADEIROS:
        return True
    if valor in FALSOS:
        return False
    raise ImproperlyConfigured(f'{nome} deve ser "true" ou "false" (recebido: {valor!r}).')


def inteiro_nao_negativo(environ, nome, padrao):
    if nome not in environ:
        return padrao
    valor = environ[nome].strip()
    if not (valor.isascii() and valor.isdigit()):
        raise ImproperlyConfigured(f'{nome} deve ser um número inteiro de segundos (recebido: {valor!r}).')
    return int(valor)


# Cache do limitador de tentativas de login (SEG-01) em produção.
#
# O limitador conta falhas com add() + incr(). Só são aceitos backends verificados que
# compartilham os contadores entre processos e fazem o incremento de forma atômica no servidor.
# O valor indica os esquemas exigidos no LOCATION (None: formato definido pela biblioteca).
CACHES_DO_LIMITADOR_ACEITOS = {
    # INCRBY do Redis: atômico; expiração controlada pelo servidor. Requer o pacote "redis".
    'django.core.cache.backends.redis.RedisCache': ('redis://', 'rediss://', 'unix://'),
    # incr do Memcached: atômico no servidor. Requerem "pymemcache" ou "pylibmc".
    'django.core.cache.backends.memcached.PyMemcacheCache': None,
    'django.core.cache.backends.memcached.PyLibMCCache': None,
}
# Recusados explicitamente, com o motivo exibido na mensagem de erro.
CACHES_DO_LIMITADOR_RECUSADOS = {
    'django.core.cache.backends.locmem.LocMemCache':
        'guarda os contadores na memória de cada processo, sem compartilhá-los entre workers',
    'django.core.cache.backends.dummy.DummyCache':
        'não armazena nada, então o limite nunca seria atingido',
    'django.core.cache.backends.filebased.FileBasedCache':
        'incrementa com leitura seguida de gravação, perdendo falhas em requisições simultâneas',
    'django.core.cache.backends.db.DatabaseCache':
        'incrementa com leitura seguida de gravação, perdendo falhas em requisições simultâneas',
}
MENSAGEM_CACHE_COMPARTILHADO = (
    'Em produção, o limitador de tentativas de login precisa de um cache compartilhado entre '
    'processos, com incremento atômico (Redis ou Memcached).'
)


def cache_do_limitador_de_producao(environ):
    """Configuração do cache do limitador lida do ambiente; não há valor padrão permissivo."""
    backend = environ.get('DJANGO_LIMITE_LOGIN_CACHE_BACKEND', '').strip()
    endereco = environ.get('DJANGO_LIMITE_LOGIN_CACHE_LOCATION', '').strip()
    if not backend or not endereco:
        raise ImproperlyConfigured(
            f'{MENSAGEM_CACHE_COMPARTILHADO} Defina DJANGO_LIMITE_LOGIN_CACHE_BACKEND e '
            'DJANGO_LIMITE_LOGIN_CACHE_LOCATION.'
        )
    return {'BACKEND': backend, 'LOCATION': endereco}


def validar_cache_do_limitador(caches, alias, nome_ambiente):
    """Em produção, recusa o backend configurado para o alias que o limitador realmente usa.

    As mensagens citam o alias e o backend, nunca o LOCATION, que pode conter credenciais.
    """
    if nome_ambiente != PRODUCAO:
        return
    configuracao = caches.get(alias)
    if configuracao is None:
        raise ImproperlyConfigured(
            f'O alias de cache {alias!r} usado pelo limitador de login não existe em CACHES. '
            f'{MENSAGEM_CACHE_COMPARTILHADO}'
        )
    backend = configuracao.get('BACKEND', '')
    if backend in CACHES_DO_LIMITADOR_RECUSADOS:
        raise ImproperlyConfigured(
            f'O cache {alias!r} usa {backend.rsplit(".", 1)[-1]}, que '
            f'{CACHES_DO_LIMITADOR_RECUSADOS[backend]}. {MENSAGEM_CACHE_COMPARTILHADO}'
        )
    if backend not in CACHES_DO_LIMITADOR_ACEITOS:
        raise ImproperlyConfigured(
            f'O backend {backend!r} do cache {alias!r} não está entre os verificados para o '
            f'limitador de login. {MENSAGEM_CACHE_COMPARTILHADO}'
        )
    enderecos = configuracao.get('LOCATION')
    if isinstance(enderecos, str):
        enderecos = [enderecos]
    if not enderecos or not all(isinstance(e, str) and e.strip() for e in enderecos):
        raise ImproperlyConfigured(f'O cache {alias!r} do limitador de login não tem LOCATION definido.')
    esquemas = CACHES_DO_LIMITADOR_ACEITOS[backend]
    if esquemas and not all(e.strip().startswith(esquemas) for e in enderecos):
        raise ImproperlyConfigured(
            f'O LOCATION do cache {alias!r} deve começar com {", ".join(esquemas)}.'
        )
