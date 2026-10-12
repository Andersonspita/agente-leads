"""Deduplicação de empresas: domínio → telefone → nome parecido no mesmo município (TRD 2.3)."""
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q

from django.conf import settings

from apps.core.text import name_trigrams, normalize_company_name, normalize_phone, trigram_similarity
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
    cnpj: str = ""


def is_shared_domain(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in SHARED_DOMAINS)


class NameIndex:
    """Índice em memória dos nomes das empresas de um município, montado uma vez por busca.

    Usa índice invertido de trigramas: cada comparação olha só as empresas que compartilham
    algum trigrama com o nome novo, em vez de recalcular a similaridade com a cidade inteira.
    """

    def __init__(self, municipality_id):
        self.trigrams: dict[int, set[str]] = {}
        self.inverted: dict[str, set[int]] = defaultdict(set)
        self.cnpjs: dict[int, str] = {}
        for pk, name, cnpj in Company.objects.filter(municipality_id=municipality_id).values_list(
                "id", "nome_normalizado", "cnpj"):
            self.add(pk, name, cnpj)

    def add(self, pk: int, name: str, cnpj: str = ""):
        self.cnpjs[pk] = cnpj
        grams = name_trigrams(name)
        if not grams:
            return
        self.trigrams[pk] = grams
        for g in grams:
            self.inverted[g].add(pk)

    def best_match(self, name: str, cnpj: str = "") -> int | None:
        grams = name_trigrams(name)
        if not grams:
            return None
        shared: dict[int, int] = defaultdict(int)
        for g in grams:
            for pk in self.inverted.get(g, ()):
                if not cnpj or not self.cnpjs.get(pk) or self.cnpjs[pk] == cnpj:  # CNPJs diferentes: outra empresa
                    shared[pk] += 1
        best_pk, best_sim = None, 0.0
        for pk, inter in shared.items():
            sim = inter / (len(grams) + len(self.trigrams[pk]) - inter)
            if sim > best_sim:
                best_pk, best_sim = pk, sim
        return best_pk if best_sim >= NAME_SIMILARITY else None


def find_duplicate(candidate: Candidate, name_index: NameIndex | None = None) -> Company | None:
    # CNPJ é a chave mais forte. Telefone e nome só unem quando os CNPJs não se contradizem: escritórios
    # de contabilidade costumam cadastrar o próprio telefone no CNPJ dos clientes.
    if candidate.cnpj:
        match = Company.objects.filter(cnpj=candidate.cnpj).first()
        if match:
            return match
    compatible = Q(cnpj="") | Q(cnpj=candidate.cnpj) if candidate.cnpj else Q()

    domain = normalize_domain(candidate.site)
    if domain and not is_shared_domain(domain):
        site = Website.objects.select_related("company").filter(dominio=domain).filter(
            **({"company__cnpj__in": ["", candidate.cnpj]} if candidate.cnpj else {})).first()
        if site:
            return site.company

    phone = normalize_phone(candidate.telefone)
    if len(phone) >= 10:
        match = Company.objects.filter(compatible, telefone=phone).first()
        if match:
            return match

    name = normalize_company_name(candidate.nome)
    if not name or not candidate.municipality_id:
        return None
    if name_index is not None:
        pk = name_index.best_match(name, candidate.cnpj)
        return Company.objects.filter(pk=pk).first() if pk else None
    same_city = Company.objects.filter(compatible, municipality_id=candidate.municipality_id)
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
