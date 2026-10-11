"""Registro e teto mensal de custos de APIs pagas (TRD 2.7 / RF14)."""
import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import ApiUsage

logger = logging.getLogger(__name__)

# Estimativas em R$ por chamada; ajuste conforme a fatura real.
UNIT_COST_BRL = {
    ("google_places", "text_search"): Decimal("0.20"),
    ("google_places", "place_details"): Decimal("0.10"),
}
USD_BRL = Decimal("5.50")
# US$ por milhão de tokens (entrada, saída) — tabela de preços da Anthropic.
ANTHROPIC_PRICES_USD = {
    "claude-opus-5": (Decimal("5"), Decimal("25")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-4-5": (Decimal("1"), Decimal("5")),
}


class BudgetExceeded(Exception):
    pass


def month_spend() -> Decimal:
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = ApiUsage.objects.filter(data__gte=start).aggregate(t=Sum("custo_estimado"))["t"]
    return total or Decimal("0")


def check_budget():
    budget = Decimal(str(settings.MONTHLY_API_BUDGET_BRL))
    spent = month_spend()
    if spent >= budget:
        raise BudgetExceeded(f"Teto mensal de APIs atingido (R$ {spent:.2f} de R$ {budget:.2f}).")
    return spent, budget


def record(provedor, endpoint, custo=None, **detalhes):
    if custo is None:
        custo = UNIT_COST_BRL.get((provedor, endpoint), Decimal("0"))
    ApiUsage.objects.create(provedor=provedor, endpoint=endpoint, custo_estimado=custo, detalhes=detalhes)
    spent = month_spend()
    budget = Decimal(str(settings.MONTHLY_API_BUDGET_BRL))
    if budget and spent >= budget * Decimal("0.8"):
        logger.warning("Custo de APIs em %.0f%% do teto mensal", spent / budget * 100)


def anthropic_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    price_in, price_out = ANTHROPIC_PRICES_USD.get(model, ANTHROPIC_PRICES_USD["claude-opus-5"])
    usd = (Decimal(input_tokens) * price_in + Decimal(output_tokens) * price_out) / Decimal(1_000_000)
    return (usd * USD_BRL).quantize(Decimal("0.0001"))
