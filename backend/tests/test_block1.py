"""Auditoria manual (site bloqueado), metas do PRD no painel, edição de achados e briefing em PDF."""
import io
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image

from apps.audits.models import STEPS, Audit, AuditStep, Finding
from apps.leads.models import Company, LeadStatus, Website
from apps.reports.models import Report


def png(w=1440, h=900):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return SimpleUploadedFile("captura.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def blocked_audit(city, category):
    company = Company.objects.create(nome="Clínica Bloqueada", municipality=city, category=category)
    site = Website.objects.create(company=company, url="https://bloqueado.com.br", auditavel=False)
    audit = Audit.objects.create(website=site, status=Audit.Status.FAILED, erro="O site bloqueou o robô",
                                 concluido_em=timezone.now())
    AuditStep.objects.bulk_create([AuditStep(audit=audit, etapa=k, ordem=o, status="nao_medido") for o, k, _ in STEPS])
    return audit


@pytest.mark.django_db
def test_manual_audit_flow_until_public_report(api, blocked_audit):
    r = api.post(f"/api/audits/{blocked_audit.pk}/upload_capture", {"tipo": "desktop", "arquivo": png()},
                 format="multipart")
    assert r.status_code == 201 and r.data["meta"]["largura"] == 1440 and r.data["meta"]["manual"]
    r = api.post(f"/api/audits/{blocked_audit.pk}/upload_capture", {"tipo": "desktop", "arquivo": png(1280, 800)},
                 format="multipart")
    assert blocked_audit.artifacts.count() == 1  # substitui a captura do mesmo tipo

    bad = SimpleUploadedFile("x.png", b"isto nao e imagem", content_type="image/png")
    assert api.post(f"/api/audits/{blocked_audit.pk}/upload_capture", {"tipo": "desktop", "arquivo": bad},
                    format="multipart").status_code == 400
    assert api.post(f"/api/audits/{blocked_audit.pk}/upload_capture", {"tipo": "tablet", "arquivo": png()},
                    format="multipart").status_code == 400

    r = api.post(f"/api/audits/{blocked_audit.pk}/finish_manual")
    assert r.status_code == 200 and r.data["status"] == "concluida" and r.data["metricas"]["manual"]
    assert api.post(f"/api/audits/{blocked_audit.pk}/finish_manual").status_code == 400
    company = blocked_audit.website.company
    company.refresh_from_db()
    assert company.status_lead == LeadStatus.AUDITED

    r = api.post("/api/findings", {"audit": blocked_audit.pk, "dimensao": "conversao", "severidade": "alta",
                                   "titulo": "Sem botão de WhatsApp", "impacto_negocio": "Perde contatos",
                                   "melhoria_proposta": "Botão fixo"}, format="json")
    assert r.status_code == 201
    with mock.patch("apps.reports.views.enqueue"):
        r = api.post("/api/reports", {"audit": blocked_audit.pk}, format="json")
    assert r.status_code == 201
    html = Client().get(f"/r/{r.data['token']}").content.decode()
    assert "Sem botão de WhatsApp" in html and "None/100" not in html
    assert "encontramos pontos que afastam clientes" in html


@pytest.mark.django_db
def test_rewritten_ai_findings_are_tracked_and_goals_reported(api, blocked_audit):
    audit = blocked_audit
    a = Finding.objects.create(audit=audit, dimensao="conteudo", severidade="media", origem="ia", titulo="Visual datado")
    b = Finding.objects.create(audit=audit, dimensao="conteudo", severidade="media", origem="ia", titulo="Sem fotos")
    api.patch(f"/api/findings/{a.pk}", {"status_revisao": "confirmado"}, format="json")
    api.patch(f"/api/findings/{b.pk}", {"status_revisao": "confirmado", "titulo": "Faltam fotos reais"}, format="json")
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.texto_editado is False and b.texto_editado is True

    goals = {g["chave"]: g for g in api.get("/api/dashboard").data["metas"]}
    assert goals["ia"]["valor"] == "50%" and goals["ia"]["ok"] is False


@pytest.mark.django_db
def test_briefing_pdf(api, blocked_audit):
    company = blocked_audit.website.company
    briefing_id = api.post("/api/briefings", {"company": company.pk}, format="json").data["id"]
    with mock.patch("apps.reports.services.html_to_pdf", return_value=b"%PDF-1.7") as conv:
        r = api.get(f"/api/briefings/{briefing_id}/pdf")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf" and r.content == b"%PDF-1.7"
    html = conv.call_args.args[0]
    assert "Briefing do site novo" in html and "Clínica Bloqueada" in html and "Metas de qualidade" in html


@pytest.mark.django_db
def test_report_without_score_is_still_available(blocked_audit):
    blocked_audit.status = Audit.Status.DONE
    blocked_audit.save()
    report = Report.objects.create(audit=blocked_audit)
    assert Client().get(f"/r/{report.token}").status_code == 200


@pytest.mark.django_db
def test_stale_running_audits_are_marked_interrupted(api, blocked_audit, settings):
    from datetime import timedelta

    from apps.core.jobs import reap_stale_jobs

    blocked_audit.status = Audit.Status.RUNNING
    blocked_audit.iniciado_em = timezone.now() - timedelta(seconds=settings.AUDIT_TIMEOUT + 400)
    blocked_audit.save()
    fresh = Audit.objects.create(website=blocked_audit.website, status=Audit.Status.RUNNING, iniciado_em=timezone.now())
    assert reap_stale_jobs() == [blocked_audit.pk]
    blocked_audit.refresh_from_db()
    fresh.refresh_from_db()
    assert blocked_audit.status == Audit.Status.FAILED and "interrompida" in blocked_audit.erro
    assert fresh.status == Audit.Status.RUNNING
    assert api.get(f"/api/audits/{blocked_audit.pk}").data["status"] == "falhou"
