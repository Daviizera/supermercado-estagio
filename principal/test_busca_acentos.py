"""F-01 e F-02: busca e ordenação do catálogo sem distinção de maiúsculas, minúsculas e acentos."""
from decimal import Decimal

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .busca import NOME_FUNCAO_SQL, normalizar_texto
from .models import Categoria, Produto

URL = reverse('principal:catalogo')


class NormalizacaoTests(SimpleTestCase):
    def test_remove_acentos_e_aplica_casefold(self):
        for original, esperado in (
            ('Água SANITÁRIA', 'agua sanitaria'), ('Óleo', 'oleo'), ('FEIJÃO', 'feijao'), ('Café', 'cafe'),
            ('Açúcar', 'acucar'), ('Ç', 'c'), ('Straße', 'strasse'), ('arroz', 'arroz'), ('', ''),
            ('Água', 'agua'),  # "Á" decomposto (NFD) equivale ao composto
            ('ﬁno', 'fino'),  # ligadura de compatibilidade
        ):
            with self.subTest(original=original):
                self.assertEqual(normalizar_texto(original), esperado)
        self.assertIsNone(normalizar_texto(None))


class CatalogoAcentosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mercearia = Categoria.objects.create(nome='Mercearia')
        cls.limpeza = Categoria.objects.create(nome='Limpeza')
        nomes = (
            ('Zebra de teste', cls.mercearia), ('Óleo de soja', cls.mercearia), ('Feijão carioca', cls.mercearia),
            ('Café torrado', cls.mercearia), ('Banana prata', cls.mercearia), ('Arroz branco', cls.mercearia),
            ('Açúcar cristal', cls.mercearia), ('Água sanitária', cls.limpeza), ('Detergente neutro', cls.limpeza),
        )
        cls.produtos = {
            nome: Produto.objects.create(categoria=categoria, nome=nome, preco=Decimal('1.00'), unidade='un')
            for nome, categoria in nomes
        }
        Produto.objects.create(categoria=cls.limpeza, nome='Água inativa de teste', preco=Decimal('1.00'),
                               unidade='un', ativo=False)

    def nomes(self, **parametros):
        return [p.nome for p in self.client.get(URL, parametros).context['produtos']]

    def test_busca_sem_acento_encontra_nome_acentuado(self):
        self.assertEqual(self.nomes(q='agua'), ['Água sanitária'])
        self.assertEqual(self.nomes(q='oleo'), ['Óleo de soja'])
        self.assertEqual(self.nomes(q='cafe'), ['Café torrado'])
        self.assertEqual(self.nomes(q='sanitaria'), ['Água sanitária'])

    def test_busca_com_acento_encontra_nome_acentuado(self):
        self.assertEqual(self.nomes(q='água'), ['Água sanitária'])
        self.assertEqual(self.nomes(q='feijão'), ['Feijão carioca'])
        # Acento digitado onde o nome não tem também é tolerado.
        self.assertEqual(self.nomes(q='árróz'), ['Arroz branco'])

    def test_busca_em_maiusculas(self):
        for termo, esperado in (('ÁGUA', 'Água sanitária'), ('FEIJAO', 'Feijão carioca'), ('ÓLEO', 'Óleo de soja'),
                                ('ARROZ', 'Arroz branco'), ('CAFÉ', 'Café torrado')):
            with self.subTest(termo=termo):
                self.assertEqual(self.nomes(q=termo), [esperado])

    def test_busca_em_minusculas(self):
        for termo, esperado in (('açúcar', 'Açúcar cristal'), ('acucar', 'Açúcar cristal'), ('banana', 'Banana prata')):
            with self.subTest(termo=termo):
                self.assertEqual(self.nomes(q=termo), [esperado])

    def test_busca_parcial_de_palavras_acentuadas(self):
        for termo, esperado in (('sanit', ['Água sanitária']), ('ÇUC', ['Açúcar cristal']), ('ua san', ['Água sanitária']),
                                ('de so', ['Óleo de soja']), ('ão car', ['Feijão carioca'])):
            with self.subTest(termo=termo):
                self.assertEqual(self.nomes(q=termo), esperado)

    def test_diferentes_termos_e_varios_resultados(self):
        # "de" aparece em três nomes; o resultado segue a ordem alfabética corrigida.
        self.assertEqual(self.nomes(q='de'), ['Detergente neutro', 'Óleo de soja', 'Zebra de teste'])
        self.assertEqual(self.nomes(q='ao c'), ['Feijão carioca'])
        self.assertEqual(self.nomes(q='o'), ['Arroz branco', 'Café torrado', 'Detergente neutro', 'Feijão carioca',
                                             'Óleo de soja'])

    def test_busca_combinada_com_categoria(self):
        self.assertEqual(self.nomes(q='agua', categoria=self.limpeza.pk), ['Água sanitária'])
        self.assertEqual(self.nomes(q='agua', categoria=self.mercearia.pk), [])
        self.assertEqual(self.nomes(categoria=self.limpeza.pk), ['Água sanitária', 'Detergente neutro'])

    def test_parametros_get_continuam_preenchidos(self):
        resposta = self.client.get(URL, {'q': 'ÁGUA', 'categoria': self.limpeza.pk})
        self.assertContains(resposta, 'value="ÁGUA"')
        self.assertContains(resposta, f'<option value="{self.limpeza.pk}" selected>Limpeza</option>', html=True)
        # O nome é exibido como foi cadastrado, com acentos e maiúsculas.
        self.assertContains(resposta, '>Água sanitária</a>')

    def test_sem_resultado_quando_nada_corresponde(self):
        for termo in ('xyz', 'aguas', 'óleos', '%', '_'):
            with self.subTest(termo=termo):
                resposta = self.client.get(URL, {'q': termo})
                self.assertEqual(list(resposta.context['produtos']), [])
                self.assertContains(resposta, 'Nenhum produto encontrado para os filtros informados.')

    def test_produtos_inativos_continuam_fora(self):
        self.assertEqual(self.nomes(q='agua'), ['Água sanitária'])
        self.assertNotIn('Água inativa de teste', self.nomes())

    def test_ordenacao_agrupa_acentuadas_com_a_letra_base(self):
        self.assertEqual(self.nomes(), [
            'Açúcar cristal', 'Água sanitária', 'Arroz branco', 'Banana prata', 'Café torrado',
            'Detergente neutro', 'Feijão carioca', 'Óleo de soja', 'Zebra de teste',
        ])

    def test_ordem_dos_nomes_sem_acento_e_preservada(self):
        sem_acento = [nome for nome in self.nomes() if nome == normalizar_texto(nome).capitalize()]
        self.assertEqual(sem_acento, ['Arroz branco', 'Banana prata', 'Detergente neutro', 'Zebra de teste'])
        self.assertEqual(sem_acento, sorted(sem_acento))

    def test_ordem_estavel_para_nomes_equivalentes(self):
        repetidos = [Produto.objects.create(categoria=self.mercearia, nome='Sabão neutro', preco=Decimal('1.00'),
                                            unidade='un') for _ in range(3)]
        sem_acento = Produto.objects.create(categoria=self.mercearia, nome='Sabao neutro', preco=Decimal('1.00'),
                                            unidade='un')
        esperado = [sem_acento.pk] + [p.pk for p in repetidos]  # desempate: nome, depois pk
        for _ in range(3):
            pks = [p.pk for p in self.client.get(URL, {'q': 'sabao'}).context['produtos']]
            self.assertEqual(pks, esperado)

    def test_categorias_do_filtro_seguem_a_mesma_ordem(self):
        Categoria.objects.create(nome='Água e gelo')
        Categoria.objects.create(nome='Zeladoria')
        opcoes = [str(rotulo) for _, rotulo in self.client.get(URL).context['form'].fields['categoria'].choices][1:]
        self.assertEqual(opcoes, ['Água e gelo', 'Limpeza', 'Mercearia', 'Zeladoria'])

    def test_funcao_sql_registrada_e_nomes_armazenados_intactos(self):
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT {NOME_FUNCAO_SQL}(%s)', ['ÁGUA Sanitária'])
            self.assertEqual(cursor.fetchone()[0], 'agua sanitaria')
        self.assertEqual(Produto.objects.get(pk=self.produtos['Água sanitária'].pk).nome, 'Água sanitária')
