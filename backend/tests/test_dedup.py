import pytest

from apps.core.text import normalize, normalize_company_name, normalize_phone, trigram_similarity
from apps.leads.discovery.dedup import Candidate, find_duplicate, is_shared_domain
from apps.leads.models import Company, Search, SearchResult, Website, normalize_domain
from apps.leads.services import upsert_company


def test_normalizers():
    assert normalize("  Clínica  São João ") == "clinica sao joao"
    assert normalize_company_name("Clínica Odontológica Sorriso LTDA - ME") == "odontologica sorriso"
    assert normalize_phone("+55 (77) 99123-4567") == "77991234567"
    assert normalize_phone("0 77 3422-1100") == "7734221100"
    assert normalize_domain("https://WWW.Exemplo.com.br/contato") == "exemplo.com.br"


def test_trigram_similarity_matches_close_names():
    assert trigram_similarity("odonto sorriso", "odonto sorriso") == 1
    assert trigram_similarity("odonto sorriso", "odonto sorrisso") >= 0.6
    assert trigram_similarity("odonto sorriso", "advocacia silva") < 0.2


def test_shared_domains_are_not_identity():
    assert is_shared_domain("instagram.com")
    assert is_shared_domain("m.facebook.com")
    assert not is_shared_domain("clinicasorriso.com.br")


@pytest.mark.django_db
def test_dedup_by_domain_then_phone_then_name(city):
    company = Company.objects.create(nome="Clínica Sorriso", telefone="(77) 3422-1100", municipality=city)
    Website.objects.create(company=company, url="https://www.clinicasorriso.com.br")

    assert find_duplicate(Candidate("Outro nome", site="http://clinicasorriso.com.br/", municipality_id=city.pk)) == company
    assert find_duplicate(Candidate("Outro nome", telefone="+55 77 3422 1100", municipality_id=city.pk)) == company
    assert find_duplicate(Candidate("Clinica Sorriso Ltda", municipality_id=city.pk)) == company
    assert find_duplicate(Candidate("Advocacia Silva", municipality_id=city.pk)) is None


@pytest.mark.django_db
def test_same_name_in_other_city_is_not_duplicate(city):
    from apps.geo.models import Municipality

    other = Municipality.objects.create(codigo_ibge="2927408", nome="Salvador", uf="BA")
    Company.objects.create(nome="Clínica Sorriso", municipality=city)
    assert find_duplicate(Candidate("Clínica Sorriso", municipality_id=other.pk)) is None


@pytest.mark.django_db
def test_upsert_merges_places_and_cnpj_without_duplicates(city, category):
    search = Search.objects.create(category=category, municipality=city)
    a, created_a = upsert_company({"nome": "Odonto Vida", "telefone": "77 3424-5555", "site": "https://odontovida.com.br",
                                   "nota_google": 4.7, "n_avaliacoes": 88}, search, "places", 1)
    b, created_b = upsert_company({"nome": "ODONTO VIDA LTDA", "cnpj": "12345678000199",
                                   "telefone": "(77) 3424-5555"}, search, "cnpj", 2)
    assert created_a and not created_b
    assert a.pk == b.pk
    a.refresh_from_db()
    assert a.cnpj == "12345678000199"  # completa campos vazios
    assert float(a.nota_google) == 4.7
    assert Company.objects.count() == 1
    assert SearchResult.objects.filter(search=search).count() == 1
    assert a.websites.get().dominio == "odontovida.com.br"


@pytest.mark.django_db
def test_upsert_ignores_social_profile_as_website(city, category):
    search = Search.objects.create(category=category, municipality=city)
    company, _ = upsert_company({"nome": "Studio X", "site": "https://instagram.com/studiox"}, search, "places", 1)
    assert not company.websites.exists()


@pytest.mark.django_db
def test_name_index_matches_like_full_scan(city):
    from apps.leads.discovery.dedup import NameIndex

    a = Company.objects.create(nome="Clínica Sorriso", municipality=city)
    Company.objects.create(nome="Advocacia Silva Pereira", municipality=city)
    index = NameIndex(city.pk)
    assert index.best_match(normalize_company_name("Clinica Sorriso Ltda")) == a.pk
    assert index.best_match(normalize_company_name("Padaria Central")) is None
    novo = Company.objects.create(nome="Padaria Central", municipality=city)
    index.add(novo.pk, novo.nome_normalizado)
    assert index.best_match(normalize_company_name("Padaria Central ME")) == novo.pk
    found = find_duplicate(Candidate("Clinica Sorriso Ltda", municipality_id=city.pk), index)
    assert found == a


@pytest.mark.django_db
def test_different_cnpjs_sharing_the_accountant_phone_stay_separate(city, category):
    search = Search.objects.create(category=category, municipality=city)
    dentist, _ = upsert_company({"nome": "Estacao Oral", "cnpj": "11111111000111", "telefone": "7734240201"},
                                search, "cnpj", 1)
    accountant, created = upsert_company({"nome": "Emafil Contabilidade", "cnpj": "22222222000122",
                                          "telefone": "(77) 3424-0201"}, search, "cnpj", 2)
    assert created and accountant.pk != dentist.pk
    same, created = upsert_company({"nome": "Emafil Contabil Ltda", "cnpj": "22222222000122"}, search, "cnpj", 3)
    assert not created and same.pk == accountant.pk  # mesmo CNPJ: mesma empresa
