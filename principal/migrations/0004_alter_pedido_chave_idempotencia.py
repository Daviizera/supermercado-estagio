# Etapa 3 de 3: com todas as linhas preenchidas, torna a chave obrigatória e única.
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('principal', '0003_preencher_chave_idempotencia'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pedido',
            name='chave_idempotencia',
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, unique=True,
                verbose_name='chave de idempotência',
            ),
        ),
    ]
