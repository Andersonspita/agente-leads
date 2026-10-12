"""Monta o conteúdo do site novo a partir dos dados do lead, do diagnóstico e do checklist da categoria.

O site sai na hora com textos-base neutros; com a IA configurada, um job reescreve os textos em
segundo plano (sem tocar no que o analista já editou). Nada é inventado: sem número de registro profissional, prêmios, anos de experiência,
preços ou depoimentos fictícios. O que depende do cliente vai para a lista "a_confirmar".
"""
import logging
from datetime import date

from apps.audits.engine import ai
from apps.audits.models import Audit, Finding
from apps.core.text import normalize
from apps.leads.models import CnpjEstablishment, Company

logger = logging.getLogger(__name__)


# Paleta, ícone e tipo schema.org por categoria (pela palavra-chave no nome da categoria).
THEMES = [
    (("odonto", "dent"), {"cor": "#0f766e", "destaque": "#f59e0b", "schema": "Dentist", "icone": "dente"}),
    (("medic", "clinica", "saude"), {"cor": "#1d4ed8", "destaque": "#10b981", "schema": "MedicalClinic", "icone": "saude"}),
    (("advoca", "advog", "jurid"), {"cor": "#1e293b", "destaque": "#b8892c", "schema": "LegalService", "icone": "balanca"}),
    (("contab", "contador"), {"cor": "#14532d", "destaque": "#0ea5e9", "schema": "AccountingService", "icone": "grafico"}),
    (("constru", "reforma", "engenh"), {"cor": "#9a3412", "destaque": "#334155", "schema": "HomeAndConstructionBusiness", "icone": "casa"}),
    (("salao", "beleza", "estet", "cabele"), {"cor": "#9d174d", "destaque": "#d4a373", "schema": "BeautySalon", "icone": "estrela"}),
    (("restaur", "comida", "lanch", "pizz"), {"cor": "#7c2d12", "destaque": "#ca8a04", "schema": "Restaurant", "icone": "prato"}),
    (("imobili", "imove", "corret"), {"cor": "#312e81", "destaque": "#0d9488", "schema": "RealEstateAgent", "icone": "casa"}),
]
DEFAULT_THEME = {"cor": "#1d4ed8", "destaque": "#f59e0b", "schema": "LocalBusiness", "icone": "estrela"}

SITE_COPY_SCHEMA = {
    "type": "object",
    "properties": {
        "titulo_seo": {"type": "string", "description": "Até 60 caracteres, com serviço e cidade"},
        "descricao_seo": {"type": "string", "description": "Entre 120 e 155 caracteres"},
        "headline": {"type": "string", "description": "Proposta de valor clara, até 70 caracteres"},
        "subheadline": {"type": "string", "description": "1 ou 2 frases"},
        "sobre": {"type": "string", "description": "2 parágrafos curtos separados por linha em branco"},
        "servicos": {"type": "array", "items": {
            "type": "object",
            "properties": {"titulo": {"type": "string"}, "descricao": {"type": "string"}},
            "required": ["titulo", "descricao"], "additionalProperties": False}},
        "diferenciais": {"type": "array", "items": {
            "type": "object",
            "properties": {"titulo": {"type": "string"}, "descricao": {"type": "string"}},
            "required": ["titulo", "descricao"], "additionalProperties": False}},
        "faq": {"type": "array", "items": {
            "type": "object",
            "properties": {"pergunta": {"type": "string"}, "resposta": {"type": "string"}},
            "required": ["pergunta", "resposta"], "additionalProperties": False}},
    },
    "required": ["titulo_seo", "descricao_seo", "headline", "subheadline", "sobre", "servicos", "diferenciais", "faq"],
    "additionalProperties": False,
}

COPY_PROMPT = """Você é redator sênior de sites para pequenas empresas brasileiras.
Escreva os textos do site novo de "{empresa}", {categoria} em {cidade}.

Regras obrigatórias:
- Português do Brasil, tom profissional, acolhedor e direto; frases curtas.
- NÃO invente fatos: nada de anos de experiência, número de clientes, prêmios, registros profissionais
  (CRO, OAB, CRM, CRC, CRECI), preços, promoções, convênios ou nomes de profissionais.
- Fale de serviços típicos da categoria de forma genérica e verdadeira para qualquer empresa do ramo.
- Cite a cidade ({cidade}) no título SEO, na headline ou na subheadline.
- Respeite as regras de publicidade do conselho profissional da categoria (ex.: sem promessa de resultado,
  sem linguagem de captação agressiva para advocacia e saúde).
- 6 serviços, 4 diferenciais e 5 perguntas frequentes.

Problemas do site atual que o site novo precisa resolver (use como guia para os diferenciais e textos):
{problemas}

Itens obrigatórios da categoria:
{checklist}
"""


def theme_for(company: Company) -> dict:
    name = normalize(company.category.nome if company.category else "")
    for keys, theme in THEMES:
        if any(k in name for k in keys):
            return dict(theme)
    return dict(DEFAULT_THEME)


def is_mobile(phone: str) -> bool:
    return len(phone or "") == 11 and phone[2] == "9"


def default_copy(company: Company, cidade: str, categoria: str) -> dict:
    """Textos-base sem IA: neutros e verdadeiros para qualquer empresa do ramo."""
    servico = categoria.lower() if categoria else "atendimento"
    return {
        "titulo_seo": f"{company.nome} | {categoria or 'Atendimento'} em {cidade}"[:70],
        "descricao_seo": (f"{company.nome}: {servico} em {cidade}. Atendimento próximo de você, "
                          f"com agendamento fácil pelo WhatsApp. Veja serviços, localização e horários.")[:160],
        "headline": f"{categoria or 'Atendimento de qualidade'} em {cidade}",
        "subheadline": f"A {company.nome} atende você com cuidado e clareza. Fale conosco e tire suas dúvidas.",
        "sobre": (f"A {company.nome} atende clientes em {cidade} com foco em atenção, clareza e respeito ao seu tempo."
                  "\n\nNosso compromisso é explicar cada etapa do atendimento e facilitar o contato, "
                  "pelo telefone, pelo WhatsApp ou pessoalmente."),
        "servicos": [{"titulo": f"Serviço {i}", "descricao": "Descreva aqui um serviço oferecido."} for i in range(1, 7)],
        "diferenciais": [
            {"titulo": "Atendimento próximo", "descricao": "Explicações claras e atenção a cada cliente."},
            {"titulo": "Contato fácil", "descricao": "Fale pelo WhatsApp, telefone ou formulário."},
            {"titulo": "Localização acessível", "descricao": f"Fácil de chegar em {cidade}, com rota pelo mapa."},
            {"titulo": "Transparência", "descricao": "Informações claras antes de qualquer decisão."},
        ],
        "faq": [
            {"pergunta": "Como faço para agendar?", "resposta": "Chame no WhatsApp ou ligue: respondemos no horário de atendimento."},
            {"pergunta": "Onde vocês ficam?", "resposta": f"Estamos em {cidade}. Veja o endereço completo e a rota na seção de contato."},
            {"pergunta": "Qual o horário de atendimento?", "resposta": "Confira o horário atualizado na seção de contato."},
            {"pergunta": "Posso tirar dúvidas antes?", "resposta": "Sim. Mande sua dúvida pelo formulário ou WhatsApp."},
            {"pergunta": "Como meus dados são tratados?", "resposta": "Usamos seus dados só para responder ao contato. Veja a política de privacidade."},
        ],
    }


def _validate_copy(data: dict) -> dict:
    for key in ("servicos", "diferenciais", "faq"):
        if not isinstance(data.get(key), list) or not data[key]:
            raise ValueError(f"lista '{key}' vazia")
    for key in ("titulo_seo", "headline", "sobre"):
        if not str(data.get(key) or "").strip():
            raise ValueError(f"campo '{key}' vazio")
    return data


NO_AI_NOTE = "Textos dos serviços (gerados sem IA, revise todos)"


def _facts(company: Company, audit: Audit | None) -> dict:
    checklist = list(company.category.checklist.values_list("item", flat=True)) if company.category else []
    problemas = []
    if audit:
        problemas = list(audit.findings.filter(status_revisao=Finding.Review.CONFIRMED)
                         .values_list("titulo", flat=True)[:15])
    return {
        "cidade": company.municipality.nome if company.municipality_id else "",
        "uf": company.municipality.uf if company.municipality_id else "",
        "categoria": company.category.nome if company.category else "",
        "checklist": checklist,
        "problemas": problemas,
    }


def ai_copy(company: Company, audit: Audit | None) -> tuple[dict, str]:
    """Textos do site escritos pela IA (roda em job; pode demorar). Devolve (textos, modelo)."""
    f = _facts(company, audit)
    prompt = COPY_PROMPT.format(
        empresa=company.nome, categoria=f["categoria"] or "negócio local", cidade=f["cidade"] or "sua cidade",
        problemas="\n".join(f"- {p}" for p in f["problemas"]) or "- (sem diagnóstico: empresa sem site)",
        checklist="\n".join(f"- {c}" for c in f["checklist"]) or "- (nenhum)",
    )
    return ai.complete_json(prompt, SITE_COPY_SCHEMA, _validate_copy)


def merge_ai_copy(content: dict, company: Company, copy: dict) -> dict:
    """Aplica os textos da IA só nos campos que o analista ainda não editou (iguais aos textos-base)."""
    f = _facts(company, None)
    base = default_copy(company, f["cidade"], f["categoria"])
    merged = dict(content)
    for key in SITE_COPY_SCHEMA["required"]:
        if merged.get(key) == base.get(key):
            merged[key] = copy[key]
    merged["a_confirmar"] = [i for i in merged.get("a_confirmar", []) if i != NO_AI_NOTE]
    return merged


def build_content(company: Company, audit: Audit | None) -> dict:
    """Conteúdo completo com os textos-base (instantâneo); a IA reescreve os textos depois, em job."""
    f = _facts(company, audit)
    cidade, uf, categoria, checklist, problemas = f["cidade"], f["uf"], f["categoria"], f["checklist"], f["problemas"]
    est = CnpjEstablishment.objects.filter(cnpj=company.cnpj).first() if company.cnpj else None
    theme = theme_for(company)
    copy = default_copy(company, cidade, categoria)

    whatsapp = company.whatsapp or (company.telefone if is_mobile(company.telefone) else "")
    a_confirmar = ["Horário de atendimento", "Fotos reais do espaço e da equipe (as imagens atuais são ilustrações)"]
    if not company.whatsapp:
        a_confirmar.append("Número de WhatsApp" + (" (usamos o celular cadastrado)" if whatsapp else ""))
    if not company.redes_sociais:
        a_confirmar.append("Links do Instagram/Facebook")
    if any("agend" in c.lower() for c in checklist):
        a_confirmar.append("Link de agendamento online (hoje o agendamento é pelo WhatsApp)")
    a_confirmar.append(NO_AI_NOTE)
    a_confirmar.append("Registro profissional do responsável técnico, se exigido pelo conselho da categoria")

    content = {
        "empresa": company.nome,
        "categoria": categoria,
        "cidade": cidade,
        "uf": uf,
        "telefone": company.telefone,
        "whatsapp": whatsapp,
        "email": "",
        "endereco": company.endereco,
        "bairro": company.bairro,
        "cep": est.cep if est else "",
        "cnpj": company.cnpj,
        "horario": "Segunda a sexta, das 8h às 18h",
        "instagram": (company.redes_sociais or {}).get("instagram", ""),
        "facebook": (company.redes_sociais or {}).get("facebook", ""),
        "link_agendamento": "",
        "agendamento": any("agend" in c.lower() for c in checklist),
        "nota_google": float(company.nota_google) if company.nota_google else None,
        "n_avaliacoes": company.n_avaliacoes,
        "cor": theme["cor"],
        "cor_destaque": theme["destaque"],
        "schema_tipo": theme["schema"],
        "icone": theme["icone"],
        "ano": date.today().year,
        **{k: copy[k] for k in SITE_COPY_SCHEMA["required"]},
        "problemas_resolvidos": problemas,
        "a_confirmar": a_confirmar,
    }
    return content
