"""Deduplicação de empresas: domínio → telefone → nome parecido no mesmo município (TRD 2.3)."""
from dataclasses import dataclass

from django.conf import settings

from apps.core.text import normalize_company_name, normalize_phone, trigram_similarity
from apps.leads.models import Company, Website, normalize_domain

NAME_SIMILARITY = 0.8

# Domínios que não identificam a empresa (redes sociais, diretórios, construtores genéricos).
SHARED_DOMAINS = {
    "facebook.com", "instagram.com", "linktr.ee", "wa.me", "api.whatsapp.com", "google.com", "goo.gl",
    "business.site", "doctoralia.com.br", "linkedin.com", "youtube.com", "tiktok.com", "guiamais.com.br",
    "apontador.com.br", "yelp.com", "sites.google.com", "bit.ly",
}


@dataclass
class Candidate:
    nome: str
    telefone: str = ""
    site: str = ""
    municipality_id: str | None = None


def is_shared_domain(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in SHARED_DOMAINS)


def find_duplicate(candidate: Candidate) -> Company | None:
    domain = normalize_domain(candidate.site)
    if domain and not is_shared_domain(domain):
        site = Website.objects.select_related("company").filter(dominio=domain).first()
        if site:
            return site.company

    phone = normalize_phone(candidate.telefone)
    if len(phone) >= 10:
        match = Company.objects.filter(telefone=phone).first()
        if match:
            return match

    name = normalize_company_name(candidate.nome)
    if not name or not candidate.municipality_id:
        return None
    same_city = Company.objects.filter(municipality_id=candidate.municipality_id)
    if settings.IS_POSTGRES:
        from django.contrib.postgres.search import TrigramSimilarity

        match = (
            same_city.annotate(sim=TrigramSimilarity("nome_normalizado", name))
            .filter(sim__gte=NAME_SIMILARITY)
            .order_by("-sim")
            .first()
        )
        return match
    best, best_sim = None, 0.0
    for company in same_city.only("id", "nome_normalizado"):
        sim = trigram_similarity(name, company.nome_normalizado)
        if sim > best_sim:
            best, best_sim = company, sim
    return best if best_sim >= NAME_SIMILARITY else None
