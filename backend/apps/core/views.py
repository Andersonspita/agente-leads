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


def _median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def prd_goals() -> list[dict]:
    """Metas de sucesso do PRD 1.2, calculadas com os dados reais do sistema."""
    from apps.audits.models import Audit, Finding
    from apps.sitebuilder.models import SiteProject
    from apps.leads.models import Search

    goals = []

    searches = list(Search.objects.filter(status=Search.Status.DONE, concluido_em__isnull=False)
                    .order_by("-concluido_em")[:20])
    if searches:
        avg_found = sum(s.total_encontrado for s in searches) / len(searches)
        avg_secs = _median([(s.concluido_em - s.criado_em).total_seconds() for s in searches])
        goals.append({"chave": "busca", "nome": "Empresas por busca", "valor": f"{avg_found:.0f} em {avg_secs:.0f} s",
                      "meta": "≥ 50 em até 2 min", "ok": avg_found >= 50 and avg_secs <= 120,
                      "amostra": f"últimas {len(searches)} buscas"})

    audits = list(Audit.objects.filter(status=Audit.Status.DONE, iniciado_em__isnull=False,
                                       concluido_em__isnull=False).order_by("-concluido_em")[:30])
    if audits:
        secs = _median([(a.concluido_em - a.iniciado_em).total_seconds() for a in audits])
        goals.append({"chave": "auditoria", "nome": "Tempo de auditoria (mediana)", "valor": f"{secs / 60:.1f} min",
                      "meta": "≤ 3 min", "ok": secs <= 180, "amostra": f"últimas {len(audits)} auditorias"})

    sent = Company.objects.filter(websites__audits__reports__enviado_em__isnull=False).distinct()
    total_sent = sent.count()
    if total_sent:
        closed = sent.filter(status_lead__in=[LeadStatus.CLOSED, LeadStatus.DELIVERED]).count()
        goals.append({"chave": "propostas", "nome": "Propostas aceitas após o relatório",
                      "valor": f"{closed / total_sent * 100:.0f}% ({closed} de {total_sent})",
                      "meta": "linha de base no 1º trimestre, depois +20%", "ok": None,
                      "amostra": "leads com relatório enviado"})

    pairs = []
    for project in SiteProject.objects.filter(website__isnull=False).select_related("audit_origem", "website"):
        new = project.website.audits.filter(status=Audit.Status.DONE).order_by("-concluido_em").first()
        if new and new.nota_geral is not None:
            old = project.audit_origem.nota_geral if project.audit_origem else None
            pairs.append((new.nota_geral, old))
    if pairs:
        avg_new = sum(n for n, _ in pairs) / len(pairs)
        gains = [n - o for n, o in pairs if o is not None]
        avg_gain = sum(gains) / len(gains) if gains else None
        valor = f"{avg_new:.0f}/100" + (f" (+{avg_gain:.0f} pontos)" if avg_gain is not None else "")
        goals.append({"chave": "site_novo", "nome": "Nota do site novo vs. antigo", "valor": valor,
                      "meta": "≥ 85 e +30 sobre o antigo",
                      "ok": avg_new >= 85 and (avg_gain is None or avg_gain >= 30),
                      "amostra": f"{len(pairs)} site(s) gerado(s) auditado(s)"})

    review_minutes = []
    for r in Report.objects.select_related("audit").filter(audit__concluido_em__isnull=False)[:50]:
        review_minutes.append((r.criado_em - r.audit.concluido_em).total_seconds() / 60)
    med = _median([m for m in review_minutes if m >= 0])
    if med is not None:
        goals.append({"chave": "revisao", "nome": "Da auditoria ao relatório (mediana)",
                      "valor": f"{med:.0f} min" if med < 120 else f"{med / 60:.1f} h",
                      "meta": "≤ 30 min de revisão", "ok": med <= 30,
                      "amostra": "inclui espera; é um teto para o tempo real de revisão"})

    reviewed = Finding.objects.filter(origem=Finding.Origin.AI,
                                      status_revisao__in=[Finding.Review.CONFIRMED, Finding.Review.DISCARDED])
    total_ai = reviewed.count()
    if total_ai:
        accepted = reviewed.filter(status_revisao=Finding.Review.CONFIRMED, texto_editado=False).count()
        pct = accepted / total_ai * 100
        goals.append({"chave": "ia", "nome": "Achados da IA aceitos sem reescrita", "valor": f"{pct:.0f}%",
                      "meta": "≥ 80%", "ok": pct >= 80, "amostra": f"{total_ai} achado(s) de IA revisado(s)"})
    return goals


@api_view(["GET"])
def dashboard(request):
    """GET /api/dashboard — funil, auditorias da semana e custo de APIs."""
    from .jobs import reap_stale_jobs

    reap_stale_jobs()
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
        "metas": prd_goals(),
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
