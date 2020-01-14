# -*- coding: utf-8 -*-
# Generated by Django 1.10.1 on 2016-09-22 20:42
from __future__ import unicode_literals
from django.conf import settings
from django.db import migrations, models

# local
from .. import models as dbf_models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='DBF',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('file', models.FileField(upload_to='')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('export_date', models.DateField()),
                (
                    'notification_year',
                    models.IntegerField(default=dbf_models.current_year),
                ),
                (
                    'uploaded_by',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        )
    ]
