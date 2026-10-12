from rest_framework import serializers

from apps.audits.engine.scoring import score_band
from apps.geo.views import MunicipalitySerializer

from .models import Company, LeadNote, LeadStatus, Search, SearchResult, Website


class WebsiteSerializer(serializers.ModelSerializer):
    ultima_auditoria = serializers.SerializerMethodField()

    class Meta:
        model = Website
        fields = ["id", "url", "dominio", "principal", "https", "status_http", "url_final", "online",
                  "ultimo_check", "tecnologias", "auditavel", "ultima_auditoria"]
        read_only_fields = ["dominio", "https", "status_http", "url_final", "online", "ultimo_check", "tecnologias"]

    def get_ultima_auditoria(self, obj):
        audit = obj.audits.order_by("-criado_em").first()
        if not audit:
            return None
        return {"id": audit.pk, "status": audit.status, "nota_geral": audit.nota_geral,
                "concluido_em": audit.concluido_em, **score_band(audit.nota_geral)}


def site_state(company) -> str:
    sites = list(company.websites.all())
    if not sites:
        return "sem_site"
    main = sites[0]
    if main.online is False:
        return "fora_do_ar"
    return "tem_site"


class CompanyListSerializer(serializers.ModelSerializer):
    municipio = serializers.StringRelatedField(source="municipality")
    categoria = serializers.CharField(source="category.nome", default="", read_only=True)
    site = serializers.SerializerMethodField()
    situacao_site = serializers.SerializerMethodField()
    nota_site = serializers.SerializerMethodField()
    status_lead_nome = serializers.CharField(source="get_status_lead_display", read_only=True)

    class Meta:
        model = Company
        fields = ["id", "nome", "bairro", "telefone", "whatsapp", "nota_google", "n_avaliacoes", "status_lead",
                  "status_lead_nome", "municipio", "categoria", "site", "situacao_site", "nota_site", "cnpj"]

    def _main(self, obj):
        sites = list(obj.websites.all())
        return sites[0] if sites else None

    def get_site(self, obj):
        main = self._main(obj)
        return {"id": main.pk, "url": main.url, "dominio": main.dominio, "https": main.https,
                "online": main.online, "auditavel": main.auditavel} if main else None

    def get_situacao_site(self, obj):
        return site_state(obj)

    def get_nota_site(self, obj):
        main = self._main(obj)
        if not main:
            return None
        audit = next((a for a in main.audits.all() if a.status == "concluida"), None)
        return audit.nota_geral if audit else None


class LeadNoteSerializer(serializers.ModelSerializer):
    autor_nome = serializers.StringRelatedField(source="autor")

    class Meta:
        model = LeadNote
        fields = ["id", "texto", "autor_nome", "criado_em"]


class CompanyDetailSerializer(CompanyListSerializer):
    websites = WebsiteSerializer(many=True, read_only=True)
    notes = LeadNoteSerializer(many=True, read_only=True)
    municipality_data = MunicipalitySerializer(source="municipality", read_only=True)
    transicoes = serializers.SerializerMethodField()
    responsavel_nome = serializers.StringRelatedField(source="responsavel")

    class Meta(CompanyListSerializer.Meta):
        fields = CompanyListSerializer.Meta.fields + [
            "endereco", "google_place_id", "redes_sociais", "category", "municipality", "municipality_data",
            "responsavel", "responsavel_nome", "websites", "notes", "transicoes", "criado_em", "atualizado_em",
        ]

    def get_transicoes(self, obj):
        from .models import LEAD_TRANSITIONS

        return [{"valor": s.value, "nome": s.label} for s in LEAD_TRANSITIONS.get(LeadStatus(obj.status_lead), [])]

    def validate_status_lead(self, value):
        if self.instance and not self.instance.can_transition(value):
            raise serializers.ValidationError(
                f"Não é possível ir de “{self.instance.get_status_lead_display()}” para “{LeadStatus(value).label}”."
            )
        return value


class CompanyCreateSerializer(serializers.ModelSerializer):
    """Cadastro manual de empresa + URL avulsa (PRD 1.4 item 2)."""

    url = serializers.URLField(required=False, allow_blank=True, write_only=True)
    auditar = serializers.BooleanField(default=False, write_only=True)

    class Meta:
        model = Company
        fields = ["id", "nome", "category", "municipality", "telefone", "endereco", "bairro", "cnpj", "url", "auditar"]


class SearchSerializer(serializers.ModelSerializer):
    categoria = serializers.CharField(source="category.nome", default="", read_only=True)
    municipio = serializers.StringRelatedField(source="municipality")
    criado_por_nome = serializers.StringRelatedField(source="criado_por")

    class Meta:
        model = Search
        fields = ["id", "category", "categoria", "municipality", "municipio", "termo_livre", "bairro", "status",
                  "total_encontrado", "fontes", "erro", "criado_por_nome", "criado_em", "concluido_em", "descricao"]
        read_only_fields = ["status", "total_encontrado", "fontes", "erro", "criado_em", "concluido_em"]

    def validate(self, attrs):
        if not attrs.get("category") and not attrs.get("termo_livre"):
            raise serializers.ValidationError("Informe uma categoria ou um termo de busca.")
        return attrs


class SearchResultSerializer(serializers.ModelSerializer):
    company = CompanyListSerializer(read_only=True)

    class Meta:
        model = SearchResult
        fields = ["id", "fonte", "posicao", "company"]
