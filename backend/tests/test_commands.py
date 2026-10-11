import json
import zipfile
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import Client

from apps.catalog.models import Category, Rule
from apps.geo.models import Municipality
from apps.leads.models import CnpjEstablishment


@pytest.mark.django_db
def test_load_ibge_from_file(tmp_path):
    data = [{"municipio-id": 2933307, "municipio-nome": "Vitória da Conquista", "UF-sigla": "BA"},
            {"municipio-id": 3550308, "municipio-nome": "São Paulo", "UF-sigla": "SP"}]
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    call_command("load_ibge", file=str(path))
    city = Municipality.objects.get(pk="2933307")
    assert city.nome_normalizado == "vitoria da conquista"


@pytest.mark.django_db
def test_seed_categories_is_idempotent_and_weights_sum_to_one():
    call_command("seed_categories")
    call_command("seed_categories")
    assert Category.objects.count() >= 8
    for cat in Category.objects.all():
        assert abs(sum(cat.weights().values()) - 1) < 0.001, cat.nome
    assert Rule.objects.filter(codigo="SEC-001").exists()


def _zip(path, name, rows):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, "\n".join(";".join(f'"{c}"' for c in r) for r in rows).encode("latin-1"))
    return str(path)


@pytest.mark.django_db
def test_import_cnpj_filters_active_cnae_and_uf(tmp_path, city, category):
    municipios = _zip(tmp_path / "Municipios.zip", "MUNIC.CSV", [["3965", "VITORIA DA CONQUISTA"]])

    def est(basico, situacao, cnae, uf, fantasia):
        row = [""] * 30
        row[0], row[1], row[2], row[4], row[5] = basico, "0001", "99", fantasia, situacao
        row[10], row[11], row[12] = "20150301", cnae, ""
        row[13], row[14], row[15], row[17], row[18], row[19], row[20] = "RUA", "SIQUEIRA", "10", "CENTRO", "45000000", uf, "3965"
        row[21], row[22], row[27] = "77", "34221100", "dono@gmail.com"
        return row

    estab = _zip(tmp_path / "Estabelecimentos0.zip", "ESTABELE.CSV", [
        est("11111111", "02", "8630504", "BA", "ODONTO SORRISO"),
        est("22222222", "08", "8630504", "BA", "BAIXADA"),        # inativa
        est("33333333", "02", "4711302", "BA", "MERCADO"),        # outro CNAE
        est("44444444", "02", "8630504", "SP", "OUTRA UF"),
    ])
    empresas = _zip(tmp_path / "Empresas0.zip", "EMPRECSV", [["11111111", "ODONTO SORRISO LTDA", "2062"]])
    call_command("import_cnpj", municipios=municipios, estabelecimentos=[estab], empresas=[empresas], uf=["BA"])

    est = CnpjEstablishment.objects.get()
    assert est.cnpj == "11111111000199" and est.nome_fantasia == "Odonto Sorriso"
    assert est.razao_social == "Odonto Sorriso Ltda"
    assert est.municipality_id == city.pk and est.telefone == "7734221100"
    assert not hasattr(est, "email")  # o e-mail em si nunca é importado (LGPD)
    assert est.dominio_email == ""  # provedor gratuito (gmail) não vira candidato a site


@pytest.mark.django_db
def test_create_operator_and_public_pages():
    call_command("create_operator", "ana@example.com", role="admin", password="senha-muito-forte-1", nome="Ana Souza")
    from apps.accounts.models import User

    user = User.objects.get(email="ana@example.com")
    assert user.is_admin and user.first_name == "Ana"
    client = Client()
    assert client.get("/robots.txt").content == b"User-agent: *\nDisallow: /\n"
    assert "Política de privacidade" in client.get("/privacidade").content.decode()
    assert "Exclusão de dados" in client.get("/exclusao-de-dados").content.decode()


@pytest.mark.django_db
def test_report_pdf_task_and_expiry(city):
    from datetime import timedelta

    from django.utils import timezone

    from apps.audits.models import Audit
    from apps.leads.models import Company, Website
    from apps.reports.models import Report
    from apps.reports.tasks import expire_reports, render_report_pdf

    company = Company.objects.create(nome="Clínica", municipality=city)
    audit = Audit.objects.create(website=Website.objects.create(company=company, url="https://c.com.br"),
                                 status="concluida", nota_geral=50)
    report = Report.objects.create(audit=audit)
    with mock.patch("apps.reports.services.render_pdf", return_value=b"%PDF-1.7 teste"):
        render_report_pdf.run(report.pk)
    report.refresh_from_db()
    assert report.pdf_status == "pronto" and report.pdf.read() == b"%PDF-1.7 teste"

    Report.objects.create(audit=audit, expira_em=timezone.now() - timedelta(days=1))
    assert expire_reports() == 1


@pytest.mark.django_db
def test_purge_old_artifacts(city, settings):
    from datetime import timedelta

    from django.core.files.base import ContentFile
    from django.utils import timezone

    from apps.audits.models import Artifact, Audit
    from apps.core.tasks import purge_old_artifacts
    from apps.leads.models import Company, Website

    company = Company.objects.create(nome="Clínica", municipality=city)
    audit = Audit.objects.create(website=Website.objects.create(company=company, url="https://c.com.br"))
    old = Artifact(audit=audit, tipo="screenshot_desktop")
    old.arquivo.save("a.png", ContentFile(b"x"))
    Artifact.objects.filter(pk=old.pk).update(criado_em=timezone.now() - timedelta(days=400))
    new = Artifact(audit=audit, tipo="screenshot_mobile")
    new.arquivo.save("b.png", ContentFile(b"y"))
    assert purge_old_artifacts() == 1
    assert list(Artifact.objects.values_list("pk", flat=True)) == [new.pk]
