import os

from celery import Celery

# This makes sure celery knows where settings are, so we don't need to set it
# when calling it from the command line
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ad_main.settings")


app = Celery("ad_main", include=["dbf.tasks"])
app.config_from_object("ad_main.celery_settings", namespace="CELERY")
app.autodiscover_tasks()
