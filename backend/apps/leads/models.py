from urllib.parse import urlparse

from django.conf import settings
from django.db import models

from apps.catalog.models import Category
from apps.core.text import normalize_company_name, normalize_phone
from apps.geo.models import Municipality


class LeadStatus(models.TextChoices):
    """Estados do funil (App Flow 3.2)."""

    FOUND = "encontrado", "Encontrado"
    AUDITED = "auditado", "Auditado"
    NO_SITE = "sem_site", "Sem site"
    REPORT_SENT = "relatorio_enviado", "Relatório enviado"
    NEGOTIATING = "em_negociacao", "Em negociação"
    CLOSED = "fechado", "Fechado"
    LOST = "perdido", "Perdido"
    DELIVERED = "entregue", "Entregue"


LEAD_TRANSITIONS = {
    LeadStatus.FOUND: {LeadStatus.AUDITED, LeadStatus.NO_SITE, LeadStatus.LOST},
    LeadStatus.AUDITED: {LeadStatus.REPORT_SENT, LeadStatus.LOST},
    LeadStatus.NO_SITE: {LeadStatus.REPORT_SENT, LeadStatus.AUDITED, LeadStatus.LOST},
    LeadStatus.REPORT_SENT: {LeadStatus.NEGOTIATING, LeadStatus.LOST},
    LeadStatus.NEGOTIATING: {LeadStatus.CLOSED, LeadStatus.LOST},
    LeadStatus.CLOSED: {LeadStatus.DELIVERED},
    LeadStatus.LOST: {LeadStatus.FOUND},  # recontatar
    LeadStatus.DELIVERED: set(),
}


def normalize_domain(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


class Search(models.Model):
    class Status(models.TextChoices):
        QUEUED = "na_fila", "Na fila"
        RUNNING = "executando", "Executando"
        DONE = "concluida", "Concluída"
        FAILED = "falhou", "Falhou"

    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    municipality = models.ForeignKey(Municipality, on_delete=models.PROTECT)
    termo_livre = models.CharField(max_length=120, blank=True)
    bairro = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    total_encontrado = models.PositiveIntegerField(default=0)
    fontes = models.JSONField(default=dict, blank=True)  # {"places": 40, "cnpj": 12, "erros": [...]}
    erro = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)
    concluido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "busca"

    @property
    def descricao(self):
        termo = self.termo_livre or (self.category.nome if self.category else "")
        return f"{termo} em {self.municipality}"

    def __str__(self):
        return self.descricao


class Company(models.Model):
    nome = models.CharField(max_length=200)
    nome_normalizado = models.CharField(max_length=200, db_index=True)
    cnpj = models.CharField(max_length=14, blank=True, db_index=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    municipality = models.ForeignKey(Municipality, null=True, blank=True, on_delete=models.SET_NULL)
    endereco = models.CharField(max_length=255, blank=True)
    bairro = models.CharField(max_length=80, blank=True)
    telefone = models.CharField(max_length=20, blank=True, db_index=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    google_place_id = models.CharField(max_length=120, blank=True, db_index=True)
    nota_google = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    n_avaliacoes = models.PositiveIntegerField(null=True, blank=True)
    redes_sociais = models.JSONField(default=dict, blank=True)
    status_lead = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.FOUND)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "empresa"
        indexes = [models.Index(fields=["municipality", "category", "status_lead"])]

    def save(self, *args, **kwargs):
        self.nome_normalizado = normalize_company_name(self.nome)
        self.telefone = normalize_phone(self.telefone)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome

    @property
    def main_website(self):
        return self.websites.order_by("-principal", "id").first()

    def can_transition(self, new_status) -> bool:
        return new_status == self.status_lead or new_status in LEAD_TRANSITIONS.get(self.status_lead, set())


class Website(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="websites")
    url = models.URLField(max_length=500)
    dominio = models.CharField(max_length=255, unique=True)
    principal = models.BooleanField(default=True)
    https = models.BooleanField(null=True)
    status_http = models.PositiveSmallIntegerField(null=True, blank=True)
    url_final = models.URLField(max_length=500, blank=True)
    online = models.BooleanField(null=True)
    ultimo_check = models.DateTimeField(null=True, blank=True)
    tecnologias = models.JSONField(default=list, blank=True)
    auditavel = models.BooleanField(default=True, help_text="Falso quando o site bloqueia o robô")
    origem = models.CharField(
        max_length=12, blank=True,
        choices=[("places", "Google Places"), ("osm", "OpenStreetMap"), ("email_cnpj", "E-mail do CNPJ"),
                 ("web", "Busca web"), ("manual", "Cadastro manual"), ("gerado", "Site novo gerado")],
        help_text="De onde veio o endereço do site",
    )

    class Meta:
        verbose_name = "site"

    def save(self, *args, **kwargs):
        if self.origem == "gerado":
            # Prévias de sites gerados ficam todas no mesmo host: o caminho identifica cada uma.
            self.dominio = "gerado:" + urlparse(self.url).path.strip("/")
        else:
            self.dominio = normalize_domain(self.url)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.dominio

    @property
    def last_audit(self):
        return self.audits.filter(status="concluida").order_by("-concluido_em").first()


class SearchResult(models.Model):
    class Source(models.TextChoices):
        PLACES = "places", "Google Places"
        CNPJ = "cnpj", "Base CNPJ"
        OSM = "osm", "OpenStreetMap"
        WEB = "web", "Busca web"
        MANUAL = "manual", "Cadastro manual"

    search = models.ForeignKey(Search, on_delete=models.CASCADE, related_name="results")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="search_results")
    fonte = models.CharField(max_length=10, choices=Source.choices)
    posicao = models.PositiveIntegerField(default=0)
    payload_bruto = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["posicao"]
        unique_together = [("search", "company")]


class LeadNote(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="notes")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    texto = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]


class CnpjEstablishment(models.Model):
    """Recorte local da base aberta de CNPJ da Receita (carregado por `import_cnpj`).

    Só estabelecimentos ativos, dos CNAEs das categorias cadastradas. Do e-mail cadastral
    guarda apenas o domínio corporativo (ex.: clinicasorriso.com.br), usado para descobrir o
    site; o endereço de e-mail em si não é armazenado. O telefone é o comercial da empresa.
    """

    cnpj = models.CharField(max_length=14, primary_key=True)
    nome_fantasia = models.CharField(max_length=200, blank=True)
    razao_social = models.CharField(max_length=200, blank=True)
    cnae_principal = models.CharField(max_length=7, db_index=True)
    cnaes_secundarios = models.TextField(blank=True)
    municipality = models.ForeignKey(Municipality, null=True, on_delete=models.SET_NULL)
    uf = models.CharField(max_length=2)
    bairro = models.CharField(max_length=80, blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    cep = models.CharField(max_length=8, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    dominio_email = models.CharField(max_length=255, blank=True)
    inicio_atividade = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["municipality", "cnae_principal"])]

    @property
    def nome(self):
        return self.nome_fantasia or self.razao_social or f"CNPJ {self.cnpj}"
