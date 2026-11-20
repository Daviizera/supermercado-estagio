from django.apps import AppConfig


class PrincipalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'principal'

    def ready(self):
        from django.db import connections
        from django.db.backends.signals import connection_created

        from .busca import ao_criar_conexao, registrar_funcao_sql

        # Função SQL de normalização para a busca e a ordenação do catálogo (F-01, F-02):
        # registrada nas conexões futuras e nas que já estiverem abertas.
        connection_created.connect(ao_criar_conexao, dispatch_uid='principal.busca.normalizar')
        for conexao in connections.all(initialized_only=True):
            registrar_funcao_sql(conexao)
