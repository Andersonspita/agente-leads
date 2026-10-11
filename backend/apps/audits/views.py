from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog.models import Dimension
from apps.core.activity import log_activity
from apps.core.jobs import enqueue
from apps.leads.models import Company, Website

from .engine.scoring import score_band
from .models import STEPS, Artifact, Audit, AuditStep, Finding
from .tasks import ai_analysis, run_audit

MAX_BATCH = 50  # RF04


class StepSerializer(serializers.ModelSerializer):
    nome = serializers.SerializerMethodField()

    class Meta:
        model = AuditStep
        fields = ["ordem", "etapa", "nome", "status", "duracao_ms", "erro", "resultado"]

    def get_nome(self, obj):
        return next((label for _, key, label in STEPS if key == obj.etapa), obj.etapa)


class FindingSerializer(serializers.ModelSerializer):
    dimensao_nome = serializers.CharField(source="get_dimensao_display", read_only=True)
    editado_por_nome = serializers.CharField(source="editado_por.__str__", default="", read_only=True)

    class Meta:
        model = Finding
        fields = ["id", "audit", "dimensao", "dimensao_nome", "rule_id", "origem", "severidade", "titulo",
                  "descricao", "impacto_negocio", "melhoria_proposta", "evidencia", "status_revisao",
                  "editado_por_nome", "editado_em"]
        read_only_fields = ["rule_id", "evidencia", "editado_por_nome", "editado_em"]
        extra_kwargs = {"audit": {"required": False}, "origem": {"read_only": True}}


class ArtifactSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Artifact
        fields = ["id", "tipo", "url", "tamanho", "meta"]

    def get_url(self, obj):
        return obj.arquivo.url if obj.arquivo else None


class AuditListSerializer(serializers.ModelSerializer):
    empresa = serializers.CharField(source="website.company.nome", read_only=True)
    company_id = serializers.IntegerField(source="website.company_id", read_only=True)
    dominio = serializers.CharField(source="website.dominio", read_only=True)
    faixa = serializers.SerializerMethodField()
    progresso = serializers.SerializerMethodField()
    pendentes = serializers.SerializerMethodField()

    class Meta:
        model = Audit
        fields = ["id", "empresa", "company_id", "dominio", "status", "nota_geral", "faixa", "criado_em",
                  "iniciado_em", "concluido_em", "progresso", "pendentes", "erro"]

    def get_faixa(self, obj):
        return score_band(obj.nota_geral)

    def get_progresso(self, obj):
        steps = list(obj.steps.all())
        done = sum(1 for s in steps if s.status not in ("pendente", "executando"))
        current = next((s.etapa for s in steps if s.status == "executando"), None)
        return {"feitas": done, "total": len(STEPS), "atual": current}

    def get_pendentes(self, obj):
        return sum(1 for f in obj.findings.all() if f.status_revisao == Finding.Review.PENDING)


class AuditDetailSerializer(AuditListSerializer):
    steps = StepSerializer(many=True, read_only=True)
    findings = FindingSerializer(many=True, read_only=True)
    artifacts = ArtifactSerializer(many=True, read_only=True)
    dimensoes = serializers.SerializerMethodField()
    website = serializers.SerializerMethodField()
    reports = serializers.SerializerMethodField()

    class Meta(AuditListSerializer.Meta):
        fields = AuditListSerializer.Meta.fields + [
            "notas_dimensao", "pesos_usados", "metricas", "versao_regras", "versao_prompt", "steps", "findings",
            "artifacts", "dimensoes", "website", "reports",
        ]

    def get_dimensoes(self, obj):
        findings = list(obj.findings.all())
        return [
            {"chave": d.value, "nome": d.label, "nota": obj.notas_dimensao.get(d.value),
             "peso": obj.pesos_usados.get(d.value), **score_band(obj.notas_dimensao.get(d.value)),
             "achados": sum(1 for f in findings if f.dimensao == d.value and f.status_revisao != "descartado")}
            for d in Dimension
        ]

    def get_website(self, obj):
        w = obj.website
        return {"id": w.pk, "url": w.url, "url_final": w.url_final, "dominio": w.dominio, "https": w.https,
                "tecnologias": w.tecnologias, "company_id": w.company_id}

    def get_reports(self, obj):
        return [{"id": r.pk, "criado_em": r.criado_em, "revogado": r.revogado, "enviado_em": r.enviado_em}
                for r in obj.reports.all()]


def start_audits(websites, user) -> list[Audit]:
    audits = []
    with transaction.atomic():
        for website in websites:
            running = website.audits.filter(status__in=[Audit.Status.QUEUED, Audit.Status.RUNNING]).first()
            if running:
                audits.append(running)
                continue
            audit = Audit.objects.create(website=website, solicitado_por=user)
            AuditStep.objects.bulk_create([AuditStep(audit=audit, etapa=k, ordem=o) for o, k, _ in STEPS])
            log_activity(user, "auditoria_solicitada", audit, dominio=website.dominio)
            enqueue(run_audit, audit.pk)
            audits.append(audit)
    return audits


class AuditViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Audit.objects.select_related("website__company").prefetch_related("steps", "findings")

    def get_serializer_class(self):
        return AuditDetailSerializer if self.action == "retrieve" else AuditListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("artifacts", "reports", "findings__editado_por")
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("empresa"):
            qs = qs.filter(website__company_id=params["empresa"])
        if params.get("revisao") == "pendente":
            qs = qs.filter(findings__status_revisao=Finding.Review.PENDING).distinct()
        return qs

    def create(self, request):
        """POST /api/audits — {website_ids: [...]} ou {company_ids: [...]} (até 50)."""
        website_ids = request.data.get("website_ids") or []
        company_ids = request.data.get("company_ids") or []
        websites = list(Website.objects.filter(pk__in=website_ids, auditavel=True))
        if company_ids:
            for company in Company.objects.filter(pk__in=company_ids).prefetch_related("websites"):
                main = company.main_website
                if main and main.auditavel and main not in websites:
                    websites.append(main)
        if not websites:
            return Response({"detail": "Nenhum site auditável selecionado (empresas sem site são ignoradas)."},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(websites) > MAX_BATCH:
            return Response({"detail": f"Máximo de {MAX_BATCH} sites por lote."}, status=status.HTTP_400_BAD_REQUEST)
        audits = start_audits(websites, request.user)
        return Response({"audit_ids": [a.pk for a in audits], "total": len(audits)}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True)
    def compare(self, request, pk=None):
        from apps.reports.services import comparison

        audit = self.get_object()
        return Response(comparison(audit, show_names=True))

    @action(detail=True, methods=["post"])
    def rerun_ai(self, request, pk=None):
        audit = self.get_object()
        enqueue(ai_analysis, audit.pk)
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def rerun(self, request, pk=None):
        """Nova auditoria do mesmo site (auditorias concluídas são imutáveis)."""
        audit = self.get_object()
        new = start_audits([audit.website], request.user)[0]
        return Response({"audit_id": new.pk}, status=status.HTTP_202_ACCEPTED)


class FindingViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    """PATCH /api/findings/{id} — confirmar, editar ou descartar (RF07)."""

    queryset = Finding.objects.select_related("audit")
    serializer_class = FindingSerializer
    http_method_names = ["get", "post", "patch"]

    def perform_update(self, serializer):
        finding = serializer.save(editado_por=self.request.user, editado_em=timezone.now())
        log_activity(self.request.user, f"achado_{finding.status_revisao}", finding,
                     campos=list(self.request.data.keys()))

    def perform_create(self, serializer):
        finding = serializer.save(origem=Finding.Origin.MANUAL, status_revisao=Finding.Review.CONFIRMED,
                                  editado_por=self.request.user, editado_em=timezone.now())
        log_activity(self.request.user, "achado_manual", finding)
