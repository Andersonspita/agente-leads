"""Motor de auditoria de ponta a ponta contra um site servido localmente (sem internet)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.audits.engine import ai, lighthouse, runner
from apps.audits.engine.crawler import Crawler, check_url
from apps.audits.models import STEPS, Audit, AuditStep, Finding
from apps.leads.models import Company, LeadStatus, Website

HOME = """<!doctype html><html lang="pt-BR"><head><title>Home</title></head><body>
<nav><a href="/contato">Contato</a><a href="/sobre">Sobre nós</a><a href="/privado/x">Privado</a>
<a href="https://outro-site.com/">Externo</a><a href="/arquivo.pdf">PDF</a></nav>
<h1>Clínica Exemplo</h1><p>Atendimento de segunda a sexta. © 2019</p>
<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script></body></html>"""
CONTACT = """<html><body><h1>Contato</h1><a href="tel:7734221100">(77) 3422-1100</a>
<form><input type="email"><textarea></textarea></form></body></html>"""
ABOUT = "<html><body><h1>Sobre</h1><p>Quem somos.</p></body></html>"
ROBOTS = "User-agent: *\nDisallow: /privado/\nSitemap: http://127.0.0.1/sitemap.xml\n"


class Handler(BaseHTTPRequestHandler):
    pages = {"/": HOME, "/contato": CONTACT, "/sobre": ABOUT, "/robots.txt": ROBOTS}
    hits: list[str] = []

    def do_GET(self):  # noqa: N802
        Handler.hits.append(self.path)
        body = self.pages.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        ctype = "text/plain" if self.path.endswith(".txt") else "text/html; charset=utf-8"
        self.send_header("Content-Type", ctype)
        self.send_header("Server", "Apache/2.4.1")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def site(settings):
    settings.CRAWLER_MIN_INTERVAL = 0
    Handler.hits = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_crawler_respects_robots_and_stays_on_domain(site):
    result = Crawler().crawl(site + "/")
    urls = {p.final_url.replace(site, "") for p in result.pages}
    assert urls == {"/", "/contato", "/sobre"}
    assert "/privado/x" not in Handler.hits  # bloqueado pelo robots.txt
    assert not any("pdf" in h for h in Handler.hits)
    assert result.robots_allows_home and result.sitemap_urls
    assert check_url(site)["status_http"] == 200


def test_crawler_stops_when_robots_forbids_everything(site):
    Handler.pages = {**Handler.pages, "/robots.txt": "User-agent: *\nDisallow: /\n"}
    try:
        result = Crawler().crawl(site + "/")
        assert not result.robots_allows_home and len(result.pages) == 1
    finally:
        Handler.pages = {**Handler.pages, "/robots.txt": ROBOTS}


@pytest.mark.django_db
def test_full_audit_runs_steps_scores_and_marks_lead(site, city, category):
    company = Company.objects.create(nome="Clínica Exemplo", municipality=city, category=category)
    website = Website.objects.create(company=company, url=site + "/")
    audit = Audit.objects.create(website=website)
    fake_security = {"https": False, "http_redireciona_https": None, "certificado": {"sem_https": True},
                     "cabecalhos": {"HSTS": False, "CSP": False, "X-Frame-Options": False,
                                    "X-Content-Type-Options": False, "Referrer-Policy": False},
                     "versoes_expostas": {"server": "Apache/2.4.1"}, "conteudo_misto": []}
    with mock.patch.object(runner, "browser_available", return_value=False), \
         mock.patch.object(runner, "lighthouse_command", return_value=None), \
         mock.patch.object(runner.security, "check_security", return_value=fake_security):
        runner.AuditRunner(audit).run()

    audit.refresh_from_db()
    steps = {s.etapa: s.status for s in audit.steps.all()}
    assert audit.status == Audit.Status.DONE
    assert steps["rastreio"] == "ok" and steps["conteudo"] == "ok" and steps["pontuacao"] == "ok"
    assert steps["capturas"] == "nao_medido" and steps["lighthouse"] == "nao_medido" and steps["ia"] == "nao_medido"
    codes = set(audit.findings.values_list("rule_id", flat=True))
    assert {"SEC-001", "SEC-006", "CONV-001", "LGPD-001", "LGPD-002", "CONT-004"} <= codes
    assert "CONT-001" not in codes and "CONV-002" not in codes  # telefone e formulário na página de contato
    assert audit.nota_geral is not None and 0 <= audit.nota_geral <= 100
    assert audit.notas_dimensao["seguranca"] is not None
    assert all(f.status_revisao == Finding.Review.CONFIRMED for f in audit.findings.all())
    company.refresh_from_db()
    assert company.status_lead == LeadStatus.AUDITED


@pytest.mark.django_db
def test_audit_of_offline_site_fails_gracefully(city):
    company = Company.objects.create(nome="Fora do Ar", municipality=city)
    website = Website.objects.create(company=company, url="http://127.0.0.1:9/")
    audit = Audit.objects.create(website=website)
    runner.AuditRunner(audit).run()
    audit.refresh_from_db()
    website.refresh_from_db()
    assert audit.status == Audit.Status.FAILED and "fora do ar" in audit.erro.lower()
    assert website.online is False
    assert audit.steps.filter(status="nao_medido").count() == 8


def _fake_response(text, stop="end_turn"):
    return SimpleNamespace(
        stop_reason=stop, model="claude-opus-5",
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        content=[SimpleNamespace(type="text", text=text)],
    )


AI_OK = json.dumps({
    "resumo": "Site datado.", "pontos_fortes": ["Boa localização"],
    "achados": [{"dimensao": "conteudo", "severidade": "media", "titulo": "Visual datado",
                 "descricao": "Layout antigo", "impacto_negocio": "Passa pouca confiança",
                 "melhoria_proposta": "Layout moderno", "captura": "desktop", "local_na_captura": "topo"}],
})


@pytest.mark.django_db
def test_ai_analysis_retries_invalid_json_and_creates_pending_findings(settings, city):
    settings.ANTHROPIC_API_KEY = "sk-test"
    company = Company.objects.create(nome="Clínica", municipality=city)
    audit = Audit.objects.create(website=Website.objects.create(company=company, url="https://c.com.br"))
    step = AuditStep.objects.create(audit=audit, etapa="ia", ordem=8)
    client = mock.MagicMock()
    client.beta.messages.create.side_effect = [_fake_response("{inválido"), _fake_response(AI_OK)]
    ctx = SimpleNamespace(desktop=SimpleNamespace(fold_png=b"png"), mobile=None, pages=[])
    with mock.patch("anthropic.Anthropic", return_value=client):
        runner.run_ai_analysis(audit, ctx, step)
    assert client.beta.messages.create.call_count == 2
    kwargs = client.beta.messages.create.call_args.kwargs
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    finding = audit.findings.get()
    assert finding.origem == "ia" and finding.status_revisao == "pendente"
    assert step.resultado["pontos_fortes"] == ["Boa localização"]
    from apps.core.models import ApiUsage

    assert ApiUsage.objects.filter(provedor="anthropic").count() == 2


@pytest.mark.django_db
def test_ai_gives_up_after_second_invalid_answer_and_handles_refusal(settings):
    settings.ANTHROPIC_API_KEY = "sk-test"
    client = mock.MagicMock()
    client.beta.messages.create.side_effect = [_fake_response("x"), _fake_response("y")]
    kwargs = dict(empresa="X", categoria="", cidade="", desktop_png=None, mobile_png=None, texto="t",
                  achados_regras=[])
    with mock.patch("anthropic.Anthropic", return_value=client), pytest.raises(ai.AIInvalidOutput):
        ai.analyze(**kwargs)
    client.beta.messages.create.side_effect = [_fake_response("", stop="refusal")]
    with mock.patch("anthropic.Anthropic", return_value=client), pytest.raises(ai.AIInvalidOutput):
        ai.analyze(**kwargs)


def test_ai_output_validation():
    with pytest.raises(ai.AIInvalidOutput):
        ai.validate({"achados": [{"dimensao": "seguranca", "severidade": "alta", "titulo": "x"}]})  # IA não avalia segurança
    assert ai.validate(json.loads(AI_OK))["achados"][0]["titulo"] == "Visual datado"


def test_lighthouse_summary_and_median(settings, tmp_path):
    lighthouse.LOCK_PATH = tmp_path / "lighthouse.lock"  # trava isolada do resto da máquina
    report = {
        "categories": {"performance": {"score": 0.42}, "seo": {"score": 0.9}},
        "audits": {"largest-contentful-paint": {"numericValue": 6100.0},
                   "total-byte-weight": {"numericValue": 3_400_000},
                   "render-blocking": {"id": "render-blocking", "title": "Bloqueio", "score": 0.3,
                                       "details": {"type": "opportunity", "overallSavingsMs": 900}}},
    }
    summary = lighthouse.summarize(report)
    assert summary["scores"] == {"performance": 42, "seo": 90}
    assert summary["metricas"]["lcp_ms"] == 6100.0
    assert summary["oportunidades"][0]["id"] == "render-blocking"

    runs = iter([0.3, 0.9, 0.5] * 2)

    def fake_run(cmd, url, preset, timeout):
        return {**report, "categories": {"performance": {"score": next(runs)}}}

    with mock.patch.object(lighthouse, "lighthouse_command", return_value=["lighthouse"]), \
         mock.patch.object(lighthouse, "_run_once", side_effect=fake_run):
        result = lighthouse.run_lighthouse("https://x", runs=3)
    assert result["mobile"]["scores"]["performance"] == 50  # mediana de 30, 90, 50
    assert result["desktop"]["scores"]["performance"] == 50
    assert not lighthouse.LOCK_PATH.exists()  # a trava é liberada depois de cada execução


@pytest.mark.django_db
def test_ai_via_gemini_openai_compatible_endpoint(settings):
    settings.GEMINI_API_KEY = "chave-teste"
    settings.AI_MODEL = "gemini-2.5-flash"
    ok = mock.Mock(status_code=200)
    ok.json.return_value = {"model": "gemini-2.5-flash", "usage": {"prompt_tokens": 900, "completion_tokens": 300},
                            "choices": [{"finish_reason": "stop", "message": {"content": f"```json\n{AI_OK}\n```"}}]}
    with mock.patch("requests.post", return_value=ok) as post:
        data = ai.analyze(empresa="X", categoria="", cidade="", desktop_png=b"png", mobile_png=None, texto="t",
                          achados_regras=[])
    assert ai.provider() == "gemini" and data["achados"][0]["titulo"] == "Visual datado"
    url = post.call_args.args[0]
    body = post.call_args.kwargs["json"]
    assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer chave-teste"
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    from apps.core.models import ApiUsage

    usage = ApiUsage.objects.get()
    assert usage.provedor == "gemini" and usage.custo_estimado == 0

    limited = mock.Mock(status_code=429, text="quota")
    with mock.patch("requests.post", return_value=limited), pytest.raises(ai.AIUnavailable):
        ai.analyze(empresa="X", categoria="", cidade="", desktop_png=None, mobile_png=None, texto="t",
                   achados_regras=[])


@pytest.mark.django_db
def test_audit_finishes_with_score_and_queues_ai_separately(site, city, category, settings):
    settings.GEMINI_API_KEY = "x"
    company = Company.objects.create(nome="Clínica Exemplo", municipality=city, category=category)
    audit = Audit.objects.create(website=Website.objects.create(company=company, url=site + "/"))
    with mock.patch.object(runner, "browser_available", return_value=False), \
         mock.patch.object(runner, "lighthouse_command", return_value=None), \
         mock.patch.object(runner.security, "check_security", return_value={}), \
         mock.patch("apps.core.jobs.enqueue") as enqueue:
        runner.AuditRunner(audit).run()
    audit.refresh_from_db()
    assert audit.status == Audit.Status.DONE and audit.nota_geral is not None
    assert audit.steps.get(etapa="ia").status == "pendente"
    assert enqueue.call_args.args[0].name.endswith("ai_analysis") and enqueue.call_args.args[1] == audit.pk
    textos = audit.steps.get(etapa="rastreio").resultado["textos"]
    assert textos and "Clínica Exemplo" in textos[0]["texto"]
