"""Busca web complementar para achar o site de empresas que o Places não trouxe.

Usa a Google Programmable Search (Custom Search JSON API) quando
GOOGLE_CSE_ID está configurado; caso contrário, a etapa é ignorada.
"""
import os

import requests

from apps.core import costs
from apps.core.text import normalize_company_name
from apps.leads.models import normalize_domain

from .dedup import is_shared_domain

URL = "https://www.googleapis.com/customsearch/v1"
DIRECTORY_HINTS = ("guia", "lista", "telelistas", "cnpj", "econodata", "solutudo", "encontra", "reclameaqui")


def enabled() -> bool:
    return bool(os.getenv("GOOGLE_CSE_ID") and os.getenv("GOOGLE_CSE_API_KEY"))


def find_website(company_name: str, city: str) -> str | None:
    if not enabled():
        return None
    costs.check_budget()
    resp = requests.get(URL, params={
        "key": os.environ["GOOGLE_CSE_API_KEY"], "cx": os.environ["GOOGLE_CSE_ID"],
        "q": f'"{company_name}" {city}', "num": 5, "gl": "br", "hl": "pt-BR",
    }, timeout=20)
    costs.record("web_search", "custom_search", consulta=company_name)
    if resp.status_code != 200:
        return None
    tokens = [t for t in normalize_company_name(company_name).split() if len(t) >= 4]
    for item in resp.json().get("items", []):
        domain = normalize_domain(item.get("link", ""))
        if not domain or is_shared_domain(domain) or any(h in domain for h in DIRECTORY_HINTS):
            continue
        compact = domain.replace("-", "")
        if any(t in compact for t in tokens):
            return f"https://{domain}"
    return None
