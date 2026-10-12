"""Regras de negócio da prospecção: busca, gravação de empresas e enriquecimento."""
import logging
import re
from datetime import timedelta

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.jobs import enqueue
from apps.core.text import normalize_phone

from .discovery import cnpj, osm, places, websearch
from .discovery.dedup import Candidate, NameIndex, find_duplicate, is_shared_domain
from .models import Company, DoNotContact, LeadStatus, Search, SearchResult, Website, normalize_domain

logger = logging.getLogger(__name__)

SOCIAL_PATTERNS = {
    "instagram": r"instagram\.com/[A-Za-z0-9_.]+",
    "facebook": r"facebook\.com/[A-Za-z0-9_.\-]+",
    "linkedin": r"linkedin\.com/(?:company|in)/[A-Za-z0-9_\-]+",
    "youtube": r"youtube\.com/(?:@|channel/|c/)[A-Za-z0-9_\-]+",
}
WHATSAPP_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\d{10,13})")


def search_terms(search: Search) -> list[str]:
    if search.termo_livre:
        return [search.termo_livre]
    if search.category and search.category.termos_busca:
        return search.category.termos_busca
    return [search.category.nome] if search.category else []


def cached_search(search: Search) -> Search | None:
    """Mesma categoria/termo/cidade concluída nos últimos 30 dias: reaproveita (economiza API paga)."""
    since = timezone.now() - timedelta(days=settings.SEARCH_CACHE_DAYS)
    return (
        Search.objects.filter(
            category=search.category, municipality=search.municipality, termo_livre=search.termo_livre,
            status=Search.Status.DONE, concluido_em__gte=since,
        )
        .exclude(pk=search.pk)
        .order_by("-concluido_em")
        .first()
    )


SITE_ORIGIN = {"places": "places", "osm": "osm", "web": "web", "manual": "manual"}


def upsert_company(data: dict, search: Search, fonte: str, posicao: int,
                   name_index: NameIndex | None = None) -> tuple[Company, bool]:
    candidate = Candidate(
        nome=data["nome"], telefone=data.get("telefone", ""), site=data.get("site", ""),
        municipality_id=search.municipality_id, cnpj=data.get("cnpj") or "",
    )
    company = find_duplicate(candidate, name_index)
    created = company is None
    if created:
        company = Company(
            nome=data["nome"][:200], municipality=search.municipality, category=search.category,
        )
    # Completa campos vazios sem sobrescrever o que já foi preenchido/curado.
    for field in ("endereco", "bairro", "telefone", "google_place_id", "cnpj"):
        if data.get(field) and not getattr(company, field):
            setattr(company, field, str(data[field])[: Company._meta.get_field(field).max_length])
    if data.get("whatsapp") and not company.whatsapp:
        company.whatsapp = normalize_phone(data["whatsapp"])
    if data.get("redes_sociais"):
        company.redes_sociais = {**data["redes_sociais"], **(company.redes_sociais or {})}
    if data.get("nota_google") is not None:
        company.nota_google = round(float(data["nota_google"]), 1)
        company.n_avaliacoes = data.get("n_avaliacoes")
    if not company.category and search.category:
        company.category = search.category
    company.save()
    if name_index is not None:
        name_index.add(company.pk, company.nome_normalizado, company.cnpj)

    site = data.get("site")
    if site and not is_shared_domain(normalize_domain(site)):
        domain = normalize_domain(site)
        website = Website.objects.filter(dominio=domain).first()
        if website is None:
            if "://" not in site:
                site = "https://" + site
            website = Website.objects.create(company=company, url=site[:500], origem=SITE_ORIGIN.get(fonte, ""),
                                             principal=not company.websites.exists())
            enqueue_enrich(website)
    SearchResult.objects.update_or_create(
        search=search, company=company,
        defaults={"fonte": fonte, "posicao": posicao, "payload_bruto": data.get("_raw", {})},
    )
    return company, created


def enqueue_enrich(website: Website):
    from .tasks import enrich_website

    enqueue(enrich_website, website.pk)


BATCH_SIZE = 100


def batched(items, size=BATCH_SIZE):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def run_search(search: Search) -> Search:
    search.status = Search.Status.RUNNING
    search.save(update_fields=["status"])
    fontes = {"places": 0, "osm": 0, "cnpj": 0, "web": 0, "sites_por_email": 0, "erros": [], "avisos": []}
    posicao = 0
    email_probes: list[tuple[int, str, list[str]]] = []
    name_index = NameIndex(search.municipality_id)  # deduplicação por nome sem varrer a cidade a cada empresa
    blocked = DoNotContact.matcher(search.municipality_id)  # LGPD: quem pediu exclusão não volta

    # O cache de 30 dias vale só para o Google Places (pago). As fontes gratuitas são sempre consultadas,
    # para refletir, por exemplo, uma base CNPJ recém-importada.
    previous = cached_search(search) if settings.GOOGLE_PLACES_API_KEY else None
    city = f"{search.municipality.nome}, {search.municipality.uf}"
    bairro = f" {search.bairro}" if search.bairro else ""
    if previous:
        for result in previous.results.filter(fonte=SearchResult.Source.PLACES):
            posicao = max(posicao, result.posicao)
            SearchResult.objects.get_or_create(
                search=search, company=result.company,
                defaults={"fonte": result.fonte, "posicao": result.posicao, "payload_bruto": result.payload_bruto},
            )
            fontes["places"] += 1
        fontes["cache_de"] = previous.pk
    else:
        try:
            seen_places = set()
            for term in search_terms(search):
                for item in places.text_search(f"{term}{bairro} em {city}"):
                    if item["google_place_id"] in seen_places or blocked(item):
                        continue
                    seen_places.add(item["google_place_id"])
                    posicao += 1
                    with transaction.atomic():
                        upsert_company(item, search, SearchResult.Source.PLACES, posicao, name_index)
                    fontes["places"] += 1
        except places.PlacesUnavailable:
            fontes["avisos"].append("Google Places não configurado: usando só as fontes gratuitas.")
        except requests.RequestException as exc:
            fontes["erros"].append(f"Google Places: {str(exc)[:200]}")
        except Exception as exc:  # teto de custo, etc.
            fontes["erros"].append(str(exc)[:200])

    # OpenStreetMap: gratuito, complementar (a cobertura varia por cidade).
    osm_tags = search.category.osm_tags if search.category else []
    if osm_tags or search.termo_livre:
        try:
            items = [i for i in osm.search(search.municipality_id, osm_tags, search.termo_livre)
                     if (not search.bairro or search.bairro.lower() in (i.get("bairro") or "").lower())
                     and not blocked(i)]
            for batch in batched(items):  # um commit por lote: bem mais rápido que um por empresa
                with transaction.atomic():
                    for item in batch:
                        posicao += 1
                        upsert_company(item, search, SearchResult.Source.OSM, posicao, name_index)
                        fontes["osm"] += 1
        except osm.OsmUnavailable as exc:
            fontes["avisos"].append(str(exc)[:300])

    cnaes = search.category.cnaes if search.category else []
    items = [i for i in cnpj.search(search.municipality_id, cnaes)
             if (not search.bairro or search.bairro.lower() in (i.get("bairro") or "").lower()) and not blocked(i)]
    for batch in batched(items):
        with transaction.atomic():
            for item in batch:
                posicao += 1
                company, _ = upsert_company(item, search, SearchResult.Source.CNPJ, posicao, name_index)
                fontes["cnpj"] += 1
                if item.get("dominio_email") and settings.EMAIL_DOMAIN_DISCOVERY:
                    email_probes.append((company.pk, item["dominio_email"], item.get("nomes") or [item["nome"]]))

    if websearch.enabled():
        no_site = Company.objects.filter(search_results__search=search, websites__isnull=True)[:30]
        for company in no_site:
            try:
                url = websearch.find_website(company.nome, search.municipality.nome)
            except Exception as exc:
                fontes["erros"].append(f"Busca web: {str(exc)[:120]}")
                break
            if url and not Website.objects.filter(dominio=normalize_domain(url)).exists():
                website = Website.objects.create(company=company, url=url, origem="web")
                enqueue_enrich(website)
                fontes["web"] += 1

    # Empresas sem site pulam a auditoria (App Flow 3.1).
    Company.objects.filter(
        search_results__search=search, websites__isnull=True, status_lead=LeadStatus.FOUND
    ).update(status_lead=LeadStatus.NO_SITE)

    # Testa em segundo plano o domínio do e-mail do CNPJ como possível site (gratuito).
    from .tasks import probe_email_domain

    for company_id, domain, names in email_probes:
        if not Website.objects.filter(company_id=company_id).exists():
            enqueue(probe_email_domain, company_id, domain, names)
            fontes["sites_por_email"] += 1

    search.total_encontrado = search.results.count()
    search.fontes = fontes
    search.status = Search.Status.DONE if search.total_encontrado or not fontes["erros"] else Search.Status.FAILED
    search.erro = "; ".join(fontes["erros"]) if search.status == Search.Status.FAILED else ""
    search.concluido_em = timezone.now()
    search.save()
    return search


def enrich_website(website: Website):
    from apps.audits.engine.crawler import check_url

    info = check_url(website.url)
    website.ultimo_check = timezone.now()
    website.online = info.get("online", False)
    website.status_http = info.get("status_http")
    website.https = info.get("https")
    website.url_final = (info.get("url_final") or "")[:500]
    website.save()

    html = info.get("html") or ""
    if not html:
        return website
    company = website.company
    soup = BeautifulSoup(html, "lxml")
    hrefs = " ".join(a.get("href", "") for a in soup.find_all("a", href=True))
    social = dict(company.redes_sociais or {})
    for name, pattern in SOCIAL_PATTERNS.items():
        m = re.search(pattern, hrefs, re.I)
        if m and name not in social:
            social[name] = "https://" + m.group(0)
    company.redes_sociais = social
    wa = WHATSAPP_RE.search(hrefs)
    if wa and not company.whatsapp:
        company.whatsapp = normalize_phone(wa.group(1))
    company.save()
    return website


def probe_email_domain(company: Company, domain: str, names: list[str]) -> Website | None:
    """Aceita o domínio do e-mail do CNPJ como site só se ele responder e for mesmo da empresa."""
    from apps.audits.engine.crawler import check_url

    from .discovery.site_finder import belongs_to_company, looks_parked

    if company.websites.exists() or Website.objects.filter(dominio=domain).exists():
        return None
    if DoNotContact.is_blocked_domain(domain):
        return None
    for candidate in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
        info = check_url(candidate)
        if not info.get("online") or (info.get("status_http") or 500) >= 400:
            continue
        html = info.get("html") or ""
        city = company.municipality.nome if company.municipality_id else ""
        if not html or looks_parked(html) or not belongs_to_company(domain, html, names or [company.nome], city):
            return None
        final = info.get("url_final") or candidate
        if Website.objects.filter(dominio=normalize_domain(final)).exists():
            return None
        website = Website.objects.create(
            company=company, url=final[:500], origem="email_cnpj", principal=True, online=True,
            https=info.get("https"), status_http=info.get("status_http"), url_final=final[:500],
            ultimo_check=timezone.now(),
        )
        if company.status_lead == LeadStatus.NO_SITE:
            company.status_lead = LeadStatus.FOUND
            company.save(update_fields=["status_lead", "atualizado_em"])
        enqueue_enrich(website)  # redes sociais e WhatsApp linkados no site
        return website
    return None
