from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class Dimension(models.TextChoices):
    PERFORMANCE = "desempenho", "Desempenho"
    MOBILE = "mobile", "Mobile e responsividade"
    SEO = "seo", "SEO técnico e local"
    ACCESSIBILITY = "acessibilidade", "Acessibilidade"
    SECURITY = "seguranca", "Segurança"
    CONTENT = "conteudo", "Conteúdo e credibilidade"
    CONVERSION = "conversao", "Conversão"
    COMPLIANCE = "conformidade", "Conformidade (LGPD)"


DEFAULT_WEIGHTS = {
    Dimension.PERFORMANCE: Decimal("0.15"),
    Dimension.MOBILE: Decimal("0.15"),
    Dimension.SEO: Decimal("0.15"),
    Dimension.ACCESSIBILITY: Decimal("0.10"),
    Dimension.SECURITY: Decimal("0.10"),
    Dimension.CONTENT: Decimal("0.10"),
    Dimension.CONVERSION: Decimal("0.15"),
    Dimension.COMPLIANCE: Decimal("0.10"),
}


class Severity(models.TextChoices):
    CRITICAL = "critica", "Crítica"
    HIGH = "alta", "Alta"
    MEDIUM = "media", "Média"
    LOW = "baixa", "Baixa"


class Category(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    termos_busca = models.JSONField(default=list, help_text="Termos usados na busca do Google Places")
    cnaes = models.JSONField(default=list, blank=True, help_text="Ex.: ['8630-5/04']")
    osm_tags = models.JSONField(
        default=list, blank=True, help_text="Tags do OpenStreetMap, ex.: ['amenity=dentist', 'healthcare=dentist']"
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "categoria"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating:
            CategoryWeight.objects.bulk_create(
                [CategoryWeight(category=self, dimensao=d, peso=w) for d, w in DEFAULT_WEIGHTS.items()],
                ignore_conflicts=True,
            )

    def weights(self) -> dict[str, float]:
        stored = {w.dimensao: float(w.peso) for w in self.pesos.all()}
        return {d.value: stored.get(d.value, float(DEFAULT_WEIGHTS[d])) for d in Dimension}


class CategoryWeight(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="pesos")
    dimensao = models.CharField(max_length=20, choices=Dimension.choices)
    peso = models.DecimalField(max_digits=4, decimal_places=3)

    class Meta:
        unique_together = [("category", "dimensao")]


def validate_weights(weights: dict[str, float]):
    """Pesos precisam cobrir as 8 dimensões e somar 1 (TRD 2.4)."""
    missing = set(Dimension.values) - set(weights)
    if missing:
        raise ValidationError(f"Faltam pesos para: {', '.join(sorted(missing))}")
    if any(w < 0 for w in weights.values()):
        raise ValidationError("Pesos não podem ser negativos.")
    if abs(sum(weights.values()) - 1) > 0.001:
        raise ValidationError(f"Os pesos somam {sum(weights.values()):.3f}; precisam somar 1.")


class CategoryChecklistItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="checklist")
    item = models.CharField(max_length=160)
    obrigatorio = models.BooleanField(default=True)
    tipo = models.CharField(
        max_length=20,
        choices=[("pagina", "Página"), ("secao", "Seção"), ("integracao", "Integração"), ("meta", "Meta")],
        default="secao",
    )

    class Meta:
        ordering = ["tipo", "id"]


class Rule(models.Model):
    """Catálogo de regras automáticas (ex.: SEC-001 “Site sem HTTPS”)."""

    codigo = models.CharField(max_length=12, unique=True)
    dimensao = models.CharField(max_length=20, choices=Dimension.choices)
    descricao = models.CharField(max_length=200)
    severidade_padrao = models.CharField(max_length=10, choices=Severity.choices)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} {self.descricao}"
