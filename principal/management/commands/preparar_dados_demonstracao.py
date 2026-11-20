"""Cria categorias e produtos fictícios para demonstração (Semana 11, Atividade 11).

Uso (somente em desenvolvimento):
    $env:DJANGO_ENV = "development"
    python manage.py preparar_dados_demonstracao

Regras:
* só cria o que falta: categorias são identificadas pelo nome (único) e produtos pela
  combinação categoria + nome; registros existentes nunca são alterados nem apagados;
* executar de novo não duplica nada;
* tudo acontece em uma transação: ou todos os registros ausentes são criados, ou nenhum;
* não cria usuários, senhas, pedidos nem superusuários;
* os nomes são genéricos (sem marcas), sem promoções, descontos, estoque ou descrições.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from principal.models import Categoria, Produto

# (categoria, nome, preço, unidade). Preços plausíveis e fictícios, de R$ 2,49 a R$ 49,90.
PRODUTOS_DEMONSTRACAO = (
    ('Mercearia', 'Arroz branco tipo 1', '24.90', 'pacote 5 kg'),
    ('Mercearia', 'Feijão carioca', '8.49', 'pacote 1 kg'),
    ('Mercearia', 'Macarrão espaguete', '4.79', 'pacote 500 g'),
    ('Mercearia', 'Açúcar cristal', '5.29', 'pacote 1 kg'),
    ('Mercearia', 'Óleo de soja', '7.99', 'garrafa 900 mL'),
    ('Mercearia', 'Café em grãos torra média para preparo em cafeteira ou moedor', '49.90', 'pacote 1 kg'),
    ('Bebidas', 'Água mineral sem gás', '2.49', 'garrafa 1,5 L'),
    ('Bebidas', 'Suco de uva integral', '12.90', 'garrafa 1 L'),
    ('Bebidas', 'Leite integral UHT', '5.49', 'caixa 1 L'),
    ('Bebidas', 'Refrigerante sabor cola', '8.99', 'garrafa 2 L'),
    ('Limpeza', 'Detergente líquido neutro', '2.99', 'frasco 500 mL'),
    ('Limpeza', 'Água sanitária', '4.49', 'frasco 1 L'),
    ('Limpeza', 'Esponja dupla face', '3.99', 'pacote 3 unidades'),
    ('Limpeza', 'Sabão em pó para roupas brancas e coloridas em embalagem econômica', '32.90', 'pacote 2 kg'),
    ('Hortifrúti', 'Banana prata', '6.99', 'kg'),
    ('Hortifrúti', 'Tomate italiano', '9.90', 'kg'),
    ('Hortifrúti', 'Batata inglesa', '5.49', 'kg'),
    ('Hortifrúti', 'Alface crespa', '3.49', 'unidade'),
)
AMBIENTE_PERMITIDO = 'development'


class Command(BaseCommand):
    help = 'Cria categorias e produtos fictícios ausentes, sem alterar dados existentes (somente development).'

    def handle(self, *args, **options):
        ambiente = getattr(settings, 'AMBIENTE', None)
        if ambiente != AMBIENTE_PERMITIDO:
            raise CommandError(
                f'Comando permitido somente com DJANGO_ENV={AMBIENTE_PERMITIDO} '
                f'(ambiente atual: {ambiente!r}). Nenhum registro foi criado.'
            )
        criadas, categorias_existentes, criados, produtos_existentes = [], [], [], []
        with transaction.atomic():
            categorias = {}
            for nome in dict.fromkeys(item[0] for item in PRODUTOS_DEMONSTRACAO):
                categoria = Categoria.objects.filter(nome=nome).first()
                if categoria is None:
                    categoria = Categoria(nome=nome)
                    categoria.full_clean()
                    categoria.save()
                    criadas.append(nome)
                else:
                    categorias_existentes.append(nome)
                categorias[nome] = categoria
            for nome_categoria, nome, preco, unidade in PRODUTOS_DEMONSTRACAO:
                categoria = categorias[nome_categoria]
                if Produto.objects.filter(categoria=categoria, nome=nome).exists():
                    # Existente: preservado como está, mesmo que preço ou unidade sejam outros.
                    produtos_existentes.append(nome)
                    continue
                produto = Produto(categoria=categoria, nome=nome, preco=Decimal(preco), unidade=unidade)
                # full_clean antes de save: o SQLite não valida casas decimais nem tamanhos.
                produto.full_clean()
                produto.save()
                criados.append(nome)

        self._listar('Categorias criadas', criadas)
        self._listar('Categorias já existentes (mantidas)', categorias_existentes)
        self._listar('Produtos criados', criados)
        self._listar('Produtos já existentes (mantidos)', produtos_existentes)
        self.stdout.write(self.style.SUCCESS(
            f'Resumo: {len(criadas)} categoria(s) e {len(criados)} produto(s) criados; '
            f'{len(categorias_existentes)} categoria(s) e {len(produtos_existentes)} produto(s) já existiam.'
        ))

    def _listar(self, titulo, nomes):
        self.stdout.write(f'{titulo}: {len(nomes)}')
        for nome in nomes:
            self.stdout.write(f'  - {nome}')
