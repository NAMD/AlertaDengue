#!/usr/bin/env python3

from dbf.pysus import PySUS
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Imports PySUS DBC into the database"

    def add_arguments(self, parser):
        parser.add_argument("ano", type=str)
        parser.add_argument("disease", type=str)

    def handle(self, *args, **options):
        try:
            pysus = PySUS(options["ano"], options["disease"])
            pysus.save()
        except ValidationError as e:
            raise CommandError("Arquivo inválido: {}".format(e.message))
