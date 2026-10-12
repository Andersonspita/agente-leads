import secrets

from django.conf import settings
from django.db import models

from apps.audits.models import Audit
from apps.leads.models import Company, Website


def new_token():
    return secrets.token_urlsafe(16)


class SiteProject(models.Model):
    """Site novo gerado para um lead a partir do diagnóstico (versão editável pelo analista)."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="site_projects")
    audit_origem = models.ForeignKey(Audit, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                     help_text="Auditoria do site atual usada como diagnóstico")
    token = models.CharField(max_length=40, unique=True, default=new_token)
    conteudo = models.JSONField(default=dict)
    gerado_por_ia = models.BooleanField(default=False)
    modelo_ia = models.CharField(max_length=60, blank=True)
    ia_status = models.CharField(max_length=10, blank=True,
                                 help_text="Textos pela IA em segundo plano: pendente, ok ou falhou")
    website = models.OneToOneField(Website, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                   help_text="Registro usado para auditar o site gerado")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "site gerado"

    def __str__(self):
        return f"Site novo de {self.company}"

    @property
    def preview_url(self):
        return f"{settings.SITES_BASE_URL.rstrip('/')}/s/{self.token}/"
