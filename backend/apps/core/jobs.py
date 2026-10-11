"""Despacho de jobs assíncronos.

Com Redis configurado, os jobs vão para as filas do Celery. Sem Redis (modo local),
rodam num pool de threads do próprio processo web, respeitando o mesmo limite de
paralelismo — suficiente para 2 usuários em desenvolvimento.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction

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
