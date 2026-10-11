"""OpenStreetMap via API Overpass: fonte gratuita e complementar da descoberta.

Filtra pelo código IBGE do município (tag IBGE:GEOCODIGO das fronteiras brasileiras
no OSM) e pelas tags da categoria (ex.: amenity=dentist). A cobertura varia muito
por cidade; em cidades menores costuma trazer só o nome e o endereço.

Os servidores públicos do Overpass pedem uso moderado: uma consulta por busca,
User-Agent identificado e troca de servidor quando um deles está sobrecarregado.
"""
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"^[a-z_:]+=[\w:;\-]+$", re.I)


class OsmUnavailable(Exception):
    pass


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_query(ibge_code: str, tags: list[str], name_term: str = "") -> str:
    filters = []
    for tag in tags:
        if not TAG_RE.match(tag.strip()):
            continue  # ignora tags mal formadas vindas da configuração
        key, value = tag.strip().split("=", 1)
        filters.append(f'nwr["{_escape(key)}"="{_escape(value)}"](area.a);')
    if name_term:
        filters.append(f'nwr["name"~"{_escape(re.escape(name_term))}",i](area.a);')
    if not filters:
        return ""
    return (
        f'[out:json][timeout:60];area["IBGE:GEOCODIGO"="{_escape(ibge_code)}"]->.a;'
        f'({"".join(filters)});out center tags;'
    )


def parse_element(element: dict) -> dict | None:
    tags = element.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return None
    street = " ".join(p for p in (tags.get("addr:street"), tags.get("addr:housenumber")) if p)
    social = {}
    for net in ("instagram", "facebook"):
        handle = tags.get(f"contact:{net}")
        if handle:
            social[net] = handle if handle.startswith("http") else f"https://{net}.com/{handle.lstrip('@')}"
    return {
        "nome": name,
        "site": tags.get("website") or tags.get("contact:website") or tags.get("url") or "",
        "telefone": tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or "",
        "whatsapp": tags.get("contact:whatsapp") or "",
        "endereco": street,
        "bairro": tags.get("addr:suburb") or tags.get("addr:neighbourhood") or "",
        "redes_sociais": social,
        "_raw": {"osm": f"{element.get('type')}/{element.get('id')}", "tags": tags},
    }


def search(ibge_code: str, tags: list[str], name_term: str = "") -> list[dict]:
    if not settings.OSM_ENABLED:
        raise OsmUnavailable("OpenStreetMap desativado (OSM_ENABLED=false)")
    query = build_query(ibge_code, tags, name_term)
    if not query:
        return []
    errors = []
    for url in settings.OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, timeout=90,
                                 headers={"User-Agent": settings.CRAWLER_USER_AGENT})
        except requests.RequestException as exc:
            errors.append(f"{url}: {type(exc).__name__}")
            continue
        if resp.status_code in (429, 502, 503, 504):
            errors.append(f"{url}: servidor ocupado ({resp.status_code})")
            continue
        try:
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
        except (requests.HTTPError, ValueError) as exc:
            errors.append(f"{url}: {str(exc)[:120]}")
            continue
        return [item for item in map(parse_element, elements) if item]
    raise OsmUnavailable("OpenStreetMap indisponível agora: " + "; ".join(errors))
