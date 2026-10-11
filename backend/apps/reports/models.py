import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.audits.models import Audit
from apps.leads.models import Company


def new_token():
    return secrets.token_urlsafe(32)  # 32 bytes aleatórios (TRD 2.6)


def default_expiry():
    return timezone.now() + timedelta(days=settings.REPORT_DEFAULT_EXPIRY_DAYS)


class Report(models.Model):
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name="reports")
    token = models.CharField(max_length=64, unique=True, default=new_token)
    expira_em = models.DateTimeField(default=default_expiry)
    pdf = models.FileField(upload_to="reports/%Y/%m/", blank=True, max_length=300)
    pdf_status = models.CharField(max_length=12, default="pendente")
    texto_abertura = models.TextField(blank=True)
    resumo = models.TextField(blank=True, help_text="Resumo em 3 frases")
    concorrentes_ids = models.JSONField(default=list, blank=True)
    exibir_nomes_concorrentes = models.BooleanField(default=False)
    achados_ids = models.JSONField(default=list, blank=True, help_text="Ordem dos achados no relatório")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    revogado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "relatório"

    @property
    def company(self):
        return self.audit.website.company

    @property
    def is_available(self):
        return not self.revogado and self.expira_em > timezone.now()

    @property
    def public_url(self):
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/r/{self.token}"


class ReportView(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="views")
    visto_em = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=300, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-visto_em"]


class Briefing(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="briefings")
    audit = models.ForeignKey(Audit, null=True, blank=True, on_delete=models.SET_NULL)
    conteudo = models.JSONField(default=dict)
    versao = models.PositiveSmallIntegerField(default=1)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
