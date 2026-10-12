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
    content = build_content(lead, None)
    assert content["whatsapp"] == "77991234567"  # celular cadastrado vira candidato a WhatsApp
    assert content["schema_tipo"] == "Dentist"
    assert "Vitória da Conquista" in content["titulo_seo"]
    assert content["agendamento"] is True  # a categoria exige agendamento online
    assert any("WhatsApp" in item for item in content["a_confirmar"])
    assert any("revise" in item.lower() for item in content["a_confirmar"])
    text = json.dumps(content, ensure_ascii=False).lower()
    for invented in ("cro", "anos de experiência", "prêmio", "r$"):
        assert invented not in text


AI_COPY = {"titulo_seo": "Dentista em Vitória da Conquista | Odonto Vida", "descricao_seo": "d" * 130,
           "headline": "Seu sorriso bem cuidado", "subheadline": "Atendimento em Vitória da Conquista",
           "sobre": "A.\n\nB.", "servicos": [{"titulo": "Limpeza", "descricao": "x"}],
           "diferenciais": [{"titulo": "Perto", "descricao": "y"}], "faq": [{"pergunta": "P?", "resposta": "R."}]}


@pytest.mark.django_db
def test_ai_job_rewrites_copy_but_keeps_what_the_analyst_edited(lead):
    from apps.sitebuilder.content import NO_AI_NOTE
    from apps.sitebuilder.tasks import write_site_copy

    project = SiteProject.objects.create(company=lead, conteudo=build_content(lead, None), ia_status="pendente")
    project.conteudo = {**project.conteudo, "sobre": "Texto do analista"}  # editado enquanto a IA escrevia
    project.save()
    with mock.patch("apps.audits.engine.ai.complete_json", return_value=(AI_COPY, "gemini-x")) as call:
        write_site_copy(project.pk)
    project.refresh_from_db()
    assert project.ia_status == "ok" and project.gerado_por_ia and project.modelo_ia == "gemini-x"
    assert project.conteudo["headline"] == "Seu sorriso bem cuidado"
    assert project.conteudo["sobre"] == "Texto do analista"
    assert NO_AI_NOTE not in project.conteudo["a_confirmar"]
    prompt = call.call_args.args[0]
    assert "NÃO invente fatos" in prompt and "Vitória da Conquista" in prompt


@pytest.mark.django_db
def test_ai_job_failure_keeps_base_copy(lead):
    from apps.sitebuilder.tasks import write_site_copy

    content = build_content(lead, None)
    project = SiteProject.objects.create(company=lead, conteudo=content, ia_status="pendente")
    with mock.patch("apps.audits.engine.ai.complete_json", side_effect=TimeoutError("lenta")):
        write_site_copy(project.pk)
    project.refresh_from_db()
    assert project.ia_status == "falhou" and project.conteudo == content and not project.gerado_por_ia


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
    content = build_content(lead, None)
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
    content = build_content(lead, None)
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


@pytest.mark.django_db
def test_site_creation_returns_at_once_and_queues_the_ai(api, lead, settings):
    settings.GEMINI_API_KEY = "x"
    with mock.patch("apps.sitebuilder.views.enqueue") as enqueue, \
            mock.patch("apps.audits.engine.ai.complete_json") as call:
        r = api.post("/api/sites", {"company": lead.pk}, format="json")
    assert r.status_code == 201 and r.data["ia_status"] == "pendente"
    assert not call.called  # a requisição não espera a IA
    assert enqueue.call_args.args[1] == r.data["id"]


@pytest.mark.django_db
def test_editor_rejects_unsafe_links_and_invalid_colors(api, lead):
    pid = SiteProject.objects.create(company=lead, conteudo=build_content(lead, None)).pk
    for bad in ({"instagram": "javascript:alert(1)"}, {"cor": "red;}body{display:none"},
                {"link_agendamento": "agenda.com.br"}, {"servicos": "x"}):
        r = api.patch(f"/api/sites/{pid}", {"conteudo": bad}, format="json")
        assert r.status_code == 400, bad
    r = api.patch(f"/api/sites/{pid}", {"conteudo": {"instagram": "https://instagram.com/odonto", "cor": "#123abc"}},
                  format="json")
    assert r.status_code == 200 and r.data["conteudo"]["cor"] == "#123abc"
