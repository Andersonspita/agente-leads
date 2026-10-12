from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.audits.models import STEPS, Audit, AuditStep, Finding
from apps.core.models import ActivityLog
from apps.leads.models import Company, LeadStatus, Website
from apps.reports.models import Report, ReportView


def current_token(device):
    return f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"


@pytest.fixture
def audited(city, category):
    company = Company.objects.create(nome="Clínica Sorriso", municipality=city, category=category)
    website = Website.objects.create(company=company, url="https://clinicasorriso.com.br")
    audit = Audit.objects.create(website=website, status=Audit.Status.DONE, nota_geral=42,
                                 concluido_em=timezone.now(), notas_dimensao={"desempenho": 30, "seo": 55})
    AuditStep.objects.bulk_create([AuditStep(audit=audit, etapa=k, ordem=o, status="ok") for o, k, _ in STEPS])
    Finding.objects.create(audit=audit, dimensao="seguranca", severidade="critica", titulo="Site sem HTTPS",
                           impacto_negocio="Aviso de não seguro", melhoria_proposta="SSL",
                           status_revisao=Finding.Review.CONFIRMED)
    ai = Finding.objects.create(audit=audit, dimensao="conteudo", severidade="media", origem="ia",
                                titulo="Design datado", impacto_negocio="Menos confiança",
                                melhoria_proposta="Layout moderno")
    return audit, ai


# ------------------------------------------------------------------ autenticação e 2FA

@pytest.mark.django_db
def test_login_requires_totp_and_locks_after_5_failures(settings, analyst):
    settings.REQUIRE_2FA = True
    client = APIClient()

    r = client.post("/api/auth/login", {"email": analyst.email, "password": "senha-muito-forte-1"}, format="json")
    assert r.status_code == 200 and r.data["setup_required"] and not r.data["verified"]
    assert client.get("/api/dashboard").status_code == 403  # sem 2FA não acessa

    r = client.post("/api/auth/2fa/setup")
    assert r.status_code == 200 and r.data["otpauth_uri"].startswith("otpauth://totp/")
    device = TOTPDevice.objects.get(user=analyst)
    r = client.post("/api/auth/2fa/confirm", {"otp": current_token(device)}, format="json")
    assert r.status_code == 200 and r.data["verified"]
    assert client.get("/api/dashboard").status_code == 200

    other = APIClient()
    r = other.post("/api/auth/login", {"email": analyst.email, "password": "senha-muito-forte-1"}, format="json")
    assert r.data == {"otp_required": True}
    for _ in range(5):
        other.post("/api/auth/login", {"email": analyst.email, "password": "errada"}, format="json")
    r = other.post("/api/auth/login", {"email": analyst.email, "password": "senha-muito-forte-1",
                                       "otp": current_token(device)}, format="json")
    assert r.status_code == 423


@pytest.mark.django_db
def test_anonymous_cannot_use_api():
    assert APIClient().get("/api/companies").status_code == 403


# ------------------------------------------------------------------ leads

@pytest.mark.django_db
def test_manual_company_with_url_and_lead_transitions(api, city, category):
    with mock.patch("apps.leads.views.enqueue_enrich"):
        r = api.post("/api/companies", {"nome": "Odonto Mais", "municipality": city.pk, "category": category.pk,
                                        "url": "https://odontomais.com.br"}, format="json")
    assert r.status_code == 201
    cid = r.data["id"]
    assert r.data["websites"][0]["dominio"] == "odontomais.com.br"

    with mock.patch("apps.leads.views.enqueue_enrich"):
        dup = api.post("/api/companies", {"nome": "Outra", "url": "http://www.odontomais.com.br/"}, format="json")
    assert dup.status_code == 409

    assert api.patch(f"/api/companies/{cid}", {"status_lead": "fechado"}, format="json").status_code == 400
    r = api.patch(f"/api/companies/{cid}", {"status_lead": "auditado"}, format="json")
    assert r.status_code == 200 and r.data["status_lead"] == "auditado"
    assert ActivityLog.objects.filter(acao="status_lead").exists()


@pytest.mark.django_db
def test_company_filters_and_csv_export(api, city, category):
    with_site = Company.objects.create(nome="Com Site", municipality=city, category=category)
    Website.objects.create(company=with_site, url="https://comsite.com.br", online=True)
    Company.objects.create(nome="Sem Site", municipality=city, category=category)
    names = lambda r: {c["nome"] for c in r.data["results"]}  # noqa: E731
    assert names(api.get("/api/companies?site=sem_site")) == {"Sem Site"}
    assert names(api.get("/api/companies?site=tem_site")) == {"Com Site"}
    r = api.get("/api/companies/export")
    assert r.status_code == 200 and "Com Site" in r.content.decode("utf-8")


@pytest.mark.django_db
def test_search_is_created_and_dispatched(api, city, category):
    with mock.patch("apps.leads.views.enqueue") as enqueue:
        r = api.post("/api/searches", {"category": category.pk, "municipality": city.pk}, format="json")
    assert r.status_code == 201
    enqueue.assert_called_once()
    assert api.post("/api/searches", {"municipality": city.pk}, format="json").status_code == 400


@pytest.mark.django_db
def test_search_without_places_key_uses_cnpj_base_and_marks_no_site(city, category):
    from apps.leads.models import CnpjEstablishment, Search
    from apps.leads.services import run_search

    CnpjEstablishment.objects.create(cnpj="11222333000144", nome_fantasia="Odonto Centro", cnae_principal="8630504",
                                     municipality=city, uf="BA", telefone="7734001234")
    search = Search.objects.create(category=category, municipality=city)
    run_search(search)
    assert search.status == Search.Status.DONE and search.total_encontrado == 1
    assert search.fontes["erros"] == []
    assert any("Google Places" in a for a in search.fontes["avisos"])
    assert Company.objects.get().status_lead == LeadStatus.NO_SITE


# ------------------------------------------------------------------ auditorias e revisão

@pytest.mark.django_db
def test_batch_audit_skips_companies_without_site(api, city):
    a = Company.objects.create(nome="A", municipality=city)
    site = Website.objects.create(company=a, url="https://a.com.br")
    b = Company.objects.create(nome="B", municipality=city)
    with mock.patch("apps.audits.views.enqueue") as enqueue:
        r = api.post("/api/audits", {"company_ids": [a.pk, b.pk]}, format="json")
    assert r.status_code == 202 and r.data["total"] == 1
    audit = Audit.objects.get(website=site)
    assert audit.steps.count() == 9
    enqueue.assert_called_once()
    with mock.patch("apps.audits.views.enqueue"):
        again = api.post("/api/audits", {"website_ids": [site.pk]}, format="json")
    assert again.data["audit_ids"] == [audit.pk]  # não duplica auditoria em andamento


@pytest.mark.django_db
def test_finding_review_and_report_gate(api, audited):
    audit, ai = audited
    assert api.get(f"/api/findings/{ai.pk}").data["editado_por_nome"] is None  # não vaza "<method-wrapper ...>"
    r = api.post("/api/reports", {"audit": audit.pk}, format="json")
    assert r.status_code == 400  # achado de IA pendente bloqueia o relatório

    r = api.patch(f"/api/findings/{ai.pk}", {"status_revisao": "confirmado", "titulo": "Visual desatualizado"},
                  format="json")
    assert r.status_code == 200 and r.data["editado_por_nome"]

    with mock.patch("apps.reports.views.enqueue") as enqueue:
        r = api.post("/api/reports", {"audit": audit.pk, "texto_abertura": "Olá!"}, format="json")
    assert r.status_code == 201
    enqueue.assert_called_once()
    assert len(r.data["token"]) >= 43 and r.data["url_publica"].endswith(r.data["token"])


# ------------------------------------------------------------------ relatório público

@pytest.mark.django_db
def test_public_report_tracks_views_and_respects_revocation(api, audited):
    audit, ai = audited
    ai.status_revisao = Finding.Review.DISCARDED
    ai.save()
    report = Report.objects.create(audit=audit)
    anon = APIClient()

    anon.get(f"/r/{report.token}", HTTP_USER_AGENT="WhatsApp/2.23.20.0")  # prévia do link: não conta
    anon.get(f"/r/{report.token}", HTTP_USER_AGENT="facebookexternalhit/1.1")
    assert ReportView.objects.count() == 0
    phone = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36"
    r = anon.get(f"/r/{report.token}", HTTP_USER_AGENT=phone)
    html = r.content.decode()
    assert r.status_code == 200
    assert "Clínica Sorriso" in html and "Site sem HTTPS" in html and "Design datado" not in html
    assert r["X-Robots-Tag"] == "noindex, nofollow"
    view = ReportView.objects.get()
    assert view.user_agent == phone and len(view.ip_hash) == 64 and "127.0.0.1" not in view.ip_hash

    with mock.patch("apps.reports.views.enqueue"):
        api.post(f"/api/reports/{report.pk}/revoke")
    assert anon.get(f"/r/{report.token}").status_code == 404

    expired = Report.objects.create(audit=audit, expira_em=timezone.now() - timedelta(days=1))
    assert anon.get(f"/r/{expired.token}").status_code == 404
    assert anon.get("/r/token-inexistente").status_code == 404


@pytest.mark.django_db
def test_mark_sent_moves_lead_forward(api, audited):
    audit, _ = audited
    company = audit.website.company
    company.status_lead = LeadStatus.AUDITED
    company.save()
    report = Report.objects.create(audit=audit)
    r = api.post(f"/api/reports/{report.pk}/mark_sent", {"canal": "whatsapp"}, format="json")
    assert r.status_code == 200 and r.data["enviado_em"]
    company.refresh_from_db()
    assert company.status_lead == LeadStatus.REPORT_SENT


# ------------------------------------------------------------------ briefing e configurações

@pytest.mark.django_db
def test_briefing_maps_findings_to_requirements(api, audited):
    audit, _ = audited
    company = audit.website.company
    r = api.post("/api/briefings", {"company": company.pk}, format="json")
    assert r.status_code == 201
    content = r.data["conteudo"]
    assert content["nota_atual"] == 42
    assert any(req["problema"] == "Site sem HTTPS" for req in content["requisitos"])
    assert "Agendamento online" in content["integracoes"]
    md = api.get(f"/api/briefings/{r.data['id']}/markdown")
    assert md.status_code == 200 and "# Briefing do site novo" in md.content.decode()
    second = api.post("/api/briefings", {"company": company.pk}, format="json")
    assert second.data["versao"] == 2


@pytest.mark.django_db
def test_only_admin_changes_weights(api, admin_api, category):
    weights = {"desempenho": 0.2, "mobile": 0.2, "seo": 0.1, "acessibilidade": 0.1, "seguranca": 0.1,
               "conteudo": 0.1, "conversao": 0.1, "conformidade": 0.1}
    assert api.put(f"/api/categories/{category.pk}/weights", weights, format="json").status_code == 403
    assert admin_api.put(f"/api/categories/{category.pk}/weights", {**weights, "seo": 0.3},
                         format="json").status_code == 400
    r = admin_api.put(f"/api/categories/{category.pk}/weights", weights, format="json")
    assert r.status_code == 200 and r.data["pesos"]["desempenho"] == 0.2


@pytest.mark.django_db
def test_dashboard(api, audited):
    r = api.get("/api/dashboard")
    assert r.status_code == 200
    assert {row["status"] for row in r.data["funil"]} >= {"encontrado", "fechado"}
    assert r.data["revisao_pendente"] == 1


def test_admin_site_requires_otp_when_2fa_is_on(settings):
    import importlib

    from django.contrib import admin
    from django_otp.admin import OTPAdminSite

    import config.urls

    original = admin.site.__class__
    settings.REQUIRE_2FA = True
    try:
        importlib.reload(config.urls)
        assert isinstance(admin.site, OTPAdminSite)
    finally:
        admin.site.__class__ = original
        settings.REQUIRE_2FA = False
        importlib.reload(config.urls)
