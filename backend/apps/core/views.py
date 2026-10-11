from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin, IsAdminOrReadOnly
from apps.audits.models import Audit, Finding
from apps.leads.models import Company, LeadStatus
from apps.reports.models import Report, ReportView

from .costs import month_spend
from .models import ActivityLog, ApiUsage, BrandSettings, PromptVersion


@api_view(["GET"])
def dashboard(request):
    """GET /api/dashboard — funil, auditorias da semana e custo de APIs."""
    now = timezone.now()
    week = now - timedelta(days=7)
    funnel = dict(Company.objects.order_by().values_list("status_lead").annotate(n=Count("id")))
    running = Audit.objects.filter(status__in=[Audit.Status.QUEUED, Audit.Status.RUNNING]).select_related(
        "website__company")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    by_provider = (
        ApiUsage.objects.filter(data__gte=month_start).values("provedor")
        .annotate(total=Sum("custo_estimado"), chamadas=Count("id"))
    )
    spent = month_spend()
    budget = Decimal(str(settings.MONTHLY_API_BUDGET_BRL))
    return Response({
        "funil": [{"status": s.value, "nome": s.label, "total": funnel.get(s.value, 0)} for s in LeadStatus],
        "auditorias_em_andamento": [
            {"id": a.pk, "empresa": a.website.company.nome, "status": a.status, "criado_em": a.criado_em}
            for a in running[:20]
        ],
        "semana": {
            "auditorias": Audit.objects.filter(concluido_em__gte=week, status=Audit.Status.DONE).count(),
            "relatorios_enviados": Report.objects.filter(enviado_em__gte=week).count(),
            "relatorios_abertos": ReportView.objects.filter(visto_em__gte=week).values("report").distinct().count(),
            "leads_novos": Company.objects.filter(criado_em__gte=week).count(),
        },
        "revisao_pendente": Finding.objects.filter(status_revisao=Finding.Review.PENDING).values("audit")
        .distinct().count(),
        "custos": {
            "gasto_mes": float(spent), "teto_mes": float(budget),
            "percentual": round(float(spent / budget * 100), 1) if budget else 0,
            "alerta": bool(budget and spent >= budget * Decimal("0.8")),
            "por_provedor": [{"provedor": p["provedor"], "total": float(p["total"] or 0), "chamadas": p["chamadas"]}
                             for p in by_provider],
        },
        "atividade": [
            {"acao": a.acao, "entidade": a.entidade, "entidade_id": a.entidade_id, "usuario": str(a.user or ""),
             "quando": a.criado_em}
            for a in ActivityLog.objects.select_related("user")[:15]
        ],
    })


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandSettings
        fields = ["nome_empresa", "cor_primaria", "logo", "whatsapp", "link_agenda", "email_contato", "site",
                  "exibir_nomes_concorrentes"]

    def validate_cor_primaria(self, value):
        import re

        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Use o formato #RRGGBB.")
        return value


@api_view(["GET", "PATCH"])
@permission_classes([IsAdminOrReadOnly])
def brand(request):
    obj = BrandSettings.get()
    if request.method == "PATCH":
        ser = BrandSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
    return Response(BrandSerializer(obj).data)


class PromptVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptVersion
        fields = ["id", "nome", "texto", "modelo", "ativo", "criado_em"]


class PromptVersionViewSet(viewsets.ModelViewSet):
    """Prompts versionados: cada edição cria uma nova versão (TRD 2.5)."""

    queryset = PromptVersion.objects.all()
    serializer_class = PromptVersionSerializer
    permission_classes = [IsAdmin]
    pagination_class = None
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return super().get_queryset().order_by("-criado_em")


@api_view(["GET"])
@permission_classes([IsAdmin])
def api_usage(request):
    since = timezone.now() - timedelta(days=int(request.query_params.get("dias", 30)))
    rows = ApiUsage.objects.filter(data__gte=since)[:500]
    return Response([
        {"provedor": r.provedor, "endpoint": r.endpoint, "custo": float(r.custo_estimado), "data": r.data,
         "detalhes": r.detalhes}
        for r in rows
    ])


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"ok": True, "hora": timezone.now()})


@api_view(["GET"])
def capabilities(request):
    """Diz ao painel quais integrações estão ativas (para explicar etapas 'não medidas')."""
    from apps.audits.engine import ai
    from apps.audits.engine.browser import AXE_PATH, browser_available
    from apps.audits.engine.lighthouse import lighthouse_command
    from apps.leads.discovery import websearch
    from apps.leads.models import CnpjEstablishment

    return Response({
        "google_places": bool(settings.GOOGLE_PLACES_API_KEY),
        "osm": settings.OSM_ENABLED,
        "email_cnpj": settings.EMAIL_DOMAIN_DISCOVERY,
        "busca_web": websearch.enabled(),
        "ia": ai.is_configured(),
        "modelo_ia": f"{ai.provider()}: {ai.model_name()}" if ai.is_configured() else "",
        "navegador": browser_available(),
        "axe": AXE_PATH.exists(),
        "lighthouse": bool(lighthouse_command()),
        "filas_celery": bool(settings.CELERY_BROKER_URL),
        "base_cnpj": CnpjEstablishment.objects.exists(),
    })
