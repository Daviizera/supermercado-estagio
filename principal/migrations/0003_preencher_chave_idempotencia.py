# Etapa 2 de 3: gera um UUID distinto para cada pedido preexistente sem chave.
# Somente a nova coluna é preenchida; os demais dados históricos não são alterados.
import uuid

from django.db import migrations


def preencher_chaves(apps, schema_editor):
    Pedido = apps.get_model('principal', 'Pedido')
    pedidos = Pedido.objects.using(schema_editor.connection.alias)
    for pk in pedidos.filter(chave_idempotencia__isnull=True).values_list('pk', flat=True):
        # uuid4 é chamado por pedido; a etapa 3 ainda confirmará a unicidade no banco.
        pedidos.filter(pk=pk).update(chave_idempotencia=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('principal', '0002_pedido_chave_idempotencia'),
    ]

    operations = [
        # Na reversão, a etapa 1 remove a coluna inteira; não há dado a restaurar aqui.
        migrations.RunPython(preencher_chaves, migrations.RunPython.noop),
    ]
