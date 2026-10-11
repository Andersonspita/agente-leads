import csv

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audits.models import Audit
from apps.core.activity import log_activity
from apps.core.jobs import enqueue

from .models import Company, LeadNote, Search, SearchResult, Website, normalize_domain
from .serializers import (
    CompanyCreateSerializer,
    CompanyDetailSerializer,
    CompanyListSerializer,
    LeadNoteSerializer,
    SearchResultSerializer,
    SearchSerializer,
)
from .services import enqueue_enrich
from .tasks import discover_companies

COMPANY_PREFETCH = [
    Prefetch("websites", queryset=Website.objects.order_by("-principal", "id").prefetch_related(
        Prefetch("audits", queryset=Audit.objects.order_by("-concluido_em"))
    )),
]


def filter_companies(qs, params):
    """Filtros comuns à lista de leads e aos resultados de busca (RF01)."""
    situacao = params.get("site")
    if situacao == "sem_site":
        qs = qs.filter(websites__isnull=True)
    elif situacao == "fora_do_ar":
        qs = qs.filter(websites__online=False)
    elif situacao == "tem_site":
        qs = qs.filter(websites__isnull=False).exclude(websites__online=False)
    if params.get("bairro"):
        qs = qs.filter(bairro__icontains=params["bairro"])
    if params.get("status"):
        qs = qs.filter(status_lead__in=params["status"].split(","))
    if params.get("categoria"):
        qs = qs.filter(category_id=params["categoria"])
    if params.get("municipio"):
        qs = qs.filter(municipality_id=params["municipio"])
    if params.get("q"):
        q = params["q"]
        qs = qs.filter(Q(nome__icontains=q) | Q(websites__dominio__icontains=q) | Q(telefone__contains=q))
    if params.get("nota_max"):
        qs = qs.filter(websites__audits__status="concluida", websites__audits__nota_geral__lte=params["nota_max"])
    if params.get("nota_google_min"):
        qs = qs.filter(nota_google__gte=params["nota_google_min"])
    return qs.distinct()


def export_csv(companies, filename):
    """Exportação de leads em CSV (RF13), com BOM para abrir direto no Excel."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Empresa", "CNPJ", "Categoria", "Cidade", "Bairro", "Telefone", "WhatsApp", "Site",
                     "Situação do site", "Nota do site", "Nota Google", "Avaliações", "Status do lead"])
    ser = CompanyListSerializer(companies, many=True)
    for row in ser.data:
        writer.writerow([
            row["nome"], row["cnpj"], row["categoria"], row["municipio"], row["bairro"], row["telefone"],
            row["whatsapp"], (row["site"] or {}).get("url", ""), row["situacao_site"], row["nota_site"] or "",
            row["nota_google"] or "", row["n_avaliacoes"] or "", row["status_lead_nome"],
        ])
    return response


class SearchViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                    viewsets.GenericViewSet):
    queryset = Search.objects.select_related("category", "municipality", "criado_por")
    serializer_class = SearchSerializer

    def perform_create(self, serializer):
        search = serializer.save(criado_por=self.request.user)
        log_activity(self.request.user, "busca_criada", search, descricao=search.descricao)
        enqueue(discover_companies, search.pk)

    @action(detail=True)
    def results(self, request, pk=None):
        search = self.get_object()
        companies = filter_companies(Company.objects.filter(search_results__search=search), request.query_params)
        qs = (
            SearchResult.objects.filter(search=search, company__in=companies)
            .select_related("company__municipality", "company__category")
            .prefetch_related(Prefetch("company__websites", queryset=COMPANY_PREFETCH[0].queryset))
        )
        if request.query_params.get("formato") == "csv":
            return export_csv([r.company for r in qs], f"busca-{search.pk}.csv")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(SearchResultSerializer(page, many=True).data)


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.select_related("municipality", "category", "responsavel").prefetch_related(
        *COMPANY_PREFETCH
    )
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        if self.action == "create":
            return CompanyCreateSerializer
        if self.action == "list":
            return CompanyListSerializer
        return CompanyDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("notes__autor")
        if self.action in ("list", "export"):
            qs = filter_companies(qs, self.request.query_params)
            order = self.request.query_params.get("ordem", "-atualizado_em")
            if order.lstrip("-") in ("nome", "atualizado_em", "nota_google", "status_lead"):
                qs = qs.order_by(order)
        return qs

    def create(self, request, *args, **kwargs):
        ser = CompanyCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        url = ser.validated_data.pop("url", "")
        auditar = ser.validated_data.pop("auditar", False)
        with transaction.atomic():
            if url:
                existing = Website.objects.filter(dominio=normalize_domain(url)).select_related("company").first()
                if existing:
                    return Response({"detail": f"Este site já está cadastrado para “{existing.company.nome}”.",
                                     "company_id": existing.company_id}, status=status.HTTP_409_CONFLICT)
            company = ser.save()
            website = Website.objects.create(company=company, url=url, origem="manual") if url else None
            log_activity(request.user, "empresa_cadastrada", company)
        if website:
            if auditar:
                from apps.audits.views import start_audits

                start_audits([website], request.user)
            else:
                enqueue_enrich(website)
        return Response(CompanyDetailSerializer(self.get_queryset().get(pk=company.pk)).data,
                        status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        before = serializer.instance.status_lead
        company = serializer.save()
        if before != company.status_lead:
            log_activity(self.request.user, "status_lead", company, de=before, para=company.status_lead)

    def perform_destroy(self, instance):
        # Exclusão a pedido (LGPD): remove empresa, sites, auditorias, capturas e relatórios.
        from apps.audits.models import Artifact

        for artifact in Artifact.objects.filter(audit__website__company=instance):
            artifact.arquivo.delete(save=False)
        log_activity(self.request.user, "empresa_excluida", instance, nome=instance.nome)
        instance.delete()

    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        company = self.get_object()
        ser = LeadNoteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(company=company, autor=request.user)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def websites(self, request, pk=None):
        company = self.get_object()
        url = request.data.get("url", "")
        if not url:
            return Response({"detail": "Informe a URL."}, status=400)
        if Website.objects.filter(dominio=normalize_domain(url)).exists():
            return Response({"detail": "Este site já está cadastrado."}, status=409)
        website = Website.objects.create(company=company, url=url, origem="manual",
                                         principal=not company.websites.exists())
        if company.status_lead == "sem_site":
            company.status_lead = "encontrado"
            company.save(update_fields=["status_lead"])
        enqueue_enrich(website)
        return Response(CompanyDetailSerializer(self.get_queryset().get(pk=company.pk)).data, status=201)

    @action(detail=False)
    def export(self, request):
        return export_csv(self.get_queryset(), "leads.csv")


class LeadNoteViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = LeadNote.objects.all()
    serializer_class = LeadNoteSerializer
