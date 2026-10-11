"""Despacho de jobs assíncronos.

Com Redis configurado, os jobs vão para as filas do Celery. Sem Redis (modo local),
rodam num pool de threads do próprio processo web, respeitando o mesmo limite de
paralelismo — suficiente para 2 usuários em desenvolvimento.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Q

logger = logging.getLogger(__name__)
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=settings.AUDIT_PARALLELISM, thread_name_prefix="job")
    return _pool


def _run_local(task, args, kwargs):
    close_old_connections()
    try:
        task.run(*args, **kwargs)
    except Exception:
        logger.exception("Falha no job local %s", task.name)
    finally:
        close_old_connections()


def enqueue(task, *args, **kwargs):
    """Enfileira `task` depois do commit da transação atual."""

    def dispatch():
        if settings.CELERY_BROKER_URL:
            task.delay(*args, **kwargs)
        else:
            _get_pool().submit(_run_local, task, args, kwargs)

    transaction.on_commit(dispatch)


def reap_stale_jobs():
    """Marca como interrompidas as auditorias e buscas que ficaram "em andamento" além do limite.

    Acontece quando o processo que rodava o job cai ou é reiniciado (no modo local os jobs rodam
    em threads do servidor web). Sem isso, a auditoria ficaria "executando" para sempre.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.audits.models import Audit, AuditStep
    from apps.leads.models import Search

    now = timezone.now()
    audit_limit = now - timedelta(seconds=settings.AUDIT_TIMEOUT + 300)
    stale = Audit.objects.filter(status__in=[Audit.Status.QUEUED, Audit.Status.RUNNING]).filter(
        Q(iniciado_em__lt=audit_limit) | Q(iniciado_em__isnull=True, criado_em__lt=audit_limit)
    )
    ids = list(stale.values_list("pk", flat=True))
    if ids:
        AuditStep.objects.filter(audit_id__in=ids, status__in=[AuditStep.Status.PENDING, AuditStep.Status.RUNNING]).update(
            status=AuditStep.Status.SKIPPED, erro="Auditoria interrompida")
        Audit.objects.filter(pk__in=ids).update(
            status=Audit.Status.FAILED, concluido_em=now,
            erro="Auditoria interrompida (o servidor foi reiniciado ou o processo caiu). Use “Tentar de novo”.")
        logger.warning("Auditorias interrompidas marcadas como falhas: %s", ids)
    Search.objects.filter(status__in=[Search.Status.QUEUED, Search.Status.RUNNING],
                          criado_em__lt=now - timedelta(minutes=30)).update(
        status=Search.Status.FAILED, erro="Busca interrompida (servidor reiniciado). Faça a busca de novo.")
    return ids

