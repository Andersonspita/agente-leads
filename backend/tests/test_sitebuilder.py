"""Gerador de site novo: conteúdo, renderização, API, prévia e regras do auditor sobre o site gerado."""
import io
import json
import zipfile
from unittest import mock

import pytest
from django.test import Client

from apps.audits.engine import rules
from apps.audits.engine.context import AuditContext
from apps.audits.engine.crawler import CrawlResult, Page
from apps.leads.models import Company, Website
from apps.sitebuilder.content import build_content
from apps.sitebuilder.models import SiteProject
from apps.sitebuilder.render import build_zip, render_files


@pytest.fixture
def lead(city, category):
    return Company.objects.create(nome="Odonto Vida", municipality=city, category=category, telefone="77991234567",
                                  endereco="Rua Siqueira Campos 85", bairro="Centro", nota_google=4.8,
                                  n_avaliacoes=37, redes_sociais={"instagram": "https://instagram.com/odontovida"})


@pytest.mark.django_db
def test_content_without_ai_is_neutral_and_lists_what_to_confirm(lead):
    content, by_ai, _ = build_content(lead, None)
    assert not by_ai
    assert content["whatsapp"] == "77991234567"  # celular cadastrado vira candidato a WhatsApp
    assert content["schema_tipo"] == "Dentist"
    assert "Vitória da Conquista" in content["titulo_seo"]
    assert content["agendamento"] is True  # a categoria exige agendamento online
    assert any("WhatsApp" in item for item in content["a_confirmar"])
    assert any("revise" in item.lower() for item in content["a_confirmar"])
    text = json.dumps(content, ensure_ascii=False).lower()
    for invented in ("cro", "anos de experiência", "prêmio", "r$"):
        assert invented not in text


@pytest.mark.django_db
def test_content_uses_ai_copy_when_available(settings, lead):
    settings.GEMINI_API_KEY = "x"
    copy = {"titulo_seo": "Dentista em Vitória da Conquista | Odonto Vida", "descricao_seo": "d" * 130,
            "headline": "Seu sorriso bem cuidado", "subheadline": "Atendimento em Vitória da Conquista",
            "sobre": "A.\n\nB.", "servicos": [{"titulo": "Limpeza", "descricao": "x"}],
            "diferenciais": [{"titulo": "Perto", "descricao": "y"}], "faq": [{"pergunta": "P?", "resposta": "R."}]}
    with mock.patch("apps.audits.engine.ai.complete_json", return_value=(copy, "gemini-x")) as call:
        content, by_ai, model = build_content(lead, None)
    assert by_ai and model == "gemini-x" and content["headline"] == "Seu sorriso bem cuidado"
    prompt = call.call_args.args[0]
    assert "NÃO invente fatos" in prompt and "Vitória da Conquista" in prompt


@pytest.mark.django_db
def test_slow_ai_falls_back_to_base_copy(settings, lead, monkeypatch):
    import threading

    from apps.sitebuilder import content as content_mod

    settings.GEMINI_API_KEY = "x"
    monkeypatch.setattr(content_mod, "AI_WAIT_SECONDS", 0.2)
    release = threading.Event()
    with mock.patch("apps.audits.engine.ai.complete_json", side_effect=lambda *a: release.wait(5)):
        content, by_ai, _ = build_content(lead, None)
    release.set()
    assert not by_ai and content["headline"]  # não espera a IA lenta: sai com os textos-base


def _ctx_from(files, base="http://127.0.0.1:8000/s/tok/"):
    html = files["index.html"][0].decode()
    page = Page(url=base, final_url=base, status=200, headers={"content-type": "text/html"}, html=html, elapsed_ms=50)
    priv = Page(url=base + "politica-de-privacidade.html", final_url=base + "politica-de-privacidade.html",
                status=200, headers={"content-type": "text/html"},
                html=files["politica-de-privacidade.html"][0].decode(), elapsed_ms=50)
    crawl = CrawlResult(base, [page, priv], robots_txt=files["robots.txt"][0].decode(), robots_allows_home=True,
                        sitemap_urls=[])
    from apps.audits.engine import tech

    return AuditContext(url=base, crawl=crawl, city="Vitória da Conquista", checklist=["Agendamento online"],
                        tech=tech.detect(html, {}))


@pytest.mark.django_db
def test_generated_site_passes_content_seo_conversion_and_lgpd_rules(lead):
    content, _, _ = build_content(lead, None)
    files = render_files(content, "http://127.0.0.1:8000/s/tok/")
    assert {"index.html", "politica-de-privacidade.html", "robots.txt", "sitemap.xml", "favicon.svg",
            "img/destaque.svg", "img/sobre.svg", "img/contato.svg"} <= set(files)
    ctx = _ctx_from(files)
    failed = {r.code for r in rules.RULES if (o := r.check(ctx)) is not None and not o.passed}
    assert failed == set(), failed
    html = files["index.html"][0].decode()
    assert "https://wa.me/5577991234567" in html and 'href="tel:+5577991234567"' in html
    assert '"@type": ["LocalBusiness", "Dentist"]' in html and '"ratingValue": 4.8' in html
    assert "4,8 no Google" in html


@pytest.mark.django_db
def test_zip_contains_site_and_readme(lead):
    content, _, _ = build_content(lead, None)
    zf = zipfile.ZipFile(io.BytesIO(build_zip(content, "http://x/s/t/")))
    assert "index.html" in zf.namelist() and "LEIA-ME.txt" in zf.namelist()
    assert "Itens a confirmar" in zf.read("LEIA-ME.txt").decode()


@pytest.mark.django_db
def test_site_api_preview_and_robots(api, lead, settings):
    settings.SITES_BASE_URL = "http://127.0.0.1:8000"
    settings.PUBLIC_BASE_URL = "http://localhost:8000"
    r = api.post("/api/sites", {"company": lead.pk}, format="json")
    assert r.status_code == 201
    pid, token = r.data["id"], r.data["token"]
    assert r.data["preview_url"] == f"http://127.0.0.1:8000/s/{token}/"

    r = api.patch(f"/api/sites/{pid}", {"conteudo": {"headline": "Novo título", "hackeado": "x"}}, format="json")
    assert r.data["conteudo"]["headline"] == "Novo título" and "hackeado" not in r.data["conteudo"]
    assert r.data["conteudo"]["empresa"] == "Odonto Vida"  # campos não enviados são preservados

    anon = Client()
    page = anon.get(f"/s/{token}/")
    assert page.status_code == 200 and "Novo título" in page.content.decode()
    assert page["X-Frame-Options"] == "SAMEORIGIN"
    assert anon.get(f"/s/{token}/img/destaque.svg")["Content-Type"] == "image/svg+xml"
    assert anon.get(f"/s/{token}/../../admin").status_code == 404
    assert anon.get("/s/inexistente/").status_code == 404

    assert "Allow: /s/" in anon.get("/robots.txt", HTTP_HOST="127.0.0.1:8000").content.decode()
    assert anon.get("/robots.txt", HTTP_HOST="localhost:8000").content == b"User-agent: *\nDisallow: /\n"

    z = api.get(f"/api/sites/{pid}/download")
    assert z.status_code == 200 and z["Content-Type"] == "application/zip"

    with mock.patch("apps.audits.views.enqueue"):
        r = api.post(f"/api/sites/{pid}/audit")
    assert r.status_code == 202
    site = SiteProject.objects.get(pk=pid).website
    assert site.origem == "gerado" and site.dominio == f"gerado:s/{token}" and not site.principal
    assert Website.objects.filter(company=lead, origem="gerado").count() == 1
