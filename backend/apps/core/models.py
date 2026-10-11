from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """Trilha de auditoria: quem gerou, editou ou enviou o quê (TRD 2.6)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    acao = models.CharField(max_length=60)
    entidade = models.CharField(max_length=40)
    entidade_id = models.CharField(max_length=40, blank=True)
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["entidade", "entidade_id"])]

    def __str__(self):
        return f"{self.acao} {self.entidade}#{self.entidade_id}"


class ApiUsage(models.Model):
    """Cada chamada paga a APIs externas, para o painel de custos (RF14)."""

    class Provider(models.TextChoices):
        GOOGLE_PLACES = "google_places", "Google Places"
        ANTHROPIC = "anthropic", "Claude API"
        GEMINI = "gemini", "Gemini (gratuito)"
        OPENAI_COMPAT = "openai_compat", "IA compatível com OpenAI"
        WEB_SEARCH = "web_search", "Busca web"

    provedor = models.CharField(max_length=20, choices=Provider.choices)
    endpoint = models.CharField(max_length=120)
    custo_estimado = models.DecimalField(max_digits=10, decimal_places=4, default=0)  # em R$
    detalhes = models.JSONField(default=dict, blank=True)
    data = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-data"]


class PromptVersion(models.Model):
    """Prompts de IA versionados no banco (TRD 2.5)."""

    nome = models.CharField(max_length=60)
    texto = models.TextField()
    modelo = models.CharField(max_length=60)
    ativo = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome", "-criado_em"]

    def __str__(self):
        return f"{self.nome} v{self.pk}"

    @classmethod
    def active(cls, nome):
        return cls.objects.filter(nome=nome, ativo=True).order_by("-criado_em").first()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.ativo:
            PromptVersion.objects.filter(nome=self.nome).exclude(pk=self.pk).update(ativo=False)


class BrandSettings(models.Model):
    """Marca que assina os relatórios (configurável — questão em aberto do PRD 1.8)."""

    nome_empresa = models.CharField(max_length=120, default="Horizon AJ Desenvolvimento")
    cor_primaria = models.CharField(max_length=7, default="#1d4ed8")
    logo = models.FileField(upload_to="brand/", blank=True)
    whatsapp = models.CharField(max_length=20, blank=True, help_text="Somente dígitos, com DDI e DDD")
    link_agenda = models.URLField(blank=True)
    email_contato = models.EmailField(blank=True)
    site = models.URLField(blank=True)
    exibir_nomes_concorrentes = models.BooleanField(default=False)

    class Meta:
        verbose_name = "marca"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
