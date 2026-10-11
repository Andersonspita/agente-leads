import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def purge_old_artifacts():
    """Apaga capturas e JSONs com mais de 12 meses (retenção LGPD)."""
    from apps.audits.models import Artifact

    cutoff = timezone.now() - timedelta(days=settings.ARTIFACT_RETENTION_DAYS)
    old = Artifact.objects.filter(criado_em__lt=cutoff)
    count = 0
    for artifact in old.iterator():
        artifact.arquivo.delete(save=False)
        artifact.delete()
        count += 1
    logger.info("purge_old_artifacts removeu %s arquivos", count)
    return count
