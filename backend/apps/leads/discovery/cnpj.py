"""Base aberta de CNPJ (Receita Federal): revela empresas fora do Google e sem site."""
from django.db.models import Q

from apps.core.text import only_digits
from apps.leads.models import CnpjEstablishment


def cnae_digits(cnae: str) -> str:
    return only_digits(cnae)[:7]


def search(municipality_id: str, cnaes: list[str], limit: int = 2000) -> list[dict]:
    codes = [cnae_digits(c) for c in cnaes if cnae_digits(c)]
    if not codes:
        return []
    secondary = Q()
    for code in codes:
        secondary |= Q(cnaes_secundarios__contains=code)
    qs = CnpjEstablishment.objects.filter(municipality_id=municipality_id).filter(
        Q(cnae_principal__in=codes) | secondary
    )[:limit]
    return [
        {
            "nome": est.nome,
            "cnpj": est.cnpj,
            "endereco": est.endereco,
            "bairro": est.bairro,
            "telefone": est.telefone,
            "site": "",
            "dominio_email": est.dominio_email,
            "nomes": [n for n in (est.nome_fantasia, est.razao_social) if n],
            "_raw": {"cnpj": est.cnpj, "cnae": est.cnae_principal, "razao_social": est.razao_social},
        }
        for est in qs
    ]
