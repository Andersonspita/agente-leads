from .models import ActivityLog


def log_activity(user, acao, obj=None, **dados):
    entidade = obj._meta.model_name if obj is not None else ""
    entidade_id = str(obj.pk) if obj is not None else ""
    ActivityLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        dados=dados,
    )
