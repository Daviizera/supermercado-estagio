# Etapa 1 de 3: adiciona a chave como anulável e sem unicidade, compatível com pedidos
# já existentes. Um default calculado uma única vez daria o mesmo UUID a todas as linhas.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('principal', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='chave_idempotencia',
            field=models.UUIDField(editable=False, null=True, verbose_name='chave de idempotência'),
        ),
    ]
