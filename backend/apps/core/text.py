import re
import unicodedata

_COMPANY_SUFFIXES = re.compile(
    r"\b(ltda|me|epp|eireli|s\.?a\.?|sa|ss|clinica|clínica|consultorio|consultório|dr|dra)\b\.?"
)


def normalize(text: str) -> str:
    """Minúsculas, sem acentos e com espaços simples."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def normalize_company_name(name: str) -> str:
    """Nome normalizado para deduplicação: sem sufixos societários e palavras genéricas."""
    text = normalize(name)
    text = _COMPANY_SUFFIXES.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_phone(value: str) -> str:
    """Telefone brasileiro só com DDD + número (sem DDI 55 nem zero de operadora)."""
    digits = only_digits(value)
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]
    return digits


def trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    """Mesma métrica do pg_trgm (Jaccard de trigramas), usada também fora do Postgres."""
    ta, tb = set(), set()
    for word in a.split():
        ta |= trigrams(word)
    for word in b.split():
        tb |= trigrams(word)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
