from datetime import datetime
from typing import Literal

from ad_main.celeryapp import app
from celery.schedules import crontab
from dados.dbdata import ALL_STATE_NAMES
from scanner.scanner import EpiScanner

app.conf.beat_schedule = {
    "episcanner-dengue-current-year": {
        "task": "dados.tasks.episcanner_all_states",
        "schedule": crontab(minute=0, hour=3, day_of_month=13),
        "args": (datetime.now().year, "dengue"),
    },
    "episcanner-zika-current-year": {
        "task": "dados.tasks.episcanner_all_states",
        "schedule": crontab(minute=0, hour=3, day_of_month=14),
        "args": (datetime.now().year, "zika"),
    },
    "episcanner-chik-current-year": {
        "task": "dados.tasks.episcanner_all_states",
        "schedule": crontab(minute=0, hour=3, day_of_month=15),
        "args": (datetime.now().year, "chik"),
    },
}

DATA_DIR = "/opt/services/episcanner"


@app.task
def episcanner_all_states(
    year: int,
    disease: Literal["dengue", "zika", "chik"]
):
    """
    Runs EpiScanner for all states for disease & year and exports
    to EPISCANNER_HOST_DIR in the duckdb format
    """
    for state in ALL_STATE_NAMES:
        try:
            scanner = EpiScanner(disease=disease, uf=state, year=year)
            scanner.export("duckdb", output_dir=DATA_DIR)
        except ValueError:
            continue
