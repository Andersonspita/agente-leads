"""Importa um recorte da base aberta de CNPJ da Receita Federal.

Arquivos em https://arquivos.receitafederal.gov.br/ (Dados Abertos CNPJ):
  - Estabelecimentos*.zip  (obrigatório; pode passar vários)
  - Municipios.zip         (obrigatório; mapeia o código da Receita para o IBGE pelo nome + UF)
  - Empresas*.zip          (opcional; traz a razão social)

Só entram estabelecimentos ATIVOS, dos CNAEs das categorias cadastradas (ou --cnaes)
e, se informado, das UFs em --uf. Do e-mail cadastral só o domínio corporativo é
guardado (para descobrir o site); o endereço de e-mail não é armazenado (LGPD).

Exemplo:
  python manage.py import_cnpj --municipios Municipios.zip --estabelecimentos Estabelecimentos0.zip --uf BA
"""
import csv
import glob
import io
import zipfile
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Category
from apps.core.text import normalize, only_digits
from apps.geo.models import Municipality
from apps.leads.discovery.site_finder import email_domain
from apps.leads.models import CnpjEstablishment

ACTIVE = "02"
BATCH = 2000


def open_rows(path):
    """Lê CSV (ou o único CSV dentro de um .zip) no formato da Receita: ';', latin-1, sem cabeçalho."""
    if path.lower().endswith(".zip"):
        zf = zipfile.ZipFile(path)
        name = zf.namelist()[0]
        stream = io.TextIOWrapper(zf.open(name), encoding="latin-1", newline="")
    else:
        stream = open(path, encoding="latin-1", newline="")
    return csv.reader(stream, delimiter=";", quotechar='"')


class Command(BaseCommand):
    help = "Importa estabelecimentos ativos da base aberta de CNPJ (Receita Federal)."

    def add_arguments(self, parser):
        parser.add_argument("--estabelecimentos", nargs="*", default=[])
        parser.add_argument("--municipios")
        parser.add_argument(
            "--so-razao-social", action="store_true",
            help="Só preenche a razão social das empresas já importadas (lê apenas os arquivos Empresas*)",
        )
        parser.add_argument("--empresas", nargs="*", default=[])
        parser.add_argument("--uf", nargs="*", default=[])
        parser.add_argument("--cnaes", nargs="*", default=[], help="Padrão: CNAEs das categorias ativas")

    def handle(self, *args, **opts):
        # Expande curingas aqui também: o PowerShell/cmd não expande "Estabelecimentos*.zip".
        for key in ("estabelecimentos", "empresas"):
            opts[key] = [f for pattern in opts[key] for f in (sorted(glob.glob(pattern)) or [pattern])]
        if opts["so_razao_social"]:
            if not opts["empresas"]:
                raise CommandError("Informe os arquivos com --empresas.")
            basics = set(
                CnpjEstablishment.objects.filter(razao_social="").values_list("cnpj", flat=True).iterator()
            )
            self._load_company_names(opts["empresas"], {c[:8] for c in basics})
            return
        if not opts["estabelecimentos"] or not opts["municipios"]:
            raise CommandError("Informe --estabelecimentos e --municipios.")
        cnaes = {only_digits(c)[:7] for c in (opts["cnaes"] or self._category_cnaes())}
        if not cnaes:
            raise CommandError("Nenhum CNAE informado nem cadastrado nas categorias.")
        ufs = {u.upper() for u in opts["uf"]}

        ibge = {(normalize(m.nome), m.uf): m.codigo_ibge for m in Municipality.objects.all()}
        if not ibge:
            raise CommandError("Carregue os municípios antes: python manage.py load_ibge")
        # A Receita usa códigos próprios de município: casamos pelo nome + UF (a UF vem no estabelecimento).
        rf_city_names = {row[0]: row[1] for row in open_rows(opts["municipios"]) if len(row) >= 2}
        self.stdout.write(f"CNAEs: {', '.join(sorted(cnaes))}; UFs: {', '.join(sorted(ufs)) or 'todas'}")

        batch, basics, total = [], set(), 0
        for path in opts["estabelecimentos"]:
            self.stdout.write(f"Lendo {path}...")
            for row in open_rows(path):
                if len(row) < 28 or row[5] != ACTIVE:
                    continue
                uf = row[19]
                if ufs and uf not in ufs:
                    continue
                secondary = row[12] or ""
                if row[11] not in cnaes and not any(c in secondary for c in cnaes):
                    continue
                city_name = rf_city_names.get(row[20], "")
                phone = f"{row[21]}{row[22]}".strip() if row[22] else ""
                batch.append(CnpjEstablishment(
                    cnpj=f"{row[0]}{row[1]}{row[2]}",
                    nome_fantasia=row[4].strip().title()[:200],
                    cnae_principal=row[11],
                    cnaes_secundarios=secondary,
                    municipality_id=ibge.get((normalize(city_name), uf)),
                    uf=uf,
                    bairro=row[17].strip().title()[:80],
                    endereco=" ".join(p for p in (row[13], row[14], row[15], row[16]) if p).strip().title()[:255],
                    cep=row[18][:8],
                    telefone=only_digits(phone)[:20],
                    dominio_email=email_domain(row[27])[:255],
                    inicio_atividade=_date(row[10]),
                ))
                basics.add(row[0])
                if len(batch) >= BATCH:
                    total += self._flush(batch)
        total += self._flush(batch)

        if opts["empresas"]:
            self._load_company_names(opts["empresas"], basics)
        self.stdout.write(self.style.SUCCESS(f"{total} estabelecimentos importados."))

    def _category_cnaes(self):
        return [c for cat in Category.objects.filter(ativo=True) for c in cat.cnaes]

    def _flush(self, batch):
        if not batch:
            return 0
        n = len(batch)
        CnpjEstablishment.objects.bulk_create(
            batch, update_conflicts=True, unique_fields=["cnpj"],
            update_fields=["nome_fantasia", "cnae_principal", "cnaes_secundarios", "municipality", "uf", "bairro",
                           "endereco", "cep", "telefone", "dominio_email"],
        )
        batch.clear()
        return n

    def _load_company_names(self, paths, basics):
        names = {}
        for path in paths:
            self.stdout.write(f"Lendo razão social em {path}...")
            for row in open_rows(path):
                if row and row[0] in basics:
                    names[row[0]] = row[1].strip().title()[:200]
        # Grava em lotes, cada um numa transação curta: rápido e sem segurar o banco por muito tempo.
        pending = []
        updated = 0
        for est in CnpjEstablishment.objects.only("cnpj", "razao_social").iterator(chunk_size=5000):
            name = names.get(est.cnpj[:8])
            if name and est.razao_social != name:
                est.razao_social = name
                pending.append(est)
            if len(pending) >= BATCH:
                updated += self._save_names(pending)
        updated += self._save_names(pending)
        self.stdout.write(self.style.SUCCESS(f"Razão social preenchida em {updated} estabelecimentos."))

    def _save_names(self, pending):
        n = len(pending)
        if n:
            with transaction.atomic():
                CnpjEstablishment.objects.bulk_update(pending, ["razao_social"], batch_size=500)
            pending.clear()
        return n


def _date(value):
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError):
        return None
