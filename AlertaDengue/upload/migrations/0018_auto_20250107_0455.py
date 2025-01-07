# Generated by Django 3.2.25 on 2025-01-07 04:55

from django.db import migrations, models
import upload.models


class Migration(migrations.Migration):

    dependencies = [
        ('upload', '0017_auto_20250106_2257'),
    ]

    operations = [
        migrations.AddField(
            model_name='sinanuploadlogstatus',
            name='inserts_file',
            field=models.FilePathField(null=True, path=upload.models.sinan_upload_log_path),
        ),
        migrations.AddField(
            model_name='sinanuploadlogstatus',
            name='updates_file',
            field=models.FilePathField(null=True, path=upload.models.sinan_upload_log_path),
        ),
    ]
