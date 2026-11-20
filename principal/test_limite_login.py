"""SEG-01: limitação de tentativas no login do cliente e no login do admin.

Cada teste usa um cache LocMem próprio, limpo no início, e o banco de testes. O hasher MD5
é usado só aqui para acelerar as dezenas de tentativas; ele não altera a regra testada.
"""
import time
from unittest import mock

from django.contrib.auth import SESSION_KEY, get_user_model
from django.core.cache import caches
from django.core.cache.backends import locmem
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .limite_login import MENSAGEM_BLOQUEIO

CACHE_ISOLADO = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'teste-padrao'},
    'limite_login': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'teste-limite-login'},
}
LIMITE = {
    'CACHE': 'limite_login', 'FALHAS_POR_USUARIO_E_IP': 5, 'FALHAS_POR_IP': 30,
    'JANELA_SEGUNDOS': 900, 'BLOQUEIO_SEGUNDOS': 900,
}
IP_A = '203.0.113.10'
IP_B = '203.0.113.20'


@override_settings(
    CACHES=CACHE_ISOLADO, LIMITE_LOGIN=LIMITE,
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class Base(TestCase):
    senha = 'Ficticia!Limite73Sol'
    url = None
    destino_sucesso = None

    def setUp(self):
        caches['limite_login'].clear()
        usuarios = get_user_model().objects
        self.cliente = usuarios.create_user('cliente_limite', password=self.senha)
        self.equipe = usuarios.create_user('equipe_limite', password=self.senha, is_staff=True)

    def tentar(self, usuario, senha, ip=IP_A, cliente=None, **extra):
        cliente = cliente or Client(REMOTE_ADDR=ip)
        return cliente.post(self.url, {'username': usuario, 'password': senha}, REMOTE_ADDR=ip, **extra)

    def falhar(self, vezes, usuario, ip=IP_A):
        for numero in range(vezes):
            resposta = self.tentar(usuario, f'Errada!{numero}x', ip=ip)
            self.assertEqual(resposta.status_code, 200)
            self.assertNotContains(resposta, MENSAGEM_BLOQUEIO)

    def assertBloqueado(self, resposta):
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, MENSAGEM_BLOQUEIO)
        self.assertNotIn(SESSION_KEY, resposta.wsgi_request.session)

    def assertEntrou(self, resposta, usuario):
        self.assertRedirects(resposta, self.destino_sucesso, fetch_redirect_response=False)
        self.assertEqual(str(resposta.wsgi_request.session[SESSION_KEY]), str(usuario.pk))


class LoginClienteTests(Base):
    url = '/login/'
    destino_sucesso = '/minha-conta/'

    def test_tentativa_seguinte_ao_limite_e_bloqueada(self):
        self.falhar(5, 'cliente_limite')
        self.assertBloqueado(self.tentar('cliente_limite', 'Errada!depois'))

    def test_bloqueio_impede_ate_a_senha_correta(self):
        self.falhar(5, 'cliente_limite')
        self.assertBloqueado(self.tentar('cliente_limite', self.senha))

    def test_acesso_volta_apos_o_bloqueio_expirar(self):
        self.falhar(5, 'cliente_limite')
        agora = time.time()
        with mock.patch.object(locmem.time, 'time', return_value=agora + 899):
            self.assertBloqueado(self.tentar('cliente_limite', self.senha))
        with mock.patch.object(locmem.time, 'time', return_value=agora + 901):
            self.assertEntrou(self.tentar('cliente_limite', self.senha), self.cliente)

    def test_falhas_expiram_sem_formar_bloqueio(self):
        self.falhar(4, 'cliente_limite')
        with mock.patch.object(locmem.time, 'time', return_value=time.time() + 901):
            self.falhar(4, 'cliente_limite')

    def test_outro_ip_nao_herda_o_bloqueio_do_par_usuario_ip(self):
        self.falhar(5, 'cliente_limite', ip=IP_A)
        self.assertBloqueado(self.tentar('cliente_limite', self.senha, ip=IP_A))
        self.assertEntrou(self.tentar('cliente_limite', self.senha, ip=IP_B), self.cliente)

    def test_login_bem_sucedido_zera_o_contador_do_par(self):
        self.falhar(4, 'cliente_limite')
        self.assertEntrou(self.tentar('cliente_limite', self.senha), self.cliente)
        # Sem a limpeza, estas falhas somariam 8 e bloqueariam o login seguinte.
        self.falhar(4, 'cliente_limite')
        self.assertEntrou(self.tentar('cliente_limite', self.senha), self.cliente)

    def test_nao_revela_se_o_usuario_existe(self):
        respostas = {}
        for usuario in ('cliente_limite', 'usuario_inexistente_limite'):
            antes = self.tentar(usuario, 'Errada!0x')
            self.falhar(4, usuario)
            bloqueada = self.tentar(usuario, 'Errada!depois')
            self.assertBloqueado(bloqueada)
            respostas[usuario] = (
                antes.status_code, list(antes.context['form'].non_field_errors()),
                bloqueada.status_code, list(bloqueada.context['form'].non_field_errors()),
            )
        self.assertEqual(respostas['cliente_limite'], respostas['usuario_inexistente_limite'])

    def test_variacoes_de_maiusculas_contam_para_o_mesmo_usuario(self):
        for numero, variacao in enumerate(('cliente_limite', 'Cliente_Limite', 'CLIENTE_LIMITE',
                                            'cLiEnTe_LiMiTe', 'ｃｌｉｅｎｔｅ_limite')):
            self.assertNotContains(self.tentar(variacao, f'Errada!{numero}'), MENSAGEM_BLOQUEIO)
        self.assertBloqueado(self.tentar('cliente_limite', self.senha))

    def test_falhas_de_csrf_nao_contam(self):
        protegido = Client(enforce_csrf_checks=True, REMOTE_ADDR=IP_A)
        for numero in range(10):
            resposta = protegido.post(self.url, {'username': 'cliente_limite', 'password': f'Errada!{numero}'},
                                      REMOTE_ADDR=IP_A)
            self.assertEqual(resposta.status_code, 403)
        self.assertEqual(len(caches['limite_login']._cache), 0)
        self.assertEntrou(self.tentar('cliente_limite', self.senha), self.cliente)

    def test_limite_amplo_por_ip(self):
        for numero in range(30):
            self.tentar(f'nome_variado_{numero}', 'Errada!1x')
        # O endereço fica bloqueado mesmo para um nome ainda não usado e com a senha correta.
        self.assertBloqueado(self.tentar('cliente_limite', self.senha, ip=IP_A))
        self.assertEntrou(self.tentar('cliente_limite', self.senha, ip=IP_B), self.cliente)

    def test_x_forwarded_for_nao_contorna_o_limite(self):
        for numero in range(5):
            self.tentar('cliente_limite', f'Errada!{numero}', HTTP_X_FORWARDED_FOR=f'198.51.100.{numero}')
        self.assertBloqueado(self.tentar('cliente_limite', self.senha, HTTP_X_FORWARDED_FOR='198.51.100.99'))

    def test_chaves_de_cache_nao_contem_usuario_nem_ip(self):
        self.falhar(2, 'cliente_limite')
        chaves = ' '.join(caches['limite_login']._cache)
        self.assertTrue(chaves)
        for texto in ('cliente_limite', IP_A):
            self.assertNotIn(texto, chaves)

    def test_erro_de_campo_obrigatorio_nao_conta_como_falha(self):
        for _ in range(10):
            self.client.post(self.url, {'username': 'cliente_limite', 'password': ''}, REMOTE_ADDR=IP_A)
        self.assertEqual(len(caches['limite_login']._cache), 0)


class LoginAdminTests(Base):
    url = '/admin/login/'
    destino_sucesso = '/admin/'

    def tentar(self, usuario, senha, ip=IP_A, cliente=None, **extra):
        cliente = cliente or Client(REMOTE_ADDR=ip)
        return cliente.post(self.url, {'username': usuario, 'password': senha, 'next': '/admin/'},
                            REMOTE_ADDR=ip, **extra)

    def test_admin_respeita_o_limite(self):
        self.falhar(5, 'equipe_limite')
        self.assertBloqueado(self.tentar('equipe_limite', self.senha))

    def test_admin_autentica_normalmente_sem_bloqueio(self):
        self.assertEntrou(self.tentar('equipe_limite', self.senha), self.equipe)

    def test_admin_mantem_a_recusa_nativa_de_contas_sem_is_staff(self):
        resposta = self.tentar('cliente_limite', self.senha)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn(SESSION_KEY, resposta.wsgi_request.session)
        self.assertEqual([e.code for e in resposta.context['form'].non_field_errors().as_data()], ['invalid_login'])

    def test_bloqueio_do_admin_expira(self):
        self.falhar(5, 'equipe_limite')
        with mock.patch.object(locmem.time, 'time', return_value=time.time() + 901):
            self.assertEntrou(self.tentar('equipe_limite', self.senha), self.equipe)

    def test_site_e_admin_compartilham_o_contador(self):
        # O mesmo par usuário/IP não ganha tentativas extras alternando entre os dois logins.
        for numero in range(3):
            self.tentar('equipe_limite', f'Errada!{numero}')
        for numero in range(2):
            Client().post('/login/', {'username': 'equipe_limite', 'password': f'Errada!s{numero}'}, REMOTE_ADDR=IP_A)
        self.assertBloqueado(self.tentar('equipe_limite', self.senha))
