"""Regras de conteúdo/conversão/LGPD/SEO avaliadas sobre HTML de exemplo (sem rede)."""
from types import SimpleNamespace

import pytest

from apps.audits.engine import rules
from apps.audits.engine.context import AuditContext
from apps.audits.engine.crawler import CrawlResult, Page

GOOD_HTML = """<!doctype html><html lang="pt-BR"><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clínica Sorriso — Dentista em Vitória da Conquista</title>
<meta name="description" content="Clínica odontológica em Vitória da Conquista com implantes, ortodontia e agendamento online.">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Dentist","name":"Clínica Sorriso"}</script>
</head><body>
<header><nav><a href="/sobre">Quem somos</a><a href="/contato">Contato</a><a href="/privacidade">Política de Privacidade</a></nav></header>
<h1>Dentista em Vitória da Conquista</h1>
<p>Atendimento de segunda a sexta, das 8h às 18h. Rua Siqueira Campos, 123 - Centro, CEP 45000-000.</p>
<a href="tel:+557734221100">(77) 3422-1100</a>
<a href="https://wa.me/5577991234567">WhatsApp</a>
<a href="https://maps.app.goo.gl/abc">Como chegar</a>
<a href="https://instagram.com/clinicasorriso">Instagram</a>
<a href="https://agenda.example.com/agendar">Agendar consulta</a>
<section><h2>Depoimentos</h2><p>O que nossos pacientes dizem...</p></section>
<form><input type="text" name="nome"><input type="tel" name="fone"><textarea></textarea>
<label><input type="checkbox"> Concordo com a política de privacidade</label></form>
<img src="a.jpg" alt="Recepção"><img src="b.jpg" alt="Consultório">
<p>""" + "Texto sobre tratamentos odontológicos. " * 40 + """</p>
<footer>© 2026 Clínica Sorriso</footer>
</body></html>"""

BAD_HTML = """<html><head><title>Home</title></head><body>
<h1>Bem-vindo</h1><h1>Nosso site</h1>
<p>Em breve mais informações.</p><img src="x.jpg"><img src="y.jpg">
<form><input type="email" name="email"><button>Enviar</button></form>
<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>
<footer>Copyright 2015</footer></body></html>"""


def make_ctx(html, **extra):
    page = Page(url="https://exemplo.com.br/", final_url="https://exemplo.com.br/", status=200,
                headers={"content-type": "text/html"}, html=html, elapsed_ms=100)
    crawl = CrawlResult("https://exemplo.com.br/", [page], robots_txt="User-agent: *\nAllow: /\n",
                        robots_allows_home=True, sitemap_urls=[])
    from apps.audits.engine import tech

    ctx = AuditContext(url=page.final_url, crawl=crawl, city="Vitória da Conquista",
                       checklist=["Agendamento online"], tech=tech.detect(html, page.headers), **extra)
    return ctx


def outcomes(ctx):
    return {r.code: r.check(ctx) for r in rules.RULES}


def failed(ctx):
    return {code for code, out in outcomes(ctx).items() if out is not None and not out.passed}


def test_rule_catalog_is_consistent():
    codes = [r.code for r in rules.RULES]
    assert len(codes) == len(set(codes)), "códigos de regra duplicados"
    assert len(codes) >= 30
    for r in rules.RULES:
        assert r.impact and r.improvement, f"{r.code} sem impacto/melhoria"


def test_good_site_passes_content_conversion_and_lgpd_rules():
    bad = failed(make_ctx(GOOD_HTML))
    for code in ("MOB-001", "SEO-001", "SEO-002", "SEO-003", "SEO-006", "SEO-007", "CONT-001", "CONT-002",
                 "CONT-003", "CONT-004", "CONT-005", "CONT-007", "CONV-001", "CONV-002", "CONV-004", "CONV-005",
                 "CONV-006", "CONV-007", "LGPD-001", "LGPD-003", "A11Y-002"):
        assert code not in bad, code


def test_bad_site_fails_expected_rules():
    bad = failed(make_ctx(BAD_HTML))
    expected = {"MOB-001", "SEO-001", "SEO-002", "SEO-003", "SEO-006", "SEO-007", "SEO-009", "CONT-001", "CONT-002",
                "CONT-004", "CONT-008", "CONV-001", "CONV-006", "LGPD-001", "LGPD-002", "LGPD-003", "A11Y-002"}
    assert expected <= bad


def test_rules_without_data_are_not_measured():
    ctx = AuditContext(url="https://x")  # nada rastreado
    assert all(out is None for out in outcomes(ctx).values())


def test_templates_render_measured_values():
    ctx = make_ctx(BAD_HTML)
    ctx.browser = SimpleNamespace(
        mobile=SimpleNamespace(metrics={"lcp_ms": 9100}, layout={"ctas": [], "overflow_horizontal": True},
                               bytes_total=7_200_000, requests=40),
        desktop=None, axe={},
    )
    rule = next(r for r in rules.RULES if r.code == "PERF-001")
    out = rule.check(ctx)
    assert not out.passed and out.severity == "critica"
    assert rule.render(rule.title, out) == "O site leva 9,1 s para mostrar o conteúdo principal no celular"
    weight = next(r for r in rules.RULES if r.code == "PERF-002")
    assert "7,2 MB" in weight.render(weight.title, weight.check(ctx))
    assert "CONV-003" in failed(ctx) and "MOB-002" in failed(ctx)


@pytest.mark.parametrize("robots,blocked", [
    ("User-agent: *\nDisallow: /\n", True),
    ("User-agent: *\nDisallow: /admin\n", False),
])
def test_robots_rule(robots, blocked):
    ctx = make_ctx(GOOD_HTML)
    ctx.crawl.robots_txt = robots
    out = next(r for r in rules.RULES if r.code == "SEO-005").check(ctx)
    assert out.passed is (not blocked)


def test_tech_detection_flags_outdated_wordpress():
    from apps.audits.engine import tech

    html = '<meta name="generator" content="WordPress 5.2.1"><link href="/wp-content/themes/x.css">' \
           '<script src="/wp-includes/js/jquery/jquery-1.12.4.min.js"></script>'
    found = tech.detect(html, {})
    names = {t["nome"]: t for t in found["tecnologias"]}
    assert found["cms"] == "WordPress"
    assert names["WordPress"]["versao"] == "5.2.1" and names["WordPress"]["desatualizado"]
    assert names["jQuery"]["desatualizado"]
