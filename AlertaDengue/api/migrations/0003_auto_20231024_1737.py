# Generated by Django 3.2.20 on 2023-10-24 17:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_alter_historicoalerta_table'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='historicoalertachik',
            table='"Municipio"."Historico_alerta_chik"',
        ),
        migrations.AlterModelTable(
            name='historicoalertazika',
            table='"Municipio"."Historico_alerta_zika"',
        ),
    ]
