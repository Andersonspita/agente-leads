import json

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.geo.models import Municipality

IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado"


class Command(BaseCommand):
    help = "Carrega (ou atualiza) os 5.570 municípios do IBGE."

    def add_arguments(self, parser):
        parser.add_argument("--file", help="JSON local no formato ?view=nivelado da API do IBGE (modo offline)")

    def handle(self, *args, **opts):
        if opts.get("file"):
            with open(opts["file"], encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            self.stdout.write("Baixando municípios da API de localidades do IBGE...")
            resp = requests.get(IBGE_URL, timeout=60)
            resp.raise_for_status()
            data = resp.json()

        with transaction.atomic():
            count = 0
            for row in data:
                Municipality(
                    codigo_ibge=str(row["municipio-id"]),
                    nome=row["municipio-nome"],
                    uf=row["UF-sigla"],
                ).save()
                count += 1
        self.stdout.write(self.style.SUCCESS(f"{count} municípios carregados."))
