"""Fontes gratuitas: OpenStreetMap e descoberta do site pelo domínio do e-mail do CNPJ."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import pytest
import requests

from apps.leads.discovery import osm, site_finder
from apps.leads.models import CnpjEstablishment, Company, LeadStatus, Search, Website
from apps.leads.services import probe_email_domain, run_search

# ---------------------------------------------------------------- domínio do e-mail


@pytest.mark.parametrize("email,domain", [
    ("contato@clinicasorriso.com.br", "clinicasorriso.com.br"),
    ("  Recepcao@OdontoVida.COM ", "odontovida.com"),
    ("fulano@gmail.com", ""),
    ("fulano@hotmail.com.br", ""),
    ("x@bol.com.br", ""),
    ("sem-arroba", ""),
    ("a@b@c.com", ""),
    ("", ""),
])
def test_email_domain(email, domain):
    assert site_finder.email_domain(email) == domain


def test_belongs_to_company_rejects_accountant_site():
    accountant = "<html><title>Contábil Alfa — Contabilidade</title><body>Abertura de empresas</body></html>"
    assert not site_finder.belongs_to_company("contabilalfa.com.br", accountant, ["Odonto Sorriso"])
    own = "<html><title>Sorriso Odontologia</title><body>Implantes em Vitória da Conquista</body></html>"
    assert site_finder.belongs_to_company("clinicaxyz.com.br", own, ["Odonto Sorriso"], "Vitória da Conquista")
    # nome só no texto e página de outra cidade (franquia/homônima): recusado
    other_city = "<html><title>Sorriso Odontologia</title><body>Unidade Angra dos Reis</body></html>"
    assert not site_finder.belongs_to_company("rede.com.br", other_city, ["Odonto Sorriso"], "Vitória da Conquista")
    # nome da cidade e nomes de pessoa não servem de prova
    page = "<html><body>SEST SENAT Vitória da Conquista - José Lima Barros</body></html>"
    assert not site_finder.belongs_to_company(
        "sestsenat.org.br", page, ["Vitoria Da Conquista/Ba - Jose De Lima Barros"], "Vitória da Conquista")
    assert site_finder.belongs_to_company("sorrisoodonto.com.br", "<html></html>", ["Clínica Sorriso Ltda"])
    # nomes só com palavras genéricas não identificam a empresa
    assert not site_finder.belongs_to_company("x.com.br", "<p>clinica odontologica</p>", ["Clínica Odontológica"])


def test_parked_domain_detection():
    assert site_finder.looks_parked("<h1>This domain is for sale!</h1>")
    assert site_finder.looks_parked("<title>Apache2 Ubuntu Default Page</title>")
    assert not site_finder.looks_parked("<h1>Clínica Sorriso</h1>")


# ---------------------------------------------------------------- OpenStreetMap


def test_osm_query_uses_ibge_code_and_ignores_bad_tags():
    q = osm.build_query("2933307", ["amenity=dentist", 'bad"];out;', "healthcare=dentist"], "")
    assert 'area["IBGE:GEOCODIGO"="2933307"]' in q
    assert 'nwr["amenity"="dentist"](area.a);' in q and 'nwr["healthcare"="dentist"](area.a);' in q
    assert "bad" not in q
    assert osm.build_query("1", [], "") == ""
    assert '["name"~' in osm.build_query("1", [], 'odonto "vida"')


def test_osm_parse_element():
    item = osm.parse_element({"type": "node", "id": 7, "tags": {
        "name": "Dental Slim", "contact:website": "https://dentalslim.com.br", "phone": "+55 77 3421-0000",
        "addr:street": "Avenida Luís Eduardo Magalhães", "addr:housenumber": "1495", "addr:suburb": "Candeias",
        "contact:instagram": "@dentalslim",
    }})
    assert item["nome"] == "Dental Slim" and item["site"] == "https://dentalslim.com.br"
    assert item["endereco"] == "Avenida Luís Eduardo Magalhães 1495" and item["bairro"] == "Candeias"
    assert item["redes_sociais"]["instagram"] == "https://instagram.com/dentalslim"
    assert osm.parse_element({"type": "node", "id": 8, "tags": {"amenity": "dentist"}}) is None  # sem nome


def _resp(status, payload=None):
    r = mock.Mock(status_code=status)
    r.json.return_value = payload or {}
    r.raise_for_status.side_effect = None if status < 400 else requests.HTTPError(str(status))
    return r


def test_osm_falls_back_to_next_server(settings):
    settings.OSM_ENABLED = True
    settings.OVERPASS_URLS = ["https://a/api", "https://b/api"]
    ok = _resp(200, {"elements": [{"type": "node", "id": 1, "tags": {"name": "Odonto X"}}]})
    with mock.patch("requests.post", side_effect=[_resp(504), ok]) as post:
        items = osm.search("2933307", ["amenity=dentist"])
    assert [i["nome"] for i in items] == ["Odonto X"] and post.call_count == 2
    with mock.patch("requests.post", side_effect=[_resp(429), requests.ConnectionError()]), \
         pytest.raises(osm.OsmUnavailable):
        osm.search("2933307", ["amenity=dentist"])


# ---------------------------------------------------------------- busca completa só com fontes gratuitas


@pytest.mark.django_db
def test_free_search_merges_osm_and_cnpj_and_queues_email_probes(settings, city, category):
    settings.OSM_ENABLED = True
    category.osm_tags = ["amenity=dentist"]
    category.save()
    CnpjEstablishment.objects.create(cnpj="11222333000144", nome_fantasia="Odonto Vida", cnae_principal="8630504",
                                     municipality=city, uf="BA", telefone="7734001234",
                                     dominio_email="odontovida.com.br")
    CnpjEstablishment.objects.create(cnpj="99888777000166", nome_fantasia="Sorriso Kids", cnae_principal="8630504",
                                     municipality=city, uf="BA")
    osm_items = [{"nome": "Odonto Vida", "telefone": "(77) 3400-1234", "site": "", "_raw": {"osm": "node/1"}},
                 {"nome": "Dental Slim", "site": "dentalslim.com.br", "_raw": {"osm": "node/2"}}]
    search = Search.objects.create(category=category, municipality=city)
    with mock.patch.object(osm, "search", return_value=osm_items), \
         mock.patch("apps.leads.services.enqueue") as enqueue:
        run_search(search)

    assert search.fontes["osm"] == 2 and search.fontes["cnpj"] == 2
    assert Company.objects.count() == 3  # "Odonto Vida" do OSM e do CNPJ é a mesma empresa (telefone)
    slim = Website.objects.get(dominio="dentalslim.com.br")
    assert slim.origem == "osm"
    probe_calls = [c for c in enqueue.call_args_list if c.args[0].name.endswith("probe_email_domain")]
    assert len(probe_calls) == 1 and probe_calls[0].args[2] == "odontovida.com.br"
    assert search.fontes["sites_por_email"] == 1
    assert Company.objects.get(nome="Sorriso Kids").status_lead == LeadStatus.NO_SITE


# ---------------------------------------------------------------- verificação do domínio contra um servidor local


class SiteHandler(BaseHTTPRequestHandler):
    body = ""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(SiteHandler.body.encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def local_domain():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SiteHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.django_db
@pytest.mark.parametrize("body,accepted", [
    ("<html><title>Consultório Vida Plena</title><body>Agende em Vitória da Conquista</body></html>", True),
    ("<html><title>Contábil Alfa</title><body>Contabilidade para empresas</body></html>", False),
    ("<html><body>This domain is for sale</body></html>", False),
])
def test_probe_email_domain(local_domain, city, body, accepted):
    SiteHandler.body = body
    company = Company.objects.create(nome="Odonto Vida", municipality=city, status_lead=LeadStatus.NO_SITE)
    with mock.patch("apps.leads.services.enqueue_enrich"):
        website = probe_email_domain(company, local_domain, ["Vida Plena", "Vida Plena Odontologia Ltda"])
    company.refresh_from_db()
    if accepted:
        assert website and website.origem == "email_cnpj" and website.online
        assert company.status_lead == LeadStatus.FOUND
    else:
        assert website is None and not company.websites.exists()
        assert company.status_lead == LeadStatus.NO_SITE
