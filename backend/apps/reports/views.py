import re

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import is_verified
from apps.audits.models import Audit, Finding
from apps.core.activity import log_activity
from apps.core.jobs import enqueue
from apps.leads.models import Company, LeadStatus

from .models import Briefing, Report, ReportView
from .services import briefing_markdown, briefing_pdf, build_briefing, build_report_context, hash_ip
from .tasks import render_report_pdf


class ReportSerializer(serializers.ModelSerializer):
    empresa = serializers.CharField(source="audit.website.company.nome", read_only=True)
    company_id = serializers.IntegerField(source="audit.website.company_id", read_only=True)
    nota_geral = serializers.IntegerField(source="audit.nota_geral", read_only=True)
    url_publica = serializers.CharField(source="public_url", read_only=True)
    pdf_url = serializers.SerializerMethodField()
    visualizacoes = serializers.SerializerMethodField()
    ultima_visualizacao = serializers.SerializerMethodField()
    disponivel = serializers.BooleanField(source="is_available", read_only=True)

    class Meta:
        model = Report
        fields = ["id", "audit", "empresa", "company_id", "nota_geral", "token", "url_publica", "expira_em",
                  "pdf_url", "pdf_status", "texto_abertura", "resumo", "concorrentes_ids",
                  "exibir_nomes_concorrentes", "achados_ids", "criado_em", "enviado_em", "revogado", "disponivel",
                  "visualizacoes", "ultima_visualizacao"]
        read_only_fields = ["token", "pdf_status", "criado_em", "enviado_em", "revogado"]

    def get_pdf_url(self, obj):
        return obj.pdf.url if obj.pdf else None

    def get_visualizacoes(self, obj):
        return obj.views.count()

    def get_ultima_visualizacao(self, obj):
        last = obj.views.first()
        return last.visto_em if last else None

    def validate_audit(self, audit):
        if audit.status != Audit.Status.DONE:
            raise serializers.ValidationError("A auditoria ainda não foi concluída.")
        if audit.findings.filter(status_revisao=Finding.Review.PENDING).exists():
            raise serializers.ValidationError("Revise os achados pendentes antes de gerar o relatório.")
        return audit


class ReportViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Report.objects.select_related("audit__website__company").prefetch_related("views")
    serializer_class = ReportSerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("empresa"):
            qs = qs.filter(audit__website__company_id=self.request.query_params["empresa"])
        if self.request.query_params.get("audit"):
            qs = qs.filter(audit_id=self.request.query_params["audit"])
        return qs

    def perform_create(self, serializer):
        report = serializer.save(criado_por=self.request.user)
        log_activity(self.request.user, "relatorio_gerado", report)
        enqueue(render_report_pdf, report.pk)

    def perform_update(self, serializer):
        report = serializer.save()
        log_activity(self.request.user, "relatorio_editado", report, campos=list(self.request.data.keys()))
        enqueue(render_report_pdf, report.pk)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        report = self.get_object()
        report.revogado = True
        report.save(update_fields=["revogado"])
        log_activity(request.user, "relatorio_revogado", report)
        return Response(ReportSerializer(report).data)

    @action(detail=True, methods=["post"])
    def mark_sent(self, request, pk=None):
        report = self.get_object()
        report.enviado_em = timezone.now()
        report.save(update_fields=["enviado_em"])
        company = report.company
        if company.can_transition(LeadStatus.REPORT_SENT):
            company.status_lead = LeadStatus.REPORT_SENT
            company.save(update_fields=["status_lead", "atualizado_em"])
        log_activity(request.user, "relatorio_enviado", report, canal=request.data.get("canal", ""))
        return Response(ReportSerializer(report).data)

    @action(detail=True, methods=["post"])
    def regenerate_pdf(self, request, pk=None):
        enqueue(render_report_pdf, self.get_object().pk)
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)


@never_cache
@xframe_options_sameorigin
def report_preview(request, pk):
    """Pré-visualização interna (não conta como abertura pelo cliente)."""
    if not is_verified(request):
        raise Http404
    report = get_object_or_404(Report.objects.select_related("audit__website__company"), pk=pk)
    return render(request, "reports/public.html", build_report_context(report))


LINK_PREVIEW_BOTS = re.compile(
    r"bot|crawl|spider|preview|whatsapp|facebookexternalhit|facebookcatalog|telegram|slack|discord|skype|"
    r"linkedin|embedly|pinterest|vkshare|curl|wget|python-requests|headless|lighthouse",
    re.I,
)


@never_cache
def public_report(request, token):
    """GET /r/{token} — página pública do relatório, sem login (TRD 2.6)."""
    report = Report.objects.select_related("audit__website__company").filter(token=token).first()
    if report is None or not report.is_available:
        return render(request, "reports/unavailable.html", status=404)
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    # O WhatsApp, o Facebook etc. abrem o link sozinhos para montar a prévia: isso não é o cliente lendo.
    if not request.user.is_authenticated and not LINK_PREVIEW_BOTS.search(user_agent):
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
        ReportView.objects.create(report=report, user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
                                  ip_hash=hash_ip(ip))
    html = render_to_string("reports/public.html", build_report_context(report), request=request)
    response = HttpResponse(html)
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response


class BriefingSerializer(serializers.ModelSerializer):
    empresa = serializers.CharField(source="company.nome", read_only=True)

    class Meta:
        model = Briefing
        fields = ["id", "company", "empresa", "audit", "conteudo", "versao", "criado_em"]
        read_only_fields = ["versao", "criado_em"]
        extra_kwargs = {"conteudo": {"required": False}}


class BriefingViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = Briefing.objects.select_related("company")
    serializer_class = BriefingSerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("empresa"):
            qs = qs.filter(company_id=self.request.query_params["empresa"])
        return qs

    def perform_create(self, serializer):
        company: Company = serializer.validated_data["company"]
        audit = serializer.validated_data.get("audit")
        if audit is None:
            audit = Audit.objects.filter(website__company=company, status=Audit.Status.DONE).order_by(
                "-concluido_em").first()
        version = (company.briefings.order_by("-versao").values_list("versao", flat=True).first() or 0) + 1
        briefing = serializer.save(audit=audit, conteudo=build_briefing(company, audit), versao=version,
                                   criado_por=self.request.user)
        log_activity(self.request.user, "briefing_gerado", briefing)

    @action(detail=True)
    def pdf(self, request, pk=None):
        briefing = self.get_object()
        response = HttpResponse(briefing_pdf(briefing), content_type="application/pdf")
        name = briefing.company.nome_normalizado.replace(" ", "-")[:40]
        response["Content-Disposition"] = f'attachment; filename="briefing-{name}-v{briefing.versao}.pdf"'
        return response

    @action(detail=True)
    def markdown(self, request, pk=None):
        briefing = self.get_object()
        response = HttpResponse(briefing_markdown(briefing), content_type="text/markdown; charset=utf-8")
        name = briefing.company.nome_normalizado.replace(" ", "-")[:40]
        response["Content-Disposition"] = f'attachment; filename="briefing-{name}-v{briefing.versao}.md"'
        return response


def legal_page(template):
    """Páginas públicas de política de privacidade e exclusão de dados (definição de pronto do MVP)."""

    def view(request):
        from apps.core.models import BrandSettings

        return render(request, template, {"brand": BrandSettings.get()})

    return view
