"""Etapa 9 — pontuação.

Nota = Σ w_d · s_d, com Σ w_d = 1 e s_d ∈ [0, 100] (TRD 2.4).

Cada dimensão combina:
- uma nota de base medida por ferramenta (Lighthouse/axe/métricas do navegador), quando existe;
- uma nota de regras: 100 menos as penalidades das regras reprovadas.

Dimensões que não puderam ser medidas ficam como None e seus pesos são
redistribuídos proporcionalmente entre as medidas — o relatório indica isso.
"""
from apps.catalog.models import Dimension, Severity

PENALTY = {Severity.CRITICAL: 45, Severity.HIGH: 25, Severity.MEDIUM: 12, Severity.LOW: 5}
BASE_WEIGHT = 0.6  # participação da nota de ferramenta quando ela existe
AXE_PENALTY = {"critical": 15, "serious": 8, "moderate": 3, "minor": 1}


def clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def linear_score(value: float, good: float, bad: float) -> float:
    """100 quando value <= good, 0 quando value >= bad, linear entre os dois."""
    if value <= good:
        return 100.0
    if value >= bad:
        return 0.0
    return 100.0 * (bad - value) / (bad - good)


def rule_score(outcomes: list[tuple[str, bool]]) -> float | None:
    """outcomes: (severidade, aprovada) das regras medidas na dimensão."""
    if not outcomes:
        return None
    penalty = sum(PENALTY.get(sev, 0) for sev, passed in outcomes if not passed)
    return clamp(100 - penalty)


def base_scores(lighthouse: dict, axe: dict, mobile_metrics: dict | None) -> dict[str, float]:
    base: dict[str, float] = {}
    lh_mobile = (lighthouse.get("mobile") or {}).get("scores", {})
    lh_desktop = (lighthouse.get("desktop") or {}).get("scores", {})

    if "performance" in lh_mobile:
        desktop = lh_desktop.get("performance", lh_mobile["performance"])
        base[Dimension.PERFORMANCE] = 0.7 * lh_mobile["performance"] + 0.3 * desktop
    elif mobile_metrics and mobile_metrics.get("lcp_ms"):
        lcp = linear_score(mobile_metrics["lcp_ms"], 2500, 8000)
        cls = linear_score(mobile_metrics.get("cls") or 0, 0.1, 0.5)
        base[Dimension.PERFORMANCE] = 0.75 * lcp + 0.25 * cls

    if "seo" in lh_mobile:
        base[Dimension.SEO] = lh_mobile["seo"]

    if "accessibility" in lh_mobile:
        base[Dimension.ACCESSIBILITY] = lh_mobile["accessibility"]
    elif axe and "por_impacto" in axe:
        penalty = sum(AXE_PENALTY.get(k, 1) * n for k, n in axe["por_impacto"].items())
        base[Dimension.ACCESSIBILITY] = clamp(100 - penalty)

    if "best-practices" in lh_mobile:
        base[Dimension.SECURITY] = lh_mobile["best-practices"]
    return base


def dimension_scores(rule_results: list[tuple[str, str, bool]], base: dict[str, float]) -> dict[str, int | None]:
    """rule_results: (dimensão, severidade efetiva, aprovada) — só regras medidas."""
    by_dim: dict[str, list[tuple[str, bool]]] = {d.value: [] for d in Dimension}
    for dim, sev, passed in rule_results:
        by_dim[dim].append((sev, passed))

    scores: dict[str, int | None] = {}
    for dim in Dimension:
        rules = rule_score(by_dim[dim.value])
        tool = base.get(dim)
        if tool is not None and rules is not None:
            value = BASE_WEIGHT * tool + (1 - BASE_WEIGHT) * rules
        elif tool is not None:
            value = tool
        else:
            value = rules
        scores[dim.value] = None if value is None else round(value)
    return scores


def overall_score(scores: dict[str, int | None], weights: dict[str, float]) -> int | None:
    measured = {d: s for d, s in scores.items() if s is not None}
    total_weight = sum(weights.get(d, 0) for d in measured)
    if not measured or total_weight <= 0:
        return None
    return round(sum(weights.get(d, 0) * s for d, s in measured.items()) / total_weight)


def score_band(score: int | None) -> dict:
    """Faixas de cor do brief de design (sempre com rótulo textual)."""
    if score is None:
        return {"faixa": "nao_medido", "rotulo": "Não medido"}
    if score < 50:
        return {"faixa": "ruim", "rotulo": "Crítico"}
    if score < 70:
        return {"faixa": "fraco", "rotulo": "Precisa melhorar"}
    if score < 85:
        return {"faixa": "regular", "rotulo": "Regular"}
    return {"faixa": "bom", "rotulo": "Bom"}
