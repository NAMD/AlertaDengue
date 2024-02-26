import logging
import os
import shutil
from datetime import datetime
from email.mime.image import MIMEImage
from pathlib import Path

from ad_main import settings

# from .celery import app
from ad_main.celeryapp import app
from celery.schedules import crontab
from dados.episem import episem
from dbf.db import is_partner_active
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import DBF
from .sinan import Sinan

app.conf.beat_schedule = {
    "send-mail-daily": {
        "task": "dbf.tasks.send_mail_partner",
        "schedule": crontab(
            minute="0",
            hour="3",
            day="*",
            month="*",
            day_of_week="1"
        ),
    },
}


def send_success_email(dbf):

    subject = (
        "[InfoDengue] DBF enviado em {:%d/%m/%Y} "
        "importado com successo".format(dbf.uploaded_at)
    )
    body = render_to_string(
        "successful_import_email.txt", context={"dbf": dbf}
    )
    from_email, to = settings.EMAIL_FROM_USER, settings.EMAIL_TO_ADDRESS
    msg = EmailMultiAlternatives(subject, body, from_email, [to])
    msg.send()


def send_failure_email(dbf, message):

    subject = (
        "[InfoDengue] Falha ao importar DBF enviado em "
        "{:%d/%m/%Y}".format(dbf.uploaded_at)
    )
    body = render_to_string(
        "failed_import_email.txt",
        context={"dbf": dbf, "error_message": message},
    )
    from_email, to = settings.EMAIL_FROM_USER, settings.EMAIL_TO_ADDRESS
    msg = EmailMultiAlternatives(subject, body, from_email, [to])
    msg.send()


def copy_file_to_final_destination(dbf):

    imported_files = str(Path(settings.DBF_SINAN) / "imported")

    new_filename = "{}_{}_{}_{}.dbf".format(
        dbf.abbreviation,
        dbf.municipio,
        dbf.export_date,
        dbf.notification_year,
    )
    src = dbf.file.path
    dest = os.path.join(imported_files, new_filename)
    shutil.copy(src, dest)


@app.task(name="import_dbf_to_database")
def import_dbf_to_database(dbf_id):
    dbf = DBF.objects.get(id=dbf_id)
    try:
        # Unfortunately dbfread does not allow us to use a file object. We
        # have to give it a file path and it will read from the disc.
        sinan = Sinan(dbf.file.path, dbf.notification_year)
        sinan.save_to_pgsql()
        send_success_email(dbf)
        copy_file_to_final_destination(dbf)
    except ValidationError as exc:
        send_failure_email(dbf, exc.message)


# Used to send emails from partners
class MissingConnectionException(Exception):
    pass


def get_connection(label=None, **kwargs):
    if label is None:
        label = getattr(settings, "EMAIL_CONNECTION_DEFAULT", None)

    try:
        connections = getattr(settings, "EMAIL_CONNECTIONS")
        options = connections[label]
    except KeyError:
        raise MissingConnectionException(
            'Settings for connection "%s" were not found' % label
        )

    options.update(kwargs)
    return mail.get_connection(**options)


@app.task(name="send_mail_partner")
def send_mail_partner(
    fail_silently=False,
    connection=None,
):
    mailing = is_partner_active()
    connection = get_connection()
    messages = []

    dt_now = datetime.now().strftime("%Y-%m-%d")
    year_week = episem(dt_now, sep="")
    week = year_week[-2:]
    last_week = int(week) - 1

    for idx, row in mailing.iterrows():
        subject = f"Informe de dados Infodengue SE{last_week}"
        body = render_to_string(
            "email_secretarias.txt",
            context={"name": row["contact"], "context_message": last_week},
        )
        message = EmailMultiAlternatives(
            subject, body, settings.EMAIL_OUTLOOK_USER, [row["email"]]
        )
        logging.info(f"Enviando email para: {row['email']},")
        fp = open(
            os.path.join(
                settings.STATICFILES_DIRS[0], "img/logo_signature.png"
            ),
            "rb",
        )
        img_signature = MIMEImage(fp.read())
        fp.close()
        message.attach(img_signature)
        messages.append(message)

    connection.send_messages(messages)
