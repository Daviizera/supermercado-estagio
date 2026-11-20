"""Interface compartilhada (Semana 10, etapas 1 e 2): estrutura, acessibilidade e responsividade.

Cobrem somente o que a etapa alterou no HTML/CSS; as regras de negócio seguem nos demais
módulos de teste. Todos os dados são fictícios e existem apenas no banco de testes.
"""
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from .carrinho import CHAVE_SESSAO
from .forms import EntregaForm
from .models import Categoria, EstadoPedido, Pedido, Produto
from .test_pedidos import Dados

E = EstadoPedido
CSS = Path(settings.BASE_DIR) / 'static' / 'css' / 'estilos.css'
TEMPLATES = Path(settings.BASE_DIR) / 'templates'


def links_atuais(resposta):
    """Destinos dos links marcados como página atual."""
    return re.findall(r'<a href="([^"]+)" aria-current="page">', resposta.content.decode())


class EstruturaBaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        usuarios = get_user_model().objects
        cls.cliente = usuarios.create_user('cliente_interface_teste', password=None)

    def test_link_de_salto_e_o_primeiro_item_e_aponta_para_o_main(self):
        html = self.client.get(reverse('principal:inicio')).content.decode()
        self.assertInHTML('<a class="pular-conteudo" href="#conteudo">Pular para o conteúdo</a>', html)
        corpo = html.split('<body>', 1)[1].lstrip()
        self.assertTrue(corpo.startswith('<a class="pular-conteudo" href="#conteudo">'))
        self.assertRegex(html, r'<main id="conteudo"[^>]*tabindex="-1"')
        self.assertLess(html.index('class="pular-conteudo"'), html.index('<header'))

    def test_cabecalho_usa_nome_neutro_e_rodape_simples(self):
        resposta = self.client.get(reverse('principal:inicio'))
        self.assertContains(resposta, '>Supermercado · Pedidos online</a>')
        self.assertContains(resposta, '<footer class="rodape">')

    def test_aria_current_marca_somente_a_pagina_atual(self):
        for nome in ('inicio', 'catalogo', 'carrinho', 'login', 'cadastro'):
            with self.subTest(pagina=nome):
                url = reverse(f'principal:{nome}')
                atuais = links_atuais(self.client.get(url))
                self.assertTrue(atuais)
                self.assertEqual(set(atuais), {url})

    def test_aria_current_na_area_da_conta_autenticada(self):
        self.client.force_login(self.cliente)
        for nome in ('meus_pedidos', 'minha_conta'):
            with self.subTest(pagina=nome):
                url = reverse(f'principal:{nome}')
                # A área da conta existe na versão larga e no menu <details>.
                self.assertEqual(links_atuais(self.client.get(url)), [url, url])

    def test_pagina_sem_item_de_menu_nao_marca_nenhum_link(self):
        produto = Produto.objects.create(
            categoria=Categoria.objects.create(nome='Categoria interface de teste'),
            nome='Produto interface de teste', preco=Decimal('3.00'), unidade='unidade de teste',
        )
        resposta = self.client.get(reverse('principal:detalhe_produto', args=[produto.pk]))
        self.assertEqual(links_atuais(resposta), [])

    def test_menu_movel_usa_details_e_summary(self):
        resposta = self.client.get(reverse('principal:inicio'))
        self.assertContains(resposta, '<details class="menu-movel">', count=1)
        self.assertContains(resposta, '<summary>Menu</summary>', count=1)

    def test_sair_por_post_com_csrf_nas_duas_versoes_da_area_da_conta(self):
        self.client.force_login(self.cliente)
        html = self.client.get(reverse('principal:minha_conta')).content.decode()
        formularios = re.findall(
            r'<form method="post" action="' + re.escape(reverse('principal:logout')) + r'">(.*?)</form>', html, re.S,
        )
        self.assertEqual(len(formularios), 2)
        for formulario in formularios:
            self.assertIn('name="csrfmiddlewaretoken"', formulario)
            self.assertIn('>Sair</button>', formulario)


class MenuGerenciamentoTests(Dados, TestCase):
    def setUp(self):
        self.criar_dados()

    def test_gerenciamento_aparece_nas_duas_versoes_somente_com_permissao_interna(self):
        url = reverse('principal:equipe_pedidos')
        casos = (
            (self.operador, 2), (self.staff_consulta, 2), (self.cliente, 0),
            (self.staff_sem_permissao, 0), (self.cliente_com_permissoes, 0),
        )
        for usuario, esperado in casos:
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                resposta = self.client.get(reverse('principal:inicio'))
                self.assertEqual(resposta.content.decode().count(f'href="{url}"'), esperado)


class MensagensPorTipoTests(SimpleTestCase):
    def test_cada_nivel_recebe_classe_e_prefixo_oculto_sem_alterar_o_texto(self):
        mensagens = [
            Message(constants.SUCCESS, 'Texto de sucesso de teste.'),
            Message(constants.ERROR, 'Texto de erro de teste.'),
            Message(constants.WARNING, 'Texto de aviso de teste.'),
            Message(constants.INFO, 'Texto informativo de teste.'),
        ]
        html = render_to_string('base.html', {'messages': mensagens}, request=RequestFactory().get('/'))
        for nivel, prefixo, texto in (
            ('success', 'Sucesso:', 'Texto de sucesso de teste.'),
            ('error', 'Erro:', 'Texto de erro de teste.'),
            ('warning', 'Atenção:', 'Texto de aviso de teste.'),
            ('info', 'Informação:', 'Texto informativo de teste.'),
        ):
            with self.subTest(nivel=nivel):
                self.assertRegex(
                    html,
                    rf'<li class="mensagem mensagem--{nivel}">\s*'
                    rf'<span class="visualmente-oculto">{prefixo} </span>{re.escape(texto)}\s*</li>',
                )
        self.assertIn('<ul class="mensagens" aria-live="polite">', html)


class NomesAcessiveisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        categoria = Categoria.objects.create(nome='Categoria nomes de teste')
        cls.arroz = Produto.objects.create(
            categoria=categoria, nome='Arroz nomes de teste', preco=Decimal('12.50'), unidade='pacote de teste',
        )
        cls.leite = Produto.objects.create(
            categoria=categoria, nome='Leite nomes de teste', preco=Decimal('6.70'), unidade='caixa de teste',
        )

    def preencher(self, itens):
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = itens
        sessao.save()

    def test_catalogo_identifica_o_produto_no_botao_e_no_rotulo_da_quantidade(self):
        resposta = self.client.get(reverse('principal:catalogo'))
        for produto in (self.arroz, self.leite):
            with self.subTest(produto=produto.nome):
                self.assertContains(
                    resposta,
                    f'<button type="submit" class="botao">Adicionar ao carrinho'
                    f'<span class="visualmente-oculto">: {produto.nome}</span></button>',
                    html=True,
                )
                self.assertContains(
                    resposta,
                    f'<label for="id_quantidade_{produto.pk}">Quantidade'
                    f'<span class="visualmente-oculto"> de {produto.nome}</span></label>',
                    html=True,
                )

    def test_carrinho_identifica_o_produto_em_atualizar_e_remover(self):
        self.preencher({str(self.arroz.pk): 2, str(self.leite.pk): 1})
        resposta = self.client.get(reverse('principal:carrinho'))
        for produto in (self.arroz, self.leite):
            with self.subTest(produto=produto.nome):
                self.assertContains(
                    resposta,
                    f'<button type="submit" class="botao botao--secundario">Atualizar quantidade'
                    f'<span class="visualmente-oculto"> de {produto.nome}</span></button>',
                    html=True,
                )
                self.assertContains(
                    resposta,
                    f'<button type="submit" class="botao botao--secundario">Remover'
                    f'<span class="visualmente-oculto"> {produto.nome} do carrinho</span></button>',
                    html=True,
                )

    def test_produto_excluido_e_identificado_pelo_codigo_sem_dados_antigos(self):
        excluido = Produto.objects.create(
            categoria=self.arroz.categoria, nome='Produto excluido nomes de teste',
            preco=Decimal('4.44'), unidade='unidade excluida de teste',
        )
        excluido_id = excluido.pk
        excluido.delete()
        self.preencher({str(excluido_id): 1})
        resposta = self.client.get(reverse('principal:carrinho'))
        self.assertContains(
            resposta,
            f'<span class="visualmente-oculto"> produto não encontrado (código {excluido_id}) do carrinho</span>',
            html=True,
        )
        self.assertNotContains(resposta, 'Produto excluido nomes de teste')


class TabelasResponsivasTests(Dados, TestCase):
    def setUp(self):
        self.criar_dados()

    def verificar_tabela(self, resposta, cabecalhos, rotulos):
        html = resposta.content.decode()
        self.assertIn('<table class="tabela" role="table">', html)
        self.assertEqual(html.count('<thead role="rowgroup">'), 1)
        self.assertEqual(html.count('<tbody role="rowgroup">'), 1)
        for cabecalho in cabecalhos:
            self.assertInHTML(f'<th scope="col" role="columnheader">{cabecalho}</th>', html)
        for rotulo in rotulos:
            self.assertIn(f'role="cell" data-label="{rotulo}"', html)
        self.assertNotIn('<td>', html)
        # Cada linha tem uma célula por coluna.
        for linha in re.findall(r'<tr role="row">(.*?)</tr>', html, re.S)[1:]:
            self.assertEqual(linha.count('role="cell"'), len(cabecalhos))

    def test_meus_pedidos(self):
        self.criar_pedido()
        self.client.force_login(self.cliente)
        resposta = self.client.get(reverse('principal:meus_pedidos'))
        self.verificar_tabela(
            resposta, ('Pedido', 'Data', 'Total registrado', 'Estado atual'),
            ('Data', 'Total registrado', 'Estado atual'),
        )
        self.assertContains(resposta, '<span class="valor">R$ 36,70</span>', html=True)

    def test_acompanhamento_e_detalhe_da_equipe(self):
        pedido = self.criar_pedido()
        for usuario, url in (
            (self.cliente, reverse('principal:acompanhamento_pedido', args=[pedido.pk])),
            (self.operador, reverse('principal:equipe_pedido_detalhe', args=[pedido.pk])),
        ):
            with self.subTest(url=url):
                self.client.force_login(usuario)
                resposta = self.client.get(url)
                self.verificar_tabela(
                    resposta, ('Produto / unidade', 'Quantidade', 'Preço unitário', 'Valor do item'),
                    ('Quantidade', 'Preço unitário', 'Valor do item'),
                )
                self.assertContains(resposta, '<dd class="valor"><strong>R$ 36,70</strong></dd>', html=True)

    def test_lista_da_equipe(self):
        self.criar_pedido()
        self.client.force_login(self.operador)
        resposta = self.client.get(reverse('principal:equipe_pedidos'))
        self.verificar_tabela(
            resposta, ('Pedido', 'Cliente', 'Bairro', 'Total', 'Estado'), ('Cliente', 'Bairro', 'Total', 'Estado'),
        )

    def test_carrinho(self):
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = {str(self.arroz.pk): 2}
        sessao.save()
        resposta = self.client.get(reverse('principal:carrinho'))
        self.verificar_tabela(
            resposta, ('Produto / unidade', 'Preço unitário', 'Quantidade', 'Valor do item', 'Ação'),
            ('Preço unitário', 'Valor do item'),
        )
        self.assertContains(resposta, '<span class="valor">R$ 25,00</span>', html=True)


class PainelEquipeRotulosTests(Dados, TestCase):
    ROTULOS = {
        E.CONFIRMADO: 'Confirmar pedido',
        E.EM_PREPARO: 'Iniciar preparo',
        E.SAIU_PARA_ENTREGA: 'Registrar saída para entrega',
        E.ENTREGUE: 'Concluir entrega',
        E.CANCELADO: 'Cancelar pedido',
    }

    def setUp(self):
        self.criar_dados()
        self.client.force_login(self.operador)

    def test_botoes_usam_os_verbos_do_prototipo_e_preservam_os_valores_enviados(self):
        for estado in (E.RECEBIDO, E.CONFIRMADO, E.EM_PREPARO, E.SAIU_PARA_ENTREGA):
            with self.subTest(estado=estado):
                pedido = self.criar_pedido(estado=estado)
                html = self.client.get(reverse('principal:equipe_pedido_detalhe', args=[pedido.pk])).content.decode()
                formularios = re.findall(r'<form method="post" action="([^"]+)" class="form-estado">(.*?)</form>', html, re.S)
                self.assertTrue(formularios)
                for acao, corpo in formularios:
                    self.assertEqual(acao, reverse('principal:equipe_alterar_estado', args=[pedido.pk]))
                    self.assertIn('name="csrfmiddlewaretoken"', corpo)
                    self.assertIn(f'name="estado_atual" value="{estado}"', corpo)
                    novo = re.search(r'name="novo_estado" value="([^"]+)"', corpo).group(1)
                    classe = 'botao botao--perigo' if novo == E.CANCELADO else 'botao'
                    self.assertInHTML(f'<button type="submit" class="{classe}">{self.ROTULOS[novo]}</button>', corpo)

    def test_cancelar_fica_separado_e_depois_das_demais_acoes(self):
        pedido = self.criar_pedido(estado=E.CONFIRMADO)
        html = self.client.get(reverse('principal:equipe_pedido_detalhe', args=[pedido.pk])).content.decode()
        self.assertEqual(html.count('class="acoes-estado acoes-estado--perigo"'), 1)
        self.assertLess(html.index('>Iniciar preparo<'), html.index('acoes-estado--perigo'))
        self.assertLess(html.index('acoes-estado--perigo'), html.index('>Cancelar pedido<'))

    def test_cancelar_continua_sem_etapa_extra_de_confirmacao(self):
        pedido = self.criar_pedido()
        resposta = self.client.post(
            reverse('principal:equipe_alterar_estado', args=[pedido.pk]),
            {'estado_atual': E.RECEBIDO, 'novo_estado': E.CANCELADO},
        )
        self.assertRedirects(resposta, reverse('principal:equipe_pedido_detalhe', args=[pedido.pk]))
        self.assertEqual(Pedido.objects.get(pk=pedido.pk).estado, E.CANCELADO)


class EntregaFormAtributosTests(SimpleTestCase):
    def test_preenchimento_automatico_e_teclado_de_telefone(self):
        campos = EntregaForm().fields
        self.assertEqual(campos['logradouro'].widget.attrs.get('autocomplete'), 'address-line1')
        self.assertEqual(campos['complemento'].widget.attrs.get('autocomplete'), 'address-line2')
        self.assertEqual(campos['telefone'].widget.attrs.get('autocomplete'), 'tel')
        self.assertEqual(campos['telefone'].widget.attrs.get('inputmode'), 'tel')
        self.assertNotIn('inputmode', campos['logradouro'].widget.attrs)

    def test_regras_dos_campos_nao_mudaram(self):
        campos = EntregaForm().fields
        for nome in ('logradouro', 'numero', 'complemento', 'bairro', 'telefone'):
            with self.subTest(campo=nome):
                self.assertEqual(campos[nome].max_length, Pedido._meta.get_field(nome).max_length)
                self.assertEqual(campos[nome].required, nome != 'complemento')
        html = str(EntregaForm()['telefone'])
        for atributo in ('type="text"', 'autocomplete="tel"', 'inputmode="tel"', 'maxlength="30"', 'required'):
            self.assertIn(atributo, html)

    def test_validacao_nativa_nao_e_desligada(self):
        for arquivo in TEMPLATES.rglob('*.html'):
            with self.subTest(arquivo=arquivo.name):
                self.assertNotIn('novalidate', arquivo.read_text(encoding='utf-8'))


class PaginaInicialConteudoTests(SimpleTestCase):
    def test_texto_de_apresentacao_e_link_para_o_catalogo(self):
        resposta = self.client.get(reverse('principal:inicio'))
        self.assertContains(resposta, 'Confira os produtos disponíveis e monte seu pedido online.')
        self.assertContains(
            resposta, f'<a class="botao" href="{reverse("principal:catalogo")}">Ver catálogo de produtos</a>', html=True,
        )
        self.assertNotContains(resposta, 'Semana 1')


class EstilosTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = re.sub(r'/\*.*?\*/', '', CSS.read_text(encoding='utf-8'), flags=re.S)
        cls.blocos = [
            (seletor.strip(), corpo) for seletor, corpo in re.findall(r'([^{}]+)\{([^{}]*)\}', cls.css)
        ]

    def test_quebra_agressiva_somente_em_texto_longo(self):
        com_quebra = [seletor for seletor, corpo in self.blocos if 'overflow-wrap: anywhere' in corpo]
        self.assertEqual(com_quebra, ['.texto-longo'])

    def test_valores_monetarios_nao_quebram(self):
        corpo = dict(self.blocos)['.valor']
        self.assertIn('white-space: nowrap', corpo)

    def test_cores_definidas_uma_vez_nas_variaveis(self):
        raiz = dict(self.blocos)[':root']
        fora_da_raiz = [corpo for seletor, corpo in self.blocos if seletor != ':root']
        cores = re.findall(r'#[0-9a-fA-F]{3,8}\b', raiz)
        self.assertEqual(len(cores), len({cor.lower() for cor in cores}))
        for corpo in fora_da_raiz:
            self.assertNotRegex(corpo, r'#[0-9a-fA-F]{3,8}\b')

    def test_pontos_de_quebra_mobile_first(self):
        consultas = re.findall(r'@media\s*\(([^)]*)\)', self.css)
        self.assertEqual(consultas, ['min-width: 40rem', 'min-width: 64rem', 'min-width: 80rem'])
        self.assertIn('system-ui, "Segoe UI", Roboto, Arial, sans-serif', dict(self.blocos)[':root'])


class CatalogoCartoesTests(TestCase):
    """Semana 10, etapa 2: cartões do catálogo com hierarquia sem perder recursos."""

    @classmethod
    def setUpTestData(cls):
        cls.mercearia = Categoria.objects.create(nome='Mercearia cartoes de teste')
        cls.arroz = Produto.objects.create(
            categoria=cls.mercearia, nome='Arroz cartoes de teste', preco=Decimal('12.50'), unidade='pacote de teste',
        )

    def test_cartao_separa_nome_categoria_preco_unidade_e_compra(self):
        resposta = self.client.get(reverse('principal:catalogo'))
        url = reverse('principal:detalhe_produto', args=[self.arroz.pk])
        self.assertContains(
            resposta,
            f'<h2 class="cartao-produto__nome texto-longo"><a href="{url}">{self.arroz.nome}</a></h2>', html=True,
        )
        self.assertContains(
            resposta,
            f'<p class="etiqueta-categoria"><span class="visualmente-oculto">Categoria: </span>{self.mercearia.nome}</p>',
            html=True,
        )
        self.assertContains(resposta, '<strong class="preco valor">R$ 12,50</strong>', html=True)
        self.assertContains(
            resposta,
            '<span class="cartao-produto__unidade texto-longo"><span class="visualmente-oculto">Unidade: </span>'
            'pacote de teste</span>',
            html=True,
        )
        html = resposta.content.decode()
        cartao = re.search(r'<article class="cartao-produto">(.*?)</article>', html, re.S).group(1)
        # Ordem de leitura: nome, categoria, preço e só depois o formulário de compra.
        posicoes = [cartao.index(t) for t in ('cartao-produto__nome', 'etiqueta-categoria', 'class="preco', 'form-compra')]
        self.assertEqual(posicoes, sorted(posicoes))
        self.assertIn(f'action="{reverse("principal:adicionar_ao_carrinho", args=[self.arroz.pk])}"', cartao)
        self.assertIn('name="csrfmiddlewaretoken"', cartao)

    def test_filtros_seguem_em_get_e_preservam_os_valores_informados(self):
        resposta = self.client.get(reverse('principal:catalogo'), {'q': 'arroz', 'categoria': self.mercearia.pk})
        self.assertContains(
            resposta, f'<form method="get" action="{reverse("principal:catalogo")}" class="filtros-catalogo" '
                      'role="search" aria-label="Filtrar produtos">',
        )
        self.assertContains(resposta, 'value="arroz"')
        self.assertContains(resposta, f'<option value="{self.mercearia.pk}" selected>')
        self.assertContains(resposta, self.arroz.nome)


class DetalheProdutoPainelTests(TestCase):
    """Semana 10, etapa 2: dados à esquerda e painel de compra com preço em destaque."""

    @classmethod
    def setUpTestData(cls):
        cls.categoria = Categoria.objects.create(nome='Categoria detalhe de teste')
        cls.arroz = Produto.objects.create(
            categoria=cls.categoria, nome='Arroz detalhe de teste', preco=Decimal('12.50'), unidade='pacote de teste',
        )

    def test_estrutura_e_ordem_da_pagina(self):
        html = self.client.get(reverse('principal:detalhe_produto', args=[self.arroz.pk])).content.decode()
        self.assertInHTML(f'<h1 class="texto-longo">{self.arroz.nome}</h1>', html)
        self.assertInHTML(
            f'<dl class="produto-detalhe__dados"><dt>Categoria</dt><dd>{self.categoria.nome}</dd>'
            f'<dt>Unidade</dt><dd class="texto-longo">pacote de teste</dd></dl>',
            html,
        )
        self.assertInHTML(
            '<p class="painel-compra__preco"><span class="painel-compra__rotulo">Preço</span>'
            '<strong class="preco preco--destaque valor">R$ 12,50</strong></p>',
            html,
        )
        self.assertInHTML('<button type="submit" class="botao">Adicionar ao carrinho</button>', html)
        self.assertIn('<label for="id_quantidade">Quantidade:</label>', html)
        self.assertLess(html.index('produto-detalhe__info'), html.index('painel-compra'))
        # Sem dados inventados: nenhuma imagem nem bloco de descrição.
        self.assertNotIn('<img', html)
        # Cada informação aparece uma vez no conteúdo principal.
        principal = html.split('<main', 1)[1].split('</main>', 1)[0]
        self.assertEqual(principal.count(self.categoria.nome), 1)
        self.assertEqual(principal.count('pacote de teste'), 1)

    def test_erro_de_quantidade_aparece_no_painel(self):
        resposta = self.client.post(
            reverse('principal:adicionar_ao_carrinho', args=[self.arroz.pk]), {'quantidade': '0'},
        )
        self.assertTemplateUsed(resposta, 'principal/detalhe_produto.html')
        painel = resposta.content.decode().split('class="painel-compra"', 1)[1]
        self.assertIn('<ul class="errorlist" id="id_quantidade_error">', painel)
        self.assertIn('aria-invalid="true"', painel)
        self.assertEqual(self.client.session.get(CHAVE_SESSAO, {}), {})


class RotuloQuantidadeCarrinhoTests(TestCase):
    """Semana 10, etapa 2: rótulo associado, contextual e oculto só visualmente na tabela."""

    @classmethod
    def setUpTestData(cls):
        categoria = Categoria.objects.create(nome='Categoria rotulo de teste')
        cls.arroz = Produto.objects.create(
            categoria=categoria, nome='Arroz rotulo de teste', preco=Decimal('12.50'), unidade='pacote de teste',
        )

    def setUp(self):
        sessao = self.client.session
        sessao[CHAVE_SESSAO] = {str(self.arroz.pk): 2}
        sessao.save()

    def test_rotulo_continua_associado_ao_campo(self):
        resposta = self.client.get(reverse('principal:carrinho'))
        pk = self.arroz.pk
        self.assertContains(
            resposta,
            f'<label for="id_quantidade_{pk}" class="rotulo-quantidade-carrinho">Quantidade'
            f'<span class="visualmente-oculto"> de {self.arroz.nome}</span></label>',
            html=True,
        )
        self.assertContains(resposta, f'id="id_quantidade_{pk}"')
        self.assertNotContains(resposta, 'Quantidade:</label>')

    def test_erro_mantem_identificador_e_descricao_do_campo(self):
        resposta = self.client.post(reverse('principal:atualizar_item_carrinho', args=[self.arroz.pk]), {'quantidade': 'x'})
        pk = self.arroz.pk
        self.assertContains(resposta, f'<ul class="errorlist" id="id_quantidade_{pk}_error">')
        self.assertContains(resposta, f'aria-describedby="id_quantidade_{pk}_error"')
        self.assertContains(resposta, 'aria-invalid="true"')

    def test_ocultacao_visual_somente_a_partir_de_40rem(self):
        css = re.sub(r'/\*.*?\*/', '', CSS.read_text(encoding='utf-8'), flags=re.S)
        inicio_40 = css.index('@media (min-width: 40rem)')
        inicio_64 = css.index('@media (min-width: 64rem)')
        posicoes = [m.start() for m in re.finditer(r'\.tabela \.rotulo-quantidade-carrinho', css)]
        self.assertEqual(len(posicoes), 1)
        self.assertTrue(inicio_40 < posicoes[0] < inicio_64)


class PaginaInicialHierarquiaTests(SimpleTestCase):
    def test_sem_subtitulo_isolado_e_com_textos_aprovados(self):
        html = self.client.get(reverse('principal:inicio')).content.decode()
        principal = html.split('<main', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('<h2', principal)
        self.assertEqual(principal.count('<h1'), 1)
        self.assertIn('Confira os produtos disponíveis e monte seu pedido online.', principal)
        self.assertIn('Ver catálogo de produtos', principal)
