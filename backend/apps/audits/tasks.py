import logging

from celery import shared_task

from .models import Audit, AuditStep

logger = logging.getLogger(__name__)


@shared_task(bind=True, acks_late=True, max_retries=1)
def run_audit(self, audit_id):
    from .engine.runner import AuditRunner

    audit = Audit.objects.select_related("website__company__category", "website__company__municipality").get(
        pk=audit_id
    )
    if audit.status == Audit.Status.DONE:
        return audit_id  # imutável após conclusão
    AuditRunner(audit).run()
    return audit_id


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def ai_analysis(self, audit_id):
    """Reexecuta só a etapa de IA (ex.: depois de configurar a chave ou trocar o prompt)."""
    from .engine.runner import StepSkipped, run_ai_analysis

    audit = Audit.objects.select_related("website__company").get(pk=audit_id)
    step, _ = AuditStep.objects.get_or_create(audit=audit, etapa="ia", defaults={"ordem": 8})
    step.status = AuditStep.Status.RUNNING
    step.erro = ""
    step.save()
    try:
        run_ai_analysis(audit, None, step)
        step.status = AuditStep.Status.DONE
    except StepSkipped as exc:
        step.status = AuditStep.Status.SKIPPED
        step.erro = str(exc)
    except Exception as exc:
        logger.exception("ai_analysis falhou")
        step.status = AuditStep.Status.FAILED
        step.erro = str(exc)[:500]
    step.save()
    return audit_id
