# Generated by Django 3.2.25 on 2024-12-10 08:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('upload', '0005_auto_20241205_1020'),
    ]

    operations = [
        migrations.AddField(
            model_name='sinanupload',
            name='inserted_rows',
            field=models.IntegerField(default=0, null=True),
        ),
    ]
