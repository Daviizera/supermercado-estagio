"""SEG-02 e SEG-03 (chave secreta e ambientes) e política de senhas de 12 caracteres.

Nenhum teste imprime chaves. As chaves usadas aqui são geradas na hora; o domínio de
produção de teste usa o sufixo reservado ".invalid", que nunca corresponde a um site real.
"""
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from supermercado import ambiente

BASE = Path(settings.BASE_DIR)
HOST_TESTE = 'implantacao-de-teste.invalid'
REDIS = 'django.core.cache.backends.redis.RedisCache'
LOCMEM = 'django.core.cache.backends.locmem.LocMemCache'
DUMMY = 'django.core.cache.backends.dummy.DummyCache'
ENDERECO_CACHE_TESTE = 'redis://usuario:senha-ficticia@cache-de-teste.invalid:6379/0'


def chave_teste():
    return secrets.token_urlsafe(64)


def executar(comando, **variaveis):
    """Roda manage.py em outro processo com o ambiente indicado (sem herdar DJANGO_*)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
    env.update(variaveis)
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, 'manage.py', *comando], cwd=BASE, env=env, capture_output=True,
        text=True, encoding='utf-8', timeout=120,
    )


class AmbienteTests(SimpleTestCase):
    def test_ambiente_precisa_ser_declarado_explicitamente(self):
        self.assertEqual(ambiente.ambiente({'DJANGO_ENV': 'development'}), 'development')
        self.assertEqual(ambiente.ambiente({'DJANGO_ENV': 'production'}), 'production')
        casos = {
            'ausente': ({}, 'não está definida'),
            'vazio': ({'DJANGO_ENV': ''}, 'está vazia'),
            'so_espacos': ({'DJANGO_ENV': '   '}, 'está vazia'),
            'desconhecido': ({'DJANGO_ENV': 'staging'}, 'deve ser exatamente'),
            'abreviado': ({'DJANGO_ENV': 'prod'}, 'deve ser exatamente'),
            'maiusculas': ({'DJANGO_ENV': 'Production'}, 'deve ser exatamente'),
            'com_espacos': ({'DJANGO_ENV': ' development '}, 'deve ser exatamente'),
        }
        for nome, (environ, trecho) in casos.items():
            with self.subTest(caso=nome):
                with self.assertRaisesMessage(ImproperlyConfigured, trecho):
                    ambiente.ambiente(environ)

    def test_ambiente_nao_e_deduzido_de_outras_variaveis(self):
        # Chave definida, DEBUG ou hosts não substituem a declaração de DJANGO_ENV.
        with self.assertRaisesMessage(ImproperlyConfigured, 'não está definida'):
            ambiente.ambiente({'DJANGO_SECRET_KEY': chave_teste(), 'DEBUG': 'True',
                               'DJANGO_ALLOWED_HOSTS': HOST_TESTE})

    def test_producao_exige_chave(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'DJANGO_SECRET_KEY é obrigatória em produção'):
            ambiente.chave_secreta({}, 'production', BASE)

    def test_chaves_invalidas_sao_recusadas_sem_aparecer_na_mensagem(self):
        comprometida = chave_teste()
        resumo = hashlib.sha256(comprometida.encode()).hexdigest()
        invalidas = {
            'curta': 'Ab1!' * 5,
            'prefixo': 'django-insecure-' + chave_teste(),
            'repetitiva': 'abcd' * 20,
            'vazia': '',
            'comprometida': comprometida,
        }
        with mock.patch.object(ambiente, 'CHAVES_COMPROMETIDAS_SHA256', frozenset({resumo})):
            for nome, chave in invalidas.items():
                for nome_ambiente in ('production', 'development'):
                    with self.subTest(chave=nome, ambiente=nome_ambiente):
                        with self.assertRaises(ImproperlyConfigured) as contexto:
                            ambiente.chave_secreta({'DJANGO_SECRET_KEY': chave}, nome_ambiente, BASE)
                        if chave:
                            self.assertNotIn(chave, str(contexto.exception))

    def test_chave_valida_da_variavel_e_aceita(self):
        chave = chave_teste()
        self.assertEqual(ambiente.chave_secreta({'DJANGO_SECRET_KEY': chave}, 'production', BASE), chave)

    def test_chave_exposta_no_historico_esta_na_lista_de_recusa(self):
        self.assertIn(
            '01273a573c52792b4d7494b1d52d8f1c35a1085411d622264a5e814c8d973a95',
            ambiente.CHAVES_COMPROMETIDAS_SHA256,
        )

    def test_desenvolvimento_cria_chave_local_uma_vez_sem_sobrescrever(self):
        with tempfile.TemporaryDirectory() as pasta:
            primeira = ambiente.chave_secreta({}, 'development', pasta)
            arquivo = Path(pasta) / ambiente.ARQUIVO_CHAVE_LOCAL
            self.assertTrue(arquivo.exists())
            self.assertIsNone(ambiente.problema_da_chave(primeira))
            self.assertEqual(ambiente.chave_secreta({}, 'development', pasta), primeira)
            self.assertEqual(list(Path(pasta).iterdir()), [arquivo])
            # A variável de ambiente tem prioridade sobre o arquivo local.
            outra = chave_teste()
            self.assertEqual(ambiente.chave_secreta({'DJANGO_SECRET_KEY': outra}, 'development', pasta), outra)
            self.assertEqual(arquivo.read_text(encoding='utf-8'), primeira)

    def test_arquivo_local_existente_nao_e_sobrescrito_e_invalido_gera_erro(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / ambiente.ARQUIVO_CHAVE_LOCAL
            arquivo.write_text('curta', encoding='utf-8')
            with self.assertRaisesMessage(ImproperlyConfigured, 'Apague o arquivo'):
                ambiente.chave_secreta({}, 'development', pasta)
            self.assertEqual(arquivo.read_text(encoding='utf-8'), 'curta')

    def test_hosts_e_origens_de_producao(self):
        with self.assertRaises(ImproperlyConfigured):
            ambiente.hosts_de_producao({})
        for curinga in ('*', '.exemplo.invalid', 'loja.*.invalid'):
            with self.subTest(host=curinga), self.assertRaises(ImproperlyConfigured):
                ambiente.hosts_de_producao({'DJANGO_ALLOWED_HOSTS': f'{HOST_TESTE},{curinga}'})
        self.assertEqual(
            ambiente.hosts_de_producao({'DJANGO_ALLOWED_HOSTS': f' {HOST_TESTE} , www.{HOST_TESTE} '}),
            [HOST_TESTE, f'www.{HOST_TESTE}'],
        )
        self.assertEqual(ambiente.origens_csrf({}), [])
        for origem in (f'http://{HOST_TESTE}', 'https://*.invalid', HOST_TESTE):
            with self.subTest(origem=origem), self.assertRaises(ImproperlyConfigured):
                ambiente.origens_csrf({'DJANGO_CSRF_TRUSTED_ORIGINS': origem})

    def test_hsts_e_redirecionamento_configuraveis(self):
        self.assertEqual(ambiente.inteiro_nao_negativo({}, 'X', 3600), 3600)
        self.assertEqual(ambiente.inteiro_nao_negativo({'X': '86400'}, 'X', 3600), 86400)
        for invalido in ('-1', '1.5', 'um', '٣'):
            with self.subTest(valor=invalido), self.assertRaises(ImproperlyConfigured):
                ambiente.inteiro_nao_negativo({'X': invalido}, 'X', 3600)
        self.assertTrue(ambiente.booleano({}, 'X', True))
        self.assertFalse(ambiente.booleano({'X': 'false'}, 'X', True))
        with self.assertRaises(ImproperlyConfigured):
            ambiente.booleano({'X': 'talvez'}, 'X', True)


class ConfiguracaoAtualTests(SimpleTestCase):
    def test_settings_nao_contem_chave_fixa(self):
        fonte = (BASE / 'supermercado' / 'settings.py').read_text(encoding='utf-8')
        self.assertNotRegex(fonte, r'SECRET_KEY\s*=\s*[\'"]')
        self.assertNotIn('django-insecure', fonte)

    def test_chave_em_uso_e_valida_e_nao_e_a_comprometida(self):
        self.assertIsNone(ambiente.problema_da_chave(settings.SECRET_KEY))
        self.assertNotIn(
            hashlib.sha256(settings.SECRET_KEY.encode()).hexdigest(), ambiente.CHAVES_COMPROMETIDAS_SHA256,
        )

    def test_arquivo_da_chave_local_e_ignorado_pelo_git(self):
        regras = (BASE / '.gitignore').read_text(encoding='utf-8').splitlines()
        self.assertIn('.chave-secreta-local*', regras)
        self.assertIn('.env', regras)

    def test_desenvolvimento_mantem_http_local(self):
        self.assertEqual(settings.AMBIENTE, 'development')
        # O executor de testes acrescenta 'testserver'; os hosts do projeto são só os locais.
        self.assertEqual(settings.ALLOWED_HOSTS[:3], ['127.0.0.1', 'localhost', '[::1]'])
        self.assertEqual(set(settings.ALLOWED_HOSTS) - {'testserver'}, {'127.0.0.1', 'localhost', '[::1]'})
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)


class ProducaoEmProcessoSeparadoTests(SimpleTestCase):
    """Carrega as configurações reais com DJANGO_ENV=production em outro processo."""

    def ambiente_producao(self, **extra):
        return {
            'DJANGO_ENV': 'production', 'DJANGO_SECRET_KEY': chave_teste(),
            'DJANGO_ALLOWED_HOSTS': HOST_TESTE, 'DJANGO_CSRF_TRUSTED_ORIGINS': f'https://{HOST_TESTE}',
            'DJANGO_LIMITE_LOGIN_CACHE_BACKEND': REDIS, 'DJANGO_LIMITE_LOGIN_CACHE_LOCATION': ENDERECO_CACHE_TESTE,
            **extra,
        }

    def test_valores_de_producao(self):
        codigo = (
            'import json, django; django.setup(); from django.conf import settings as s; print(json.dumps({'
            'n: getattr(s, n) for n in ("DEBUG", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "SESSION_COOKIE_SECURE",'
            ' "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS", "SECURE_HSTS_INCLUDE_SUBDOMAINS",'
            ' "SECURE_HSTS_PRELOAD", "SECURE_CONTENT_TYPE_NOSNIFF", "X_FRAME_OPTIONS")} | '
            '{"STATIC_ROOT": str(s.STATIC_ROOT), "PROXY": hasattr(s, "SECURE_PROXY_SSL_HEADER") and s.SECURE_PROXY_SSL_HEADER,'
            ' "CACHE_LIMITADOR": s.CACHES[s.LIMITE_LOGIN["CACHE"]]["BACKEND"], "CACHE_PADRAO": s.CACHES["default"]["BACKEND"],'
            ' "ALIAS_LIMITADOR": s.LIMITE_LOGIN["CACHE"]}))'
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
        env.update(self.ambiente_producao(), DJANGO_SETTINGS_MODULE='supermercado.settings')
        processo = subprocess.run([sys.executable, '-c', codigo], cwd=BASE, env=env, capture_output=True,
                                  text=True, timeout=120)
        self.assertEqual(processo.returncode, 0, processo.stderr[-500:])
        valores = json.loads(processo.stdout)
        self.assertEqual(valores, {
            'DEBUG': False, 'ALLOWED_HOSTS': [HOST_TESTE], 'CSRF_TRUSTED_ORIGINS': [f'https://{HOST_TESTE}'],
            'SESSION_COOKIE_SECURE': True, 'CSRF_COOKIE_SECURE': True, 'SECURE_SSL_REDIRECT': True,
            'SECURE_HSTS_SECONDS': 3600, 'SECURE_HSTS_INCLUDE_SUBDOMAINS': False, 'SECURE_HSTS_PRELOAD': False,
            'SECURE_CONTENT_TYPE_NOSNIFF': True, 'X_FRAME_OPTIONS': 'DENY',
            'STATIC_ROOT': str(BASE / 'staticfiles'), 'PROXY': None,
            'ALIAS_LIMITADOR': 'limite_login', 'CACHE_LIMITADOR': REDIS, 'CACHE_PADRAO': LOCMEM,
        })

    def test_check_deploy_so_aponta_as_decisoes_conscientes_de_hsts(self):
        processo = executar(['check', '--deploy'], **self.ambiente_producao())
        saida = processo.stdout + processo.stderr
        avisos = set(re.findall(r'security\.W\d{3}', saida))
        # W005 (subdomínios) e W021 (preload) ficam desligados até validar a infraestrutura.
        self.assertEqual(avisos, {'security.W005', 'security.W021'}, saida[-1500:])

    def test_producao_sem_chave_ou_sem_hosts_nao_inicia(self):
        for faltando in ('DJANGO_SECRET_KEY', 'DJANGO_ALLOWED_HOSTS', 'DJANGO_LIMITE_LOGIN_CACHE_BACKEND',
                         'DJANGO_LIMITE_LOGIN_CACHE_LOCATION'):
            with self.subTest(faltando=faltando):
                variaveis = self.ambiente_producao()
                del variaveis[faltando]
                processo = executar(['check'], **variaveis)
                self.assertNotEqual(processo.returncode, 0)
                self.assertIn('ImproperlyConfigured', processo.stderr)
                self.assertIn(faltando, processo.stderr)
                self.assertNotIn('senha-ficticia', processo.stderr)

    def test_inicializacao_depende_de_ambiente_explicito(self):
        casos = {
            'ausente': ({}, 'DJANGO_ENV não está definida'),
            'vazio': ({'DJANGO_ENV': ''}, 'DJANGO_ENV está vazia'),
            'so_espacos': ({'DJANGO_ENV': '  '}, 'DJANGO_ENV está vazia'),
            'desconhecido': ({'DJANGO_ENV': 'staging'}, 'DJANGO_ENV deve ser exatamente'),
        }
        for nome, (variaveis, trecho) in casos.items():
            with self.subTest(caso=nome):
                processo = executar(['check'], **variaveis)
                self.assertNotEqual(processo.returncode, 0)
                self.assertIn('ImproperlyConfigured', processo.stderr)
                self.assertIn(trecho, processo.stderr)
        processo = executar(['check'], DJANGO_ENV='development')
        self.assertEqual(processo.returncode, 0, processo.stderr[-500:])
        self.assertIn('System check identified no issues', processo.stdout)

    def test_producao_com_cache_local_nao_inicia(self):
        for backend in (LOCMEM, DUMMY):
            with self.subTest(backend=backend):
                processo = executar(['check'], **self.ambiente_producao(
                    DJANGO_LIMITE_LOGIN_CACHE_BACKEND=backend, DJANGO_LIMITE_LOGIN_CACHE_LOCATION='local',
                ))
                self.assertNotEqual(processo.returncode, 0)
                self.assertIn('ImproperlyConfigured', processo.stderr)
                self.assertIn('cache compartilhado entre processos', processo.stderr)
                self.assertIn(backend.rsplit('.', 1)[-1], processo.stderr)


class CacheDoLimitadorTests(SimpleTestCase):
    """Validação do backend efetivamente configurado para o alias usado pelo limitador."""

    def caches(self, **por_alias):
        base = {'default': {'BACKEND': LOCMEM, 'LOCATION': 'padrao'}}
        base.update({alias: {'BACKEND': backend, 'LOCATION': local} for alias, (backend, local) in por_alias.items()})
        return base

    def test_producao_recusa_cache_local_e_ficticio(self):
        for backend in (LOCMEM, DUMMY):
            with self.subTest(backend=backend), self.assertRaisesMessage(
                ImproperlyConfigured, 'cache compartilhado entre processos',
            ):
                ambiente.validar_cache_do_limitador(self.caches(limite_login=(backend, 'x')), 'limite_login', 'production')

    def test_producao_recusa_backends_com_incremento_nao_atomico_ou_desconhecidos(self):
        for backend in ('django.core.cache.backends.filebased.FileBasedCache',
                        'django.core.cache.backends.db.DatabaseCache', 'meu_projeto.cache.CacheQualquer'):
            with self.subTest(backend=backend), self.assertRaises(ImproperlyConfigured):
                ambiente.validar_cache_do_limitador(self.caches(limite_login=(backend, 'x')), 'limite_login', 'production')

    def test_desenvolvimento_continua_com_locmem(self):
        ambiente.validar_cache_do_limitador(self.caches(limite_login=(LOCMEM, 'x')), 'limite_login', 'development')
        self.assertEqual(settings.CACHES[settings.LIMITE_LOGIN['CACHE']]['BACKEND'], LOCMEM)

    def test_producao_aceita_backend_compartilhado_verificado(self):
        for backend, local in (
            (REDIS, ENDERECO_CACHE_TESTE), (REDIS, ['redis://a.invalid:6379', 'rediss://b.invalid:6380']),
            ('django.core.cache.backends.memcached.PyMemcacheCache', 'cache-de-teste.invalid:11211'),
            ('django.core.cache.backends.memcached.PyLibMCCache', 'cache-de-teste.invalid:11211'),
        ):
            with self.subTest(backend=backend):
                ambiente.validar_cache_do_limitador(self.caches(limite_login=(backend, local)), 'limite_login', 'production')

    def test_examina_o_alias_usado_pelo_limitador(self):
        # O padrão compartilhado não salva um alias de limitador local.
        com_padrao_redis = {'default': {'BACKEND': REDIS, 'LOCATION': ENDERECO_CACHE_TESTE},
                            'limite_login': {'BACKEND': LOCMEM, 'LOCATION': 'x'}}
        with self.assertRaisesMessage(ImproperlyConfigured, "'limite_login'"):
            ambiente.validar_cache_do_limitador(com_padrao_redis, 'limite_login', 'production')
        # Se o limitador usasse o alias "default", seria ele o examinado.
        ambiente.validar_cache_do_limitador(com_padrao_redis, 'default', 'production')
        with self.assertRaisesMessage(ImproperlyConfigured, 'não existe em CACHES'):
            ambiente.validar_cache_do_limitador(com_padrao_redis, 'outro_alias', 'production')
        self.assertEqual(settings.LIMITE_LOGIN['CACHE'], 'limite_login')

    def test_location_obrigatorio_e_nunca_exposto(self):
        for local in ('', [], 'http://usuario:senha-ficticia@cache.invalid:6379'):
            with self.subTest(local=local), self.assertRaises(ImproperlyConfigured) as contexto:
                ambiente.validar_cache_do_limitador(self.caches(limite_login=(REDIS, local)), 'limite_login', 'production')
            self.assertNotIn('senha-ficticia', str(contexto.exception))

    def test_configuracao_de_producao_lida_do_ambiente_sem_padrao_permissivo(self):
        for faltando in ('DJANGO_LIMITE_LOGIN_CACHE_BACKEND', 'DJANGO_LIMITE_LOGIN_CACHE_LOCATION'):
            variaveis = {'DJANGO_LIMITE_LOGIN_CACHE_BACKEND': REDIS,
                         'DJANGO_LIMITE_LOGIN_CACHE_LOCATION': ENDERECO_CACHE_TESTE}
            variaveis[faltando] = '  '
            with self.subTest(faltando=faltando), self.assertRaisesMessage(ImproperlyConfigured, faltando):
                ambiente.cache_do_limitador_de_producao(variaveis)
        self.assertEqual(
            ambiente.cache_do_limitador_de_producao({'DJANGO_LIMITE_LOGIN_CACHE_BACKEND': REDIS,
                                                     'DJANGO_LIMITE_LOGIN_CACHE_LOCATION': ENDERECO_CACHE_TESTE}),
            {'BACKEND': REDIS, 'LOCATION': ENDERECO_CACHE_TESTE},
        )


class PoliticaDeSenhasTests(TestCase):
    """Mínimo de 12 caracteres mais os três validadores anteriores, aplicados no servidor."""

    usuario = 'cliente_politica'

    def cadastrar(self, senha):
        resposta = self.client.post(reverse('principal:cadastro'), {
            'username': self.usuario, 'password1': senha, 'password2': senha,
        })
        criado = get_user_model().objects.filter(username=self.usuario).exists()
        codigos = []
        if resposta.status_code == 200:
            codigos = [e.code for e in resposta.context['form'].errors.as_data().get('password2', [])]
        return criado, codigos

    def test_validadores_configurados(self):
        nomes = {v['NAME'].rsplit('.', 1)[1]: v.get('OPTIONS', {}) for v in settings.AUTH_PASSWORD_VALIDATORS}
        self.assertEqual(nomes, {
            'UserAttributeSimilarityValidator': {}, 'MinimumLengthValidator': {'min_length': 12},
            'CommonPasswordValidator': {}, 'NumericPasswordValidator': {},
        })

    def test_onze_caracteres_recusada_e_doze_aceita(self):
        self.assertEqual(self.cadastrar('Vbx!tqLm9Rz'), (False, ['password_too_short']))
        self.assertEqual(self.cadastrar('Vbx!tqLm9Rzw'), (True, []))

    def test_senhas_comum_numerica_e_semelhante_recusadas(self):
        for senha, codigo in (
            ('123456qwerty', 'password_too_common'),
            ('982374651029', 'password_entirely_numeric'),
            ('cliente_politica1', 'password_too_similar'),
        ):
            with self.subTest(codigo=codigo):
                criado, codigos = self.cadastrar(senha)
                self.assertFalse(criado)
                self.assertIn(codigo, codigos)

    def test_cadastro_valido_continua_funcionando(self):
        resposta = self.client.post(reverse('principal:cadastro'), {
            'username': self.usuario, 'password1': 'Ficticia!Politica73', 'password2': 'Ficticia!Politica73',
        })
        self.assertRedirects(resposta, reverse('principal:login'))
        usuario = get_user_model().objects.get(username=self.usuario)
        self.assertTrue(usuario.check_password('Ficticia!Politica73'))
        self.assertFalse(usuario.is_staff)

    def test_conta_antiga_com_senha_curta_continua_entrando(self):
        antiga = get_user_model().objects.create_user('conta_antiga', password=None)
        antiga.set_password('Antiga!8')  # definida diretamente, como era aceito antes da mudança
        antiga.save()
        resposta = self.client.post(reverse('principal:login'), {'username': 'conta_antiga', 'password': 'Antiga!8'})
        self.assertRedirects(resposta, reverse('principal:minha_conta'))
        self.assertEqual(self.client.session[SESSION_KEY], str(antiga.pk))

    def test_definicao_de_senha_tambem_exige_doze(self):
        usuario = get_user_model().objects.create_user('conta_redefinicao', password=None)
        curta = SetPasswordForm(usuario, {'new_password1': 'Vbx!tqLm9Rz', 'new_password2': 'Vbx!tqLm9Rz'})
        self.assertFalse(curta.is_valid())
        self.assertIn('password_too_short', [e.code for e in curta.errors.as_data()['new_password2']])
        valida = SetPasswordForm(usuario, {'new_password1': 'Vbx!tqLm9Rzw', 'new_password2': 'Vbx!tqLm9Rzw'})
        self.assertTrue(valida.is_valid())
