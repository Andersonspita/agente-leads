import logging

from celery import shared_task
from django.db import transaction

from .models import SiteProject

logger = logging.getLogger(__name__)


@shared_task
def write_site_copy(project_id):
    """Reescreve os textos do site gerado com a IA (pode levar minutos no plano gratuito)."""
    from .content import ai_copy, merge_ai_copy

    project = SiteProject.objects.select_related("company__municipality", "company__category", "audit_origem").get(
        pk=project_id)
    try:
        copy, model = ai_copy(project.company, project.audit_origem)
    except Exception as exc:  # IA fora do ar, limite gratuito etc.: o site fica com os textos-base
        logger.warning("IA indisponível para os textos do site %s: %r", project_id, exc)
        SiteProject.objects.filter(pk=project_id).update(ia_status="falhou")
        return
    with transaction.atomic():  # trava a linha: uma edição do analista no meio não se perde
        project = SiteProject.objects.select_for_update().get(pk=project_id)
        project.conteudo = merge_ai_copy(project.conteudo, project.company, copy)
        project.gerado_por_ia, project.modelo_ia, project.ia_status = True, model, "ok"
        project.save()
