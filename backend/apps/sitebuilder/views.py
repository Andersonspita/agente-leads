from django.conf import settings
from django.http import Http404, HttpResponse
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audits.engine.scoring import score_band
from apps.audits.models import Audit
from apps.core.activity import log_activity
from apps.leads.models import Company, Website

from .content import build_content
from .models import SiteProject
from .render import build_zip, render_files

EDITABLE_KEYS = {
    "empresa", "categoria", "cidade", "uf", "telefone", "whatsapp", "email", "endereco", "bairro", "cep",
    "horario", "instagram", "facebook", "link_agendamento", "agendamento", "cor", "cor_destaque", "titulo_seo",
    "descricao_seo", "headline", "subheadline", "sobre", "servicos", "diferenciais", "faq", "a_confirmar",
}


def _audit_summary(audit):
    if not audit:
        return None
    return {"id": audit.pk, "status": audit.status, "nota_geral": audit.nota_geral,
            "notas_dimensao": audit.notas_dimensao, "concluido_em": audit.concluido_em,
            "achados": audit.findings.exclude(status_revisao="descartado").count(), **score_band(audit.nota_geral)}


class SiteProjectSerializer(serializers.ModelSerializer):
    empresa = serializers.CharField(source="company.nome", read_only=True)
    preview_url = serializers.CharField(read_only=True)
    auditoria_original = serializers.SerializerMethodField()
    auditoria_site_novo = serializers.SerializerMethodField()

    class Meta:
        model = SiteProject
        fields = ["id", "company", "empresa", "token", "conteudo", "gerado_por_ia", "modelo_ia", "preview_url",
                  "auditoria_original", "auditoria_site_novo", "criado_em", "atualizado_em"]
        read_only_fields = ["token", "gerado_por_ia", "modelo_ia", "criado_em", "atualizado_em"]
        extra_kwargs = {"conteudo": {"required": False}}

    def get_auditoria_original(self, obj):
        return _audit_summary(obj.audit_origem)

    def get_auditoria_site_novo(self, obj):
        if not obj.website_id:
            return None
        return _audit_summary(obj.website.audits.order_by("-criado_em").first())

    def validate_conteudo(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Formato inválido.")
        current = dict(self.instance.conteudo) if self.instance else {}
        current.update({k: v for k, v in value.items() if k in EDITABLE_KEYS})
        return current


class SiteProjectViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                         mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Site novo gerado a partir do diagnóstico: criar, editar, baixar (.zip) e auditar."""

    queryset = SiteProject.objects.select_related("company", "audit_origem", "website")
    serializer_class = SiteProjectSerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("empresa"):
            qs = qs.filter(company_id=self.request.query_params["empresa"])
        return qs

    def create(self, request, *args, **kwargs):
        company = Company.objects.filter(pk=request.data.get("company")).select_related(
            "category", "municipality").first()
        if not company:
            return Response({"detail": "Empresa não encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        audit = Audit.objects.filter(website__company=company, status=Audit.Status.DONE).exclude(
            website__origem="gerado").order_by("-concluido_em").first()
        content, by_ai, model = build_content(company, audit)
        project = SiteProject.objects.create(company=company, audit_origem=audit, conteudo=content,
                                             gerado_por_ia=by_ai, modelo_ia=model, criado_por=request.user)
        log_activity(request.user, "site_gerado", project, ia=by_ai)
        return Response(SiteProjectSerializer(project).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        project = serializer.save()
        log_activity(self.request.user, "site_editado", project)

    @action(detail=True)
    def download(self, request, pk=None):
        project = self.get_object()
        response = HttpResponse(build_zip(project.conteudo, project.preview_url), content_type="application/zip")
        slug = project.company.nome_normalizado.replace(" ", "-")[:40] or "site"
        response["Content-Disposition"] = f'attachment; filename="site-{slug}.zip"'
        return response

    @action(detail=True, methods=["post"])
    def audit(self, request, pk=None):
        """Audita o site gerado com o mesmo motor, para comparar a nota com a do site atual."""
        from apps.audits.views import start_audits

        project = self.get_object()
        if project.website_id is None:
            project.website = Website.objects.create(company=project.company, url=project.preview_url,
                                                     origem="gerado", principal=False)
            project.save(update_fields=["website"])
        audit = start_audits([project.website], request.user)[0]
        return Response({"audit_id": audit.pk}, status=status.HTTP_202_ACCEPTED)


def serve_site(request, token, path=""):
    """Prévia pública do site gerado: /s/<token>/ e seus arquivos."""
    project = SiteProject.objects.filter(token=token).first()
    if project is None:
        raise Http404
    files = render_files(project.conteudo, project.preview_url)
    entry = files.get(path or "index.html")
    if entry is None:
        raise Http404
    body, content_type = entry
    response = HttpResponse(body, content_type=content_type)
    response["Cache-Control"] = "no-store"
    response["X-Frame-Options"] = "SAMEORIGIN"  # aparece dentro do painel
    return response


def robots_for(request):
    """O host das prévias de sites libera rastreio (para o próprio auditor medir); o resto do sistema, não."""
    from urllib.parse import urlparse

    sites_host = urlparse(settings.SITES_BASE_URL).netloc
    if sites_host and request.get_host() == sites_host and sites_host != urlparse(settings.PUBLIC_BASE_URL).netloc:
        sitemaps = "".join(f"Sitemap: {p.preview_url}sitemap.xml\n" for p in SiteProject.objects.only("token")[:200])
        return HttpResponse("User-agent: *\nAllow: /s/\nDisallow: /\n" + sitemaps, content_type="text/plain")
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
