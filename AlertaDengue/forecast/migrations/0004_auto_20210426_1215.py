# Generated by Django 3.2 on 2021-04-26 12:15

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("forecast", "0003_auto_20180124_2239"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="forecastmodel",
            name="weeks",
        ),
        migrations.AddField(
            model_name="forecastmodel",
            name="filename",
            field=models.FileField(
                default="Trained model", upload_to="uploads/%Y/%m/%d/"
            ),
        ),
        migrations.AddField(
            model_name="forecastmodel",
            name="github",
            field=models.URLField(
                default="github.com",
                help_text="URL do repositório github",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="forecastmodel",
            name="train_end",
            field=models.DateField(
                default=django.utils.timezone.now, help_text="Data Final"
            ),
        ),
        migrations.AddField(
            model_name="forecastmodel",
            name="train_start",
            field=models.DateField(
                default=django.utils.timezone.now, help_text="Data Inicio"
            ),
        ),
        migrations.AlterField(
            model_name="forecastmodel",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.CreateModel(
            name="Forecast",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("city_geocode", models.IntegerField(help_text="Geocode")),
                (
                    "epiweek",
                    models.IntegerField(help_text="Epidemiological Week"),
                ),
                (
                    "epiweek_predicted",
                    models.IntegerField(help_text="Predicted Week"),
                ),
                (
                    "model",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="forecast.forecastmodel",
                    ),
                ),
            ],
            options={"db_table": 'forecast"."forecast'},
        ),
    ]
