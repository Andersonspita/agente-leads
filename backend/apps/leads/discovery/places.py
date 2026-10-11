"""Google Places API (New) — Text Search. Fonte principal da descoberta."""
import logging

import requests
from django.conf import settings

from apps.core import costs

logger = logging.getLogger(__name__)

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.addressComponents",
    "places.nationalPhoneNumber", "places.internationalPhoneNumber", "places.websiteUri",
    "places.rating", "places.userRatingCount", "places.businessStatus", "nextPageToken",
])
MAX_PAGES = 3  # 20 resultados por página


class PlacesUnavailable(Exception):
    pass


def _component(place, kind):
    for comp in place.get("addressComponents", []):
        if kind in comp.get("types", []):
            return comp.get("longText", "")
    return ""


def parse_place(place: dict) -> dict:
    return {
        "nome": place.get("displayName", {}).get("text", ""),
        "endereco": place.get("formattedAddress", ""),
        "bairro": _component(place, "sublocality_level_1") or _component(place, "sublocality"),
        "telefone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber") or "",
        "site": place.get("websiteUri", ""),
        "google_place_id": place.get("id", ""),
        "nota_google": place.get("rating"),
        "n_avaliacoes": place.get("userRatingCount"),
        "fechado": place.get("businessStatus") == "CLOSED_PERMANENTLY",
    }


def text_search(query: str, max_pages: int = MAX_PAGES) -> list[dict]:
    if not settings.GOOGLE_PLACES_API_KEY:
        raise PlacesUnavailable("GOOGLE_PLACES_API_KEY não configurada")
    headers = {
        "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": FIELDS,
        "Content-Type": "application/json",
    }
    body = {"textQuery": query, "languageCode": "pt-BR", "regionCode": "BR", "pageSize": 20}
    results = []
    for _ in range(max_pages):
        costs.check_budget()
        resp = requests.post(URL, json=body, headers=headers, timeout=30)
        costs.record("google_places", "text_search", consulta=query)
        resp.raise_for_status()
        data = resp.json()
        for place in data.get("places", []):
            parsed = parse_place(place)
            if not parsed["fechado"]:
                results.append({**parsed, "_raw": place})
        token = data.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
    return results
