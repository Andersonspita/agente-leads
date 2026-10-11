import logging
import secrets

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import Report

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=20)
def render_report_pdf(self, report_id):
    from .services import render_pdf

    report = Report.objects.select_related("audit__website__company").get(pk=report_id)
    report.pdf_status = "gerando"
    report.save(update_fields=["pdf_status"])
    try:
        pdf = render_pdf(report)
    except Exception:
        logger.exception("Falha ao gerar PDF do relatório %s", report_id)
        report.pdf_status = "falhou"
        report.save(update_fields=["pdf_status"])
        raise
    if report.pdf:
        report.pdf.delete(save=False)
    slug = report.company.nome_normalizado.replace(" ", "-")[:40] or "empresa"
    report.pdf.save(f"diagnostico-{slug}-{secrets.token_hex(8)}.pdf", ContentFile(pdf), save=False)
    report.pdf_status = "pronto"
    report.save(update_fields=["pdf", "pdf_status"])
    return report_id


@shared_task
def expire_reports():
    """Diário: revoga links vencidos (a página já respeita expira_em; isto limpa o estado)."""
    return Report.objects.filter(expira_em__lt=timezone.now(), revogado=False).update(revogado=True)
