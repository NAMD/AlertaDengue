# Generated by Django 3.2.25 on 2024-04-09 01:51

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SINAN",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "filename",
                    models.CharField(
                        help_text="Name of the file with suffix",
                        max_length=100,
                    ),
                ),
                (
                    "filepath",
                    models.FileField(
                        help_text="Absolute data file path, Null if deleted after insert",
                        null=True,
                        upload_to="",
                    ),
                ),
                (
                    "disease",
                    models.CharField(
                        choices=[
                            ("dengue", "Dengue"),
                            ("chik", "Chigungunya"),
                            ("zika", "Zika"),
                        ],
                        default="dengue",
                        max_length=50,
                    ),
                ),
                (
                    "notification_year",
                    models.IntegerField(),
                ),
                (
                    "uf",
                    models.CharField(
                        choices=[
                            ("BR", "Brasil"),
                            ("AC", "Acre"),
                            ("AL", "Alagoas"),
                            ("AP", "Amapá"),
                            ("AM", "Amazonas"),
                            ("BA", "Bahia"),
                            ("CE", "Ceará"),
                            ("ES", "Espírito Santo"),
                            ("GO", "Goiás"),
                            ("MA", "Maranhão"),
                            ("MT", "Mato Grosso"),
                            ("MS", "Mato Grosso do Sul"),
                            ("MG", "Minas Gerais"),
                            ("PA", "Pará"),
                            ("PB", "Paraíba"),
                            ("PR", "Paraná"),
                            ("PE", "Pernambuco"),
                            ("PI", "Piauí"),
                            ("RJ", "Rio de Janeiro"),
                            ("RN", "Rio Grande do Norte"),
                            ("RS", "Rio Grande do Sul"),
                            ("RO", "Rondônia"),
                            ("RR", "Roraima"),
                            ("SC", "Santa Catarina"),
                            ("SP", "São Paulo"),
                            ("SE", "Sergipe"),
                            ("TO", "Tocantins"),
                            ("DF", "Distrito Federal"),
                        ],
                        default="BR",
                        max_length=2,
                    ),
                ),
                ("municipio", models.IntegerField(null=True)),
                (
                    "status",
                    models.TextField(
                        choices=[
                            ("waiting_chunk", "Aguardando chunk"),
                            ("chunking", "Processando chunks"),
                            ("waiting_insert", "Aguardando inserção"),
                            ("inserting", "Inserindo dados"),
                            ("error", "Erro"),
                            ("finished", "Finalizado"),
                            ("finished_misparsed", "Finalizado com erro"),
                        ],
                        default="waiting_chunk",
                        help_text="Upload status of the file",
                    ),
                ),
                (
                    "status_error",
                    models.TextField(
                        help_text="If Status ERROR, the traceback will be stored in status_error",
                        null=True,
                    ),
                ),
                (
                    "parse_error",
                    models.BooleanField(
                        default=False,
                        help_text="An parse error ocurred when reading data, moved errored rows to `misparsed_file` file. This error doesn't change the status to ERROR",
                    ),
                ),
                (
                    "misparsed_file",
                    models.FileField(
                        default=None,
                        help_text="Absolute CSV file path containing failed rows from data parsing, before being uploaded to database. The filename format format is MISPARSED_{filename} and it requires further human verification",
                        null=True,
                        upload_to="",
                    ),
                ),
                (
                    "misparsed_cols",
                    models.JSONField(
                        default=list,
                        help_text="Name of the columns containing misparsed rows",
                    ),
                ),
                ("uploaded_at", models.DateField()),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
