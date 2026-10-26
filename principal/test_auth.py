from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from .models import Categoria, Produto


class AutenticacaoClientesTests(TestCase):
    """Exercita as rotas reais com usuários restritos ao banco temporário de testes."""

    senha = 'Chuva!Telhado42Mar'

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(
            username='cliente_alfa', password=cls.senha,
        )
        cls.outro_usuario = get_user_model().objects.create_user(
            username='cliente_beta', password=cls.senha,
        )

    def dados_cadastro(self, **alteracoes):
        dados = {
            'username': 'cliente_novo',
            'password1': self.senha,
            'password2': self.senha,
        }
        dados.update(alteracoes)
        return dados

    def test_cadastro_exibe_formulario_nativo_com_labels_e_csrf(self):
        resposta = self.client.get(reverse('principal:cadastro'))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'registration/cadastro.html')
        self.assertTemplateUsed(resposta, 'base.html')
        formulario = resposta.context['form']
        self.assertIsInstance(formulario, UserCreationForm)
        self.assertEqual(list(formulario.fields), ['username', 'password1', 'password2'])
        for campo in formulario:
            with self.subTest(campo=campo.name):
                self.assertContains(resposta, f'name="{campo.name}"')
                self.assertContains(resposta, f'for="{campo.id_for_label}"')
        self.assertContains(resposta, 'name="csrfmiddlewaretoken"')

    def test_cadastro_persiste_hash_e_redireciona_com_sucesso_sem_login_automatico(self):
        resposta = self.client.post(
            reverse('principal:cadastro'), self.dados_cadastro(), follow=True,
        )

        self.assertRedirects(resposta, reverse('principal:login'))
        usuario = get_user_model().objects.get(username='cliente_novo')
        self.assertEqual(get_user_model().objects.count(), 3)
        self.assertNotEqual(usuario.password, self.senha)
        self.assertTrue(usuario.check_password(self.senha))
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertTrue(usuario.is_active)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertContains(resposta, 'Cadastro realizado com sucesso.')

    def test_cadastro_exige_todos_os_campos_sem_criar_usuario(self):
        for campo in ('username', 'password1', 'password2'):
            with self.subTest(campo=campo):
                dados = self.dados_cadastro()
                dados.pop(campo)
                resposta = self.client.post(reverse('principal:cadastro'), dados)

                self.assertEqual(resposta.status_code, 200)
                formulario = resposta.context['form']
                self.assertEqual(formulario.errors.as_data()[campo][0].code, 'required')
                self.assertContains(resposta, str(formulario[campo].errors))
                self.assertEqual(get_user_model().objects.count(), 2)

    def test_cadastro_rejeita_nome_duplicado_inclusive_com_caixa_diferente(self):
        for nome in (self.usuario.username, self.usuario.username.upper()):
            with self.subTest(nome=nome):
                resposta = self.client.post(
                    reverse('principal:cadastro'), self.dados_cadastro(username=nome),
                )

                self.assertEqual(resposta.status_code, 200)
                self.assertIn('username', resposta.context['form'].errors)
                self.assertEqual(get_user_model().objects.count(), 2)

    def test_cadastro_rejeita_senhas_diferentes_preserva_nome_e_limpa_senhas(self):
        resposta = self.client.post(
            reverse('principal:cadastro'),
            self.dados_cadastro(password2='Outra!Senha73Mar'),
        )

        self.assertEqual(resposta.status_code, 200)
        formulario = resposta.context['form']
        self.assertEqual(
            formulario.errors.as_data()['password2'][0].code, 'password_mismatch',
        )
        self.assertContains(resposta, 'value="cliente_novo"')
        self.assertContains(resposta, str(formulario['password2'].errors))
        for campo in ('password1', 'password2'):
            self.assertNotIn('value=', str(formulario[campo]))
        self.assertNotContains(resposta, self.senha)
        self.assertNotContains(resposta, 'Outra!Senha73Mar')
        self.assertEqual(get_user_model().objects.count(), 2)

    def test_cadastro_aplica_os_quatro_validadores_padrao_de_senha(self):
        for senha, codigo in (
            ('Z!7a', 'password_too_short'),
            ('password', 'password_too_common'),
            ('987654321098', 'password_entirely_numeric'),
            ('cliente_novo', 'password_too_similar'),
        ):
            with self.subTest(validador=codigo):
                resposta = self.client.post(
                    reverse('principal:cadastro'),
                    self.dados_cadastro(password1=senha, password2=senha),
                )

                self.assertEqual(resposta.status_code, 200)
                erros = resposta.context['form'].errors.as_data()['password2']
                self.assertIn(codigo, [erro.code for erro in erros])
                self.assertEqual(get_user_model().objects.count(), 2)

    def test_cadastro_ignora_privilegios_enviados_e_cliente_nao_administra_cadastros(self):
        permissao = Permission.objects.get(codename='add_produto')
        resposta = self.client.post(
            reverse('principal:cadastro'),
            self.dados_cadastro(
                is_staff='on', is_superuser='on', user_permissions=[permissao.pk],
            ),
        )

        self.assertRedirects(resposta, reverse('principal:login'))
        usuario = get_user_model().objects.get(username='cliente_novo')
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertFalse(usuario.user_permissions.exists())
        self.assertFalse(usuario.groups.exists())
        login = self.client.post(
            reverse('principal:login'),
            {'username': usuario.username, 'password': self.senha},
        )
        self.assertRedirects(login, reverse('principal:minha_conta'))
        for destino in (
            'admin:index', 'admin:principal_categoria_add', 'admin:principal_produto_add',
        ):
            url = reverse(destino)
            with self.subTest(destino=destino):
                self.assertRedirects(
                    self.client.get(url), reverse('admin:login') + '?next=' + url,
                )
                self.assertEqual(self.client.post(url, {'nome': 'Sem permissão'}).status_code, 302)
        self.assertEqual(Categoria.objects.count(), 0)
        self.assertEqual(Produto.objects.count(), 0)

    def test_login_exibe_formulario_nativo_csrf_e_preserva_next(self):
        resposta = self.client.get(
            reverse('principal:login'), {'next': reverse('principal:minha_conta')},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'registration/login.html')
        self.assertIsInstance(resposta.context['form'], AuthenticationForm)
        for campo in resposta.context['form']:
            self.assertContains(resposta, f'name="{campo.name}"')
            self.assertContains(resposta, f'for="{campo.id_for_label}"')
        self.assertContains(resposta, 'name="csrfmiddlewaretoken"')
        self.assertContains(resposta, 'name="next"')
        self.assertContains(resposta, 'value="' + reverse('principal:minha_conta') + '"')
        self.assertContains(resposta, reverse('principal:cadastro'))

    def test_login_valido_mantem_sessao_entre_requisicoes(self):
        sessao = self.client.session
        sessao['marcador_visitante'] = 'origem_teste'
        sessao.save()
        chave_anterior = sessao.session_key

        resposta = self.client.post(
            reverse('principal:login'),
            {'username': self.usuario.username, 'password': self.senha},
        )

        self.assertRedirects(resposta, reverse('principal:minha_conta'))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.usuario.pk))
        self.assertNotEqual(self.client.session.session_key, chave_anterior)
        self.assertEqual(self.client.session['marcador_visitante'], 'origem_teste')
        for destino in ('principal:inicio', 'principal:minha_conta'):
            resposta = self.client.get(reverse(destino))
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.wsgi_request.user.pk, self.usuario.pk)
            self.assertTrue(resposta.wsgi_request.user.is_authenticated)

    def test_login_invalido_nao_revela_se_nome_existe_nem_reapresenta_senha(self):
        mensagens = []
        for nome in (self.usuario.username, 'usuario_inexistente'):
            with self.subTest(nome=nome):
                resposta = self.client.post(
                    reverse('principal:login'), {'username': nome, 'password': 'SenhaErrada!'},
                )

                self.assertEqual(resposta.status_code, 200)
                formulario = resposta.context['form']
                mensagens.append(list(formulario.non_field_errors()))
                self.assertTrue(formulario.non_field_errors())
                self.assertContains(resposta, str(formulario.non_field_errors()))
                self.assertContains(resposta, f'value="{nome}"')
                self.assertNotIn('value=', str(formulario['password']))
                self.assertNotContains(resposta, 'SenhaErrada!')
                self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(mensagens[0], mensagens[1])

    def test_login_rejeita_usuario_inativo(self):
        self.usuario.is_active = False
        self.usuario.save(update_fields=['is_active'])

        resposta = self.client.post(
            reverse('principal:login'),
            {'username': self.usuario.username, 'password': self.senha},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context['form'].non_field_errors())
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_aceita_next_interno(self):
        destino = reverse('principal:inicio') + '?origem=login'
        resposta = self.client.post(
            reverse('principal:login'),
            {'username': self.usuario.username, 'password': self.senha, 'next': destino},
        )

        self.assertRedirects(resposta, destino)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.usuario.pk))

    def test_login_rejeita_next_externo_e_esquema_inseguro(self):
        for destino in (
            'https://example.invalid/coleta', '//example.invalid/coleta',
            'javascript:alert(1)',
        ):
            with self.subTest(destino=destino):
                cliente = Client()
                resposta = cliente.post(
                    reverse('principal:login'),
                    {'username': self.usuario.username, 'password': self.senha, 'next': destino},
                )

                self.assertRedirects(resposta, reverse('principal:minha_conta'))
                self.assertEqual(cliente.session[SESSION_KEY], str(self.usuario.pk))

    def test_visitante_precisa_de_login_para_acessar_area_privada(self):
        resposta = self.client.get(reverse('principal:minha_conta'))

        self.assertRedirects(
            resposta, reverse('principal:login') + '?next=' + reverse('principal:minha_conta'),
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_area_privada_identifica_sessao_e_ignora_identificadores_da_query(self):
        self.client.post(
            reverse('principal:login'),
            {'username': self.usuario.username, 'password': self.senha},
        )
        resposta = self.client.get(
            reverse('principal:minha_conta'),
            {'user_id': self.outro_usuario.pk, 'username': self.outro_usuario.username},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, 'principal/minha_conta.html')
        self.assertEqual(resposta.wsgi_request.user.pk, self.usuario.pk)
        self.assertContains(resposta, self.usuario.username)
        self.assertNotContains(resposta, self.outro_usuario.username)
        self.assertNotContains(resposta, self.usuario.password)

    def test_duas_sessoes_isolam_identidade_e_logout(self):
        clientes = [(Client(), self.usuario), (Client(), self.outro_usuario)]
        for cliente, usuario in clientes:
            resposta = cliente.post(
                reverse('principal:login'),
                {'username': usuario.username, 'password': self.senha},
            )
            self.assertRedirects(resposta, reverse('principal:minha_conta'))
        self.assertNotEqual(clientes[0][0].session.session_key, clientes[1][0].session.session_key)
        for cliente, usuario in clientes:
            resposta = cliente.get(reverse('principal:minha_conta'))
            outro = self.outro_usuario if usuario == self.usuario else self.usuario
            self.assertEqual(cliente.session[SESSION_KEY], str(usuario.pk))
            self.assertContains(resposta, usuario.username)
            self.assertNotContains(resposta, outro.username)
        clientes[0][0].post(reverse('principal:logout'))
        self.assertNotIn(SESSION_KEY, clientes[0][0].session)
        self.assertEqual(clientes[1][0].session[SESSION_KEY], str(self.outro_usuario.pk))
        self.assertContains(
            clientes[1][0].get(reverse('principal:minha_conta')), self.outro_usuario.username,
        )

    def test_navegacao_do_visitante_oferece_login_e_cadastro(self):
        resposta = self.client.get(reverse('principal:inicio'))

        self.assertContains(resposta, reverse('principal:login'))
        self.assertContains(resposta, reverse('principal:cadastro'))
        self.assertNotContains(resposta, reverse('principal:logout'))
        self.assertNotContains(resposta, reverse('principal:minha_conta'))

    def test_navegacao_autenticada_exibe_identidade_conta_e_logout_por_formulario(self):
        self.client.post(
            reverse('principal:login'),
            {'username': self.usuario.username, 'password': self.senha},
        )
        resposta = self.client.get(reverse('principal:inicio'))

        self.assertContains(resposta, self.usuario.username)
        self.assertContains(resposta, reverse('principal:minha_conta'))
        self.assertContains(resposta, 'action="' + reverse('principal:logout') + '"')
        self.assertContains(resposta, 'method="post"')
        self.assertContains(resposta, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(resposta, 'href="' + reverse('principal:logout') + '"')
        self.assertNotContains(resposta, 'href="' + reverse('principal:login') + '"')
        self.assertNotContains(resposta, 'href="' + reverse('principal:cadastro') + '"')

    def test_logout_post_encerra_sessao_redireciona_e_bloqueia_area_privada(self):
        self.client.post(
            reverse('principal:login'),
            {'username': self.usuario.username, 'password': self.senha},
        )
        self.assertIn(SESSION_KEY, self.client.session)
        chave_anterior = self.client.session.session_key

        resposta = self.client.post(reverse('principal:logout'))

        self.assertRedirects(resposta, reverse('principal:inicio'))
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertRedirects(
            self.client.get(reverse('principal:minha_conta')),
            reverse('principal:login') + '?next=' + reverse('principal:minha_conta'),
        )
        cliente_com_cookie_antigo = Client()
        cliente_com_cookie_antigo.cookies[settings.SESSION_COOKIE_NAME] = chave_anterior
        self.assertRedirects(
            cliente_com_cookie_antigo.get(reverse('principal:minha_conta')),
            reverse('principal:login') + '?next=' + reverse('principal:minha_conta'),
        )
        self.assertNotIn(SESSION_KEY, cliente_com_cookie_antigo.session)

    def test_logout_get_e_rejeitado_sem_encerrar_sessao(self):
        self.client.post(
            reverse('principal:login'),
            {'username': self.usuario.username, 'password': self.senha},
        )

        resposta = self.client.get(reverse('principal:logout'))

        self.assertEqual(resposta.status_code, 405)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.usuario.pk))
        self.assertEqual(self.client.get(reverse('principal:minha_conta')).status_code, 200)

    def test_logout_ignora_next_na_query_e_no_post(self):
        url = reverse('principal:logout')
        destino = reverse('principal:login')
        for endereco, dados in ((url + '?next=' + destino, {}), (url, {'next': destino})):
            with self.subTest(endereco=endereco, dados=dados):
                cliente = Client()
                cliente.force_login(self.usuario)

                resposta = cliente.post(endereco, dados)

                self.assertRedirects(resposta, reverse('principal:inicio'))
                self.assertNotIn(SESSION_KEY, cliente.session)

    def test_cadastro_exige_csrf_e_aceita_token_valido(self):
        cliente = Client(enforce_csrf_checks=True)
        url = reverse('principal:cadastro')
        cliente.get(url)

        self.assertEqual(cliente.post(url, self.dados_cadastro()).status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username='cliente_novo').exists())
        token = cliente.cookies[settings.CSRF_COOKIE_NAME].value
        resposta = cliente.post(url, self.dados_cadastro(csrfmiddlewaretoken=token))

        self.assertRedirects(resposta, reverse('principal:login'))
        self.assertTrue(get_user_model().objects.filter(username='cliente_novo').exists())
        self.assertNotIn(SESSION_KEY, cliente.session)

    def test_login_exige_csrf_e_rotaciona_token_apos_autenticacao(self):
        cliente = Client(enforce_csrf_checks=True)
        url = reverse('principal:login')
        cliente.get(url)
        dados = {'username': self.usuario.username, 'password': self.senha}

        self.assertEqual(cliente.post(url, dados).status_code, 403)
        self.assertNotIn(SESSION_KEY, cliente.session)
        token = cliente.cookies[settings.CSRF_COOKIE_NAME].value
        resposta = cliente.post(url, {**dados, 'csrfmiddlewaretoken': token})

        self.assertRedirects(resposta, reverse('principal:minha_conta'))
        self.assertEqual(cliente.session[SESSION_KEY], str(self.usuario.pk))
        self.assertNotEqual(cliente.cookies[settings.CSRF_COOKIE_NAME].value, token)

    def test_logout_exige_csrf_preserva_sessao_na_rejeicao_e_aceita_token_valido(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.get(reverse('principal:login'))
        login = cliente.post(
            reverse('principal:login'),
            {
                'username': self.usuario.username,
                'password': self.senha,
                'csrfmiddlewaretoken': cliente.cookies[settings.CSRF_COOKIE_NAME].value,
            },
        )
        self.assertRedirects(login, reverse('principal:minha_conta'))
        url = reverse('principal:logout')

        for dados in ({}, {'csrfmiddlewaretoken': 'token-invalido'}):
            with self.subTest(dados=dados):
                self.assertEqual(cliente.post(url, dados).status_code, 403)
                self.assertEqual(cliente.session[SESSION_KEY], str(self.usuario.pk))
        resposta = cliente.post(
            url, {'csrfmiddlewaretoken': cliente.cookies[settings.CSRF_COOKIE_NAME].value},
        )

        self.assertRedirects(resposta, reverse('principal:inicio'))
        self.assertNotIn(SESSION_KEY, cliente.session)
        self.assertRedirects(
            cliente.get(reverse('principal:minha_conta')),
            reverse('principal:login') + '?next=' + reverse('principal:minha_conta'),
        )
