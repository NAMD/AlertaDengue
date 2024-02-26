#!/usr/bin/env bash

# Disable printing of executed commands and enable error checking
set +ex

# Set the Django settings module to ad_main.settings
export DJANGO_SETTINGS_MODULE=ad_main.settings

echo "[INFO] Starting celery..."
celery \
  --app=ad_main.celeryapp:app \
  worker -Ofair -l INFO -B
