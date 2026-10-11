from django.conf import settings
from django.db import models

from apps.catalog.models import Dimension, Severity
from apps.leads.models import Website

STEPS = [
    (1, "rastreio", "Rastreio"),
    (2, "capturas", "Capturas de tela"),
    (3, "lighthouse", "Lighthouse"),
    (4, "acessibilidade", "Acessibilidade (axe)"),
    (5, "seguranca", "Segurança"),
    (6, "tecnologia", "Tecnologia"),
    (7, "conteudo", "Conteúdo e conversão"),
    (8, "ia", "Análise qualitativa (IA)"),
    (9, "pontuacao", "Pontuação"),
]


class Audit(models.Model):
    class Status(models.TextChoices):
        QUEUED = "na_fila", "Na fila"
        RUNNING = "executando", "Executando"
        DONE = "concluida", "Concluída"
        FAILED = "falhou", "Falhou"

    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="audits")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    solicitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    nota_geral = models.PositiveSmallIntegerField(null=True, blank=True)
    notas_dimensao = models.JSONField(default=dict, blank=True)
    pesos_usados = models.JSONField(default=dict, blank=True)
    metricas = models.JSONField(default=dict, blank=True)  # LCP, CLS, peso da página etc.
    versao_regras = models.CharField(max_length=20, blank=True)
    versao_prompt = models.CharField(max_length=40, blank=True)
    erro = models.TextField(blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "auditoria"

    def __str__(self):
        return f"Auditoria #{self.pk} {self.website}"

    @property
    def company(self):
        return self.website.company

    @property
    def is_final(self):
        return self.status in (self.Status.DONE, self.Status.FAILED)


class AuditStep(models.Model):
    class Status(models.TextChoices):
        PENDING = "pendente", "Pendente"
        RUNNING = "executando", "Executando"
        DONE = "ok", "Concluída"
        FAILED = "falhou", "Falhou"
        SKIPPED = "nao_medido", "Não medida"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="steps")
    ordem = models.PositiveSmallIntegerField()
    etapa = models.CharField(max_length=20)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    duracao_ms = models.PositiveIntegerField(null=True, blank=True)
    erro = models.TextField(blank=True)
    resultado = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["ordem"]
        unique_together = [("audit", "etapa")]


class Finding(models.Model):
    class Origin(models.TextChoices):
        RULE = "regra", "Regra automática"
        AI = "ia", "Avaliação assistida (IA)"
        MANUAL = "manual", "Analista"

    class Review(models.TextChoices):
        PENDING = "pendente", "Pendente de revisão"
        CONFIRMED = "confirmado", "Confirmado"
        DISCARDED = "descartado", "Descartado"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="findings")
    dimensao = models.CharField(max_length=20, choices=Dimension.choices)
    rule_id = models.CharField(max_length=12, blank=True)
    origem = models.CharField(max_length=8, choices=Origin.choices, default=Origin.RULE)
    severidade = models.CharField(max_length=10, choices=Severity.choices)
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    impacto_negocio = models.TextField(blank=True)
    melhoria_proposta = models.TextField(blank=True)
    evidencia = models.JSONField(default=dict, blank=True)
    status_revisao = models.CharField(max_length=12, choices=Review.choices, default=Review.PENDING)
    ordem_relatorio = models.PositiveSmallIntegerField(null=True, blank=True)
    editado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    editado_em = models.DateTimeField(null=True, blank=True)
    texto_editado = models.BooleanField(default=False, help_text="O analista reescreveu título, impacto ou melhoria")

    SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}

    class Meta:
        ordering = ["audit", "id"]
        verbose_name = "achado"
        indexes = [models.Index(fields=["audit", "status_revisao"])]

    def __str__(self):
        return self.titulo


class Artifact(models.Model):
    class Kind(models.TextChoices):
        SCREENSHOT_DESKTOP = "screenshot_desktop", "Captura desktop (dobra)"
        SCREENSHOT_DESKTOP_FULL = "screenshot_desktop_full", "Captura desktop (página inteira)"
        SCREENSHOT_MOBILE = "screenshot_mobile", "Captura mobile (dobra)"
        SCREENSHOT_MOBILE_FULL = "screenshot_mobile_full", "Captura mobile (página inteira)"
        LIGHTHOUSE_JSON = "lighthouse_json", "JSON do Lighthouse"
        HTML = "html", "HTML"

    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="artifacts")
    tipo = models.CharField(max_length=30, choices=Kind.choices)
    arquivo = models.FileField(upload_to="artifacts/%Y/%m/", max_length=300)
    tamanho = models.PositiveIntegerField(default=0)
    meta = models.JSONField(default=dict, blank=True)  # ex.: largura/altura em px CSS da captura
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
