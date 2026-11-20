"""Comparação e ordenação de textos sem diferenciar maiúsculas, minúsculas e acentos (F-01, F-02).

No SQLite, icontains usa LIKE, que só ignora a caixa em letras ASCII e não ignora acentos, e
ORDER BY compara códigos de caractere (por isso "Água" ficava depois de "Z"). Para corrigir sem
migration, a função normalizar_texto é registrada em cada conexão SQLite como a função SQL
principal_normalizar; filtro e ordenação são feitos pelo próprio banco, sem carregar o catálogo
em memória. Os nomes armazenados e exibidos não são alterados.

Para catálogos grandes, a evolução natural é uma coluna normalizada com índice (requer migration).
"""
import unicodedata

from django.db.models import CharField, Func

NOME_FUNCAO_SQL = 'principal_normalizar'


def normalizar_texto(texto):
    """'Água SANITÁRIA' -> 'agua sanitaria': decompõe (NFKD), remove marcas e aplica casefold."""
    if texto is None:
        return None
    decomposto = unicodedata.normalize('NFKD', str(texto))
    sem_marcas = ''.join(caractere for caractere in decomposto if not unicodedata.combining(caractere))
    return unicodedata.normalize('NFKC', sem_marcas.casefold())


def registrar_funcao_sql(conexao):
    """Registra a função na conexão SQLite (determinística: mesmo texto, mesmo resultado)."""
    if conexao.vendor != 'sqlite' or conexao.connection is None:
        return
    conexao.connection.create_function(NOME_FUNCAO_SQL, 1, normalizar_texto, deterministic=True)


def ao_criar_conexao(sender, connection, **kwargs):
    registrar_funcao_sql(connection)


class Normalizado(Func):
    """Expressão SQL com o texto normalizado, usada em filtros e ordenações."""

    function = NOME_FUNCAO_SQL
    output_field = CharField()
