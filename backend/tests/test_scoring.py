import pytest
from django.core.exceptions import ValidationError

from apps.audits.engine import scoring
from apps.catalog.models import DEFAULT_WEIGHTS, Dimension, Severity, validate_weights

WEIGHTS = {d.value: float(w) for d, w in DEFAULT_WEIGHTS.items()}


def test_default_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1)


def test_rule_score_penalties_and_floor():
    assert scoring.rule_score([]) is None
    assert scoring.rule_score([(Severity.LOW, True)]) == 100
    assert scoring.rule_score([(Severity.HIGH, False), (Severity.LOW, False)]) == 70
    assert scoring.rule_score([(Severity.CRITICAL, False)] * 3) == 0


def test_linear_score():
    assert scoring.linear_score(2000, 2500, 8000) == 100
    assert scoring.linear_score(8000, 2500, 8000) == 0
    assert scoring.linear_score(5250, 2500, 8000) == pytest.approx(50)


def test_dimension_blends_tool_and_rules():
    rules = [(Dimension.PERFORMANCE.value, Severity.HIGH, False)]  # regra: 75
    base = {Dimension.PERFORMANCE: 50}
    dims = scoring.dimension_scores(rules, base)
    assert dims["desempenho"] == round(0.6 * 50 + 0.4 * 75)
    assert dims["seguranca"] is None  # nada medido


def test_overall_is_weighted_sum_when_all_measured():
    scores = {d: 80 for d in WEIGHTS}
    scores["desempenho"] = 40
    expected = sum(WEIGHTS[d] * s for d, s in scores.items())
    assert scoring.overall_score(scores, WEIGHTS) == round(expected)


def test_overall_redistributes_unmeasured_weights():
    scores = {d: None for d in WEIGHTS}
    scores["seo"] = 60
    scores["conversao"] = 90
    w = WEIGHTS["seo"] + WEIGHTS["conversao"]
    expected = (WEIGHTS["seo"] * 60 + WEIGHTS["conversao"] * 90) / w
    assert scoring.overall_score(scores, WEIGHTS) == round(expected)
    assert scoring.overall_score({d: None for d in WEIGHTS}, WEIGHTS) is None


def test_base_scores_prefers_lighthouse_and_falls_back_to_field_metrics():
    lh = {"mobile": {"scores": {"performance": 40, "seo": 90, "accessibility": 70, "best-practices": 80}},
          "desktop": {"scores": {"performance": 80}}}
    base = scoring.base_scores(lh, {}, None)
    assert base[Dimension.PERFORMANCE] == pytest.approx(0.7 * 40 + 0.3 * 80)
    assert base[Dimension.SEO] == 90

    base = scoring.base_scores({}, {"por_impacto": {"critical": 1, "serious": 2}}, {"lcp_ms": 2000, "cls": 0.05})
    assert base[Dimension.PERFORMANCE] == 100
    assert base[Dimension.ACCESSIBILITY] == 100 - 15 - 16


@pytest.mark.parametrize("score,band", [(None, "nao_medido"), (0, "ruim"), (49, "ruim"), (50, "fraco"),
                                        (69, "fraco"), (70, "regular"), (84, "regular"), (85, "bom"), (100, "bom")])
def test_score_bands_match_design_brief(score, band):
    assert scoring.score_band(score)["faixa"] == band
    assert scoring.score_band(score)["rotulo"]  # sempre com rótulo textual


def test_validate_weights():
    validate_weights(WEIGHTS)
    with pytest.raises(ValidationError):
        validate_weights({**WEIGHTS, "seo": 0.5})
    with pytest.raises(ValidationError):
        validate_weights({k: v for k, v in WEIGHTS.items() if k != "seo"})
