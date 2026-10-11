"""Descobre o site da empresa pelo domínio do e-mail cadastrado na Receita.

Ex.: e-mail cadastral contato@clinicasorriso.com.br → testa https://clinicasorriso.com.br.

Cuidados:
- provedores gratuitos (gmail, hotmail…) são ignorados;
- muitas empresas cadastram o e-mail do escritório de contabilidade, então o site
  só é aceito se o nome da empresa aparecer no domínio, no título ou no texto da página;
- domínios estacionados/à venda e páginas padrão de hospedagem são descartados.
"""
import re

from bs4 import BeautifulSoup

from apps.core.text import normalize, normalize_company_name

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br", "live.com",
    "msn.com", "yahoo.com", "yahoo.com.br", "ymail.com", "icloud.com", "me.com", "bol.com.br", "uol.com.br",
    "terra.com.br", "ig.com.br", "globo.com", "globomail.com", "r7.com", "zipmail.com.br", "oi.com.br",
    "protonmail.com", "proton.me", "aol.com", "gmx.com", "zoho.com", "yandex.com", "click21.com.br",
    "superig.com.br", "pop.com.br", "brturbo.com.br", "veloxmail.com.br", "email.com", "mail.com",
}
# Palavras comuns demais para identificar uma empresa pelo nome.
GENERIC_WORDS = {
    "clinica", "odontologia", "odontologica", "odontologico", "odonto", "consultorio", "escritorio", "advocacia",
    "advogados", "associados", "contabilidade", "contabil", "contadores", "servicos", "comercio", "restaurante",
    "construtora", "construcoes", "imobiliaria", "imoveis", "salao", "beleza", "centro", "medico", "medica",
    "medicos", "saude", "empresa", "grupo", "brasil", "silva", "santos", "souza", "oliveira", "dental", "estetica",
    "assessoria", "consultoria", "engenharia", "comercial", "industria", "loja", "bahia", "nordeste",
    "mais", "novo", "nova", "super", "center", "clinic", "prime", "premium", "total", "geral", "especializada",
    "especializado", "integrada", "integrado", "popular", "express", "servico", "oral", "odontologicos",
    "odontologicas", "medicina", "cirurgica", "cirurgico", "instituto", "unidade", "atendimento",
}
# Nomes e sobrenomes muito comuns: não identificam uma empresa (ex.: "José de Lima Barros").
COMMON_PERSON_NAMES = {
    "jose", "joao", "maria", "ana", "antonio", "francisco", "carlos", "paulo", "pedro", "lucas", "luiz", "luis",
    "marcos", "gabriel", "rafael", "daniel", "marcelo", "bruno", "eduardo", "felipe", "rodrigo", "manoel", "manuel",
    "fernanda", "juliana", "patricia", "aline", "camila", "amanda", "bruna", "jessica", "leticia", "julia", "adriana",
    "lima", "barros", "costa", "pereira", "ferreira", "alves", "rodrigues", "gomes", "martins", "araujo", "ribeiro",
    "carvalho", "almeida", "lopes", "soares", "fernandes", "vieira", "barbosa", "rocha", "dias", "nascimento",
    "andrade", "moreira", "nunes", "marques", "machado", "mendes", "freitas", "cardoso", "ramos", "goncalves",
    "santana", "teixeira", "moura", "cunha", "miranda", "neto", "filho", "junior", "sobrinho",
}
PARKED_HINTS = (
    "domain is for sale", "este dominio esta a venda", "comprar este dominio", "dominio a venda", "buy this domain",
    "parkingcrew", "sedoparking", "bodis.com", "default web site page", "apache2 ubuntu default page",
    "welcome to nginx", "it works!", "index of /", "hostgator", "account suspended", "conta suspensa",
    "this domain has been registered", "dominio registrado",
)


def email_domain(email: str) -> str:
    """Domínio corporativo do e-mail, ou "" para provedores gratuitos e valores inválidos."""
    email = (email or "").strip().lower()
    if email.count("@") != 1:
        return ""
    domain = email.split("@", 1)[1].strip(". ")
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", domain):
        return ""
    if domain in FREE_EMAIL_DOMAINS or any(domain.endswith("." + d) for d in FREE_EMAIL_DOMAINS):
        return ""
    return domain


def distinctive_tokens(company_name: str, city: str = "") -> list[str]:
    ignore = GENERIC_WORDS | COMMON_PERSON_NAMES | set(normalize(city).split())
    return [t for t in normalize_company_name(company_name).split() if len(t) >= 4 and t not in ignore]


def looks_parked(html: str) -> bool:
    text = normalize(html[:20000])
    return any(normalize(h) in text for h in PARKED_HINTS)


def belongs_to_company(domain: str, html: str, company_names: list[str], city: str = "") -> bool:
    """O site pertence à empresa (e não, por exemplo, ao escritório de contabilidade dela)?

    - Nome da empresa no domínio: aceito (ex.: coifeodonto.com.br para "Coife Odonto").
    - Nome só no texto da página: aceito apenas se a página também citar a cidade da empresa,
      para não confundir com uma franquia ou homônima de outra cidade.
    - O nome da cidade e nomes de pessoa comuns não contam como prova.
    """
    compact_domain = domain.split(".")[0].replace("-", "")
    soup = BeautifulSoup((html or "")[:300000], "lxml")
    title = soup.title.get_text(" ") if soup.title else ""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    page = normalize(f"{title} {soup.get_text(' ')[:30000]}")
    city_on_page = bool(city) and normalize(city) in page
    for name in company_names:
        tokens = distinctive_tokens(name, city)
        if any(t in compact_domain for t in tokens):
            return True
        if city_on_page and any(re.search(rf"\b{re.escape(t)}\b", page) for t in tokens):
            return True
    return False
