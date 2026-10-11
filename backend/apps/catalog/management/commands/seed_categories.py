from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, CategoryChecklistItem, CategoryWeight, Dimension

D = Dimension

# Pesos somam 1. Saúde e serviços locais pesam mais conversão/conteúdo; advocacia pesa credibilidade e LGPD.
CATEGORIES = [
    {
        "nome": "Clínica odontológica",
        "termos": ["clínica odontológica", "dentista"],
        "cnaes": ["8630-5/04"],
        "osm": ["amenity=dentist", "healthcare=dentist"],
        "pesos": {D.PERFORMANCE: "0.15", D.MOBILE: "0.15", D.SEO: "0.15", D.ACCESSIBILITY: "0.10",
                  D.SECURITY: "0.05", D.CONTENT: "0.10", D.CONVERSION: "0.20", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Agendamento online de consultas", "integracao", True),
            ("Página de tratamentos/especialidades", "pagina", True),
            ("Convênios aceitos", "secao", False),
            ("Responsável técnico com número do CRO", "secao", True),
        ],
    },
    {
        "nome": "Clínica médica",
        "termos": ["clínica médica", "consultório médico"],
        "cnaes": ["8630-5/01", "8630-5/02", "8630-5/03"],
        "osm": ["amenity=clinic", "amenity=doctors", "healthcare=clinic", "healthcare=doctor"],
        "pesos": {D.PERFORMANCE: "0.15", D.MOBILE: "0.15", D.SEO: "0.15", D.ACCESSIBILITY: "0.10",
                  D.SECURITY: "0.05", D.CONTENT: "0.10", D.CONVERSION: "0.20", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Agendamento online de consultas", "integracao", True),
            ("Página de especialidades e corpo clínico", "pagina", True),
            ("Responsável técnico com número do CRM", "secao", True),
            ("Convênios aceitos", "secao", False),
        ],
    },
    {
        "nome": "Escritório de advocacia",
        "termos": ["escritório de advocacia", "advogado"],
        "cnaes": ["6911-7/01"],
        "osm": ["office=lawyer"],
        "pesos": {D.PERFORMANCE: "0.10", D.MOBILE: "0.15", D.SEO: "0.15", D.ACCESSIBILITY: "0.10",
                  D.SECURITY: "0.10", D.CONTENT: "0.20", D.CONVERSION: "0.10", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Página de áreas de atuação", "pagina", True),
            ("Equipe com número de inscrição na OAB", "secao", True),
            ("Conteúdo informativo conforme Provimento 205/2021 da OAB (sem captação indevida)", "meta", True),
            ("Artigos/blog jurídico", "pagina", False),
        ],
    },
    {
        "nome": "Escritório de contabilidade",
        "termos": ["escritório de contabilidade", "contador"],
        "cnaes": ["6920-6/01"],
        "osm": ["office=accountant", "office=tax_advisor"],
        "pesos": {D.PERFORMANCE: "0.10", D.MOBILE: "0.15", D.SEO: "0.15", D.ACCESSIBILITY: "0.10",
                  D.SECURITY: "0.10", D.CONTENT: "0.15", D.CONVERSION: "0.15", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Página de serviços (abertura de empresa, MEI, folha, fiscal)", "pagina", True),
            ("Área do cliente / portal de documentos", "integracao", False),
            ("Registro no CRC", "secao", True),
            ("Formulário de orçamento", "secao", True),
        ],
    },
    {
        "nome": "Construtora e reformas",
        "termos": ["construtora", "empresa de reformas"],
        "cnaes": ["4120-4/00", "4330-4/99"],
        "osm": ["office=construction_company", "craft=builder"],
        "pesos": {D.PERFORMANCE: "0.15", D.MOBILE: "0.15", D.SEO: "0.15", D.ACCESSIBILITY: "0.05",
                  D.SECURITY: "0.10", D.CONTENT: "0.15", D.CONVERSION: "0.15", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Portfólio de obras com fotos", "pagina", True),
            ("Formulário de orçamento", "secao", True),
            ("Registro no CREA/CAU", "secao", False),
        ],
    },
    {
        "nome": "Salão de beleza",
        "termos": ["salão de beleza", "cabeleireiro"],
        "cnaes": ["9602-5/01", "9602-5/02"],
        "osm": ["shop=hairdresser", "shop=beauty"],
        "pesos": {D.PERFORMANCE: "0.15", D.MOBILE: "0.20", D.SEO: "0.10", D.ACCESSIBILITY: "0.05",
                  D.SECURITY: "0.05", D.CONTENT: "0.15", D.CONVERSION: "0.20", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Agendamento online", "integracao", True),
            ("Tabela de serviços", "secao", True),
            ("Galeria de trabalhos / Instagram", "secao", True),
        ],
    },
    {
        "nome": "Restaurante",
        "termos": ["restaurante"],
        "cnaes": ["5611-2/01"],
        "osm": ["amenity=restaurant"],
        "pesos": {D.PERFORMANCE: "0.15", D.MOBILE: "0.20", D.SEO: "0.15", D.ACCESSIBILITY: "0.05",
                  D.SECURITY: "0.05", D.CONTENT: "0.15", D.CONVERSION: "0.15", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Cardápio em HTML (não só PDF/imagem)", "pagina", True),
            ("Pedido online / link para delivery", "integracao", False),
            ("Reserva de mesa", "integracao", False),
        ],
    },
    {
        "nome": "Imobiliária",
        "termos": ["imobiliária"],
        "cnaes": ["6821-8/01", "6821-8/02"],
        "osm": ["office=estate_agent"],
        "pesos": {D.PERFORMANCE: "0.15", D.MOBILE: "0.15", D.SEO: "0.15", D.ACCESSIBILITY: "0.05",
                  D.SECURITY: "0.10", D.CONTENT: "0.15", D.CONVERSION: "0.15", D.COMPLIANCE: "0.10"},
        "checklist": [
            ("Busca de imóveis com filtros", "integracao", True),
            ("Registro no CRECI", "secao", True),
        ],
    },
]


class Command(BaseCommand):
    help = "Cadastra as categorias iniciais com CNAEs, pesos e checklist mínimo."

    def handle(self, *args, **opts):
        with transaction.atomic():
            for spec in CATEGORIES:
                assert abs(sum(Decimal(v) for v in spec["pesos"].values()) - 1) < Decimal("0.001"), spec["nome"]
                cat, created = Category.objects.get_or_create(
                    slug=slugify(spec["nome"]),
                    defaults={"nome": spec["nome"], "termos_busca": spec["termos"], "cnaes": spec["cnaes"],
                              "osm_tags": spec["osm"]},
                )
                if not cat.osm_tags:
                    cat.osm_tags = spec["osm"]
                    cat.save(update_fields=["osm_tags"])
                for dim, peso in spec["pesos"].items():
                    CategoryWeight.objects.update_or_create(category=cat, dimensao=dim.value,
                                                            defaults={"peso": Decimal(peso)})
                if created:
                    CategoryChecklistItem.objects.bulk_create([
                        CategoryChecklistItem(category=cat, item=item, tipo=tipo, obrigatorio=obrig)
                        for item, tipo, obrig in spec["checklist"]
                    ])
                self.stdout.write(f"{'+' if created else '='} {cat.nome}")
        from apps.catalog.views import sync_rules

        sync_rules()
        self.stdout.write(self.style.SUCCESS("Categorias e regras sincronizadas."))
