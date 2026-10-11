import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Category
from apps.geo.models import Municipality


@pytest.fixture(autouse=True)
def _settings(settings, tmp_path):
    settings.REQUIRE_2FA = False
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.CELERY_BROKER_URL = ""
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = ""
    settings.AI_PROVIDER = ""
    settings.AI_BASE_URL = ""
    settings.GOOGLE_PLACES_API_KEY = ""
    settings.OSM_ENABLED = False  # testes não acessam a internet


@pytest.fixture
def city(db):
    return Municipality.objects.create(codigo_ibge="2933307", nome="Vitória da Conquista", uf="BA")


@pytest.fixture
def category(db):
    cat = Category.objects.create(nome="Clínica odontológica", slug="clinica-odontologica",
                                  termos_busca=["dentista"], cnaes=["8630-5/04"])
    cat.checklist.create(item="Agendamento online", tipo="integracao")
    return cat


@pytest.fixture
def analyst(db):
    return User.objects.create_user(email="analista@example.com", password="senha-muito-forte-1", role="analista")


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(email="admin@example.com", password="senha-muito-forte-1", role="admin")


@pytest.fixture
def api(analyst):
    client = APIClient()
    client.force_authenticate(analyst)
    return client


@pytest.fixture
def admin_api(admin_user):
    client = APIClient()
    client.force_authenticate(admin_user)
    return client
