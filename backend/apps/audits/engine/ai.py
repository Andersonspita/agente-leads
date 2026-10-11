"""Etapa 8 — análise qualitativa assistida por IA (TRD 2.5).

- Entrada: capturas desktop/mobile + texto das páginas + achados das regras.
- Saída: JSON validado por schema (structured outputs); se vier inválido, tenta
  mais uma vez e depois marca a etapa como falha.
- A IA nunca fornece números: métricas vêm só das etapas 3–7.
- Todo achado da IA nasce "pendente de revisão".
"""
import base64
import json
import logging
import time
from decimal import Decimal

from django.conf import settings

from apps.catalog.models import Dimension, Severity
from apps.core import costs
from apps.core.models import PromptVersion

logger = logging.getLogger(__name__)

PROMPT_NAME = "analise_qualitativa"
AI_DIMENSIONS = [Dimension.CONTENT, Dimension.CONVERSION, Dimension.MOBILE, Dimension.SEO, Dimension.ACCESSIBILITY]

DEFAULT_PROMPT = """Você é um consultor sênior de UX e marketing digital para pequenas empresas brasileiras.
Avalie o site institucional de "{empresa}" ({categoria}, {cidade}) a partir das capturas de tela
(desktop 1440 px e celular 390 px) e do texto extraído das páginas.

Foque no que as regras automáticas não medem:
- design datado ou amador, hierarquia visual confusa, excesso de elementos;
- clareza da proposta de valor na primeira tela (o visitante entende em 5 segundos o que a empresa faz e onde?);
- confiança e credibilidade transmitidas (fotos genéricas de banco de imagens, textos vagos, erros de ortografia);
- caminho até o contato no celular.

Regras obrigatórias:
- NÃO cite números, tempos, notas ou percentuais: métricas são medidas por outras ferramentas.
- Não repita problemas já listados nos achados automáticos abaixo.
- Cada achado deve apontar onde aparece na captura (ex.: "faixa superior da captura mobile").
- Escreva em português do Brasil, tom construtivo e respeitoso — o dono da empresa vai ler.
- "impacto_negocio" em linguagem de negócio (clientes, confiança, contatos), sem jargão técnico.
- "melhoria_proposta" descreve como o site novo resolve o problema.
- Entre 3 e 7 achados, apenas os relevantes. Liste também até 3 pontos fortes reais do site atual.

Achados automáticos já registrados:
{achados_regras}

Texto das páginas (resumido):
{texto}
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string", "description": "Avaliação geral em até 3 frases"},
        "pontos_fortes": {"type": "array", "items": {"type": "string"}},
        "achados": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimensao": {"type": "string", "enum": [d.value for d in AI_DIMENSIONS]},
                    "severidade": {"type": "string", "enum": [s.value for s in Severity]},
                    "titulo": {"type": "string"},
                    "descricao": {"type": "string"},
                    "impacto_negocio": {"type": "string"},
                    "melhoria_proposta": {"type": "string"},
                    "captura": {"type": "string", "enum": ["desktop", "mobile"]},
                    "local_na_captura": {"type": "string"},
                },
                "required": ["dimensao", "severidade", "titulo", "descricao", "impacto_negocio",
                             "melhoria_proposta", "captura", "local_na_captura"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["resumo", "pontos_fortes", "achados"],
    "additionalProperties": False,
}


class AIUnavailable(Exception):
    pass


class AIInvalidOutput(Exception):
    pass


class AIRefused(AIInvalidOutput):
    """Recusa por política: não adianta tentar de novo."""


def active_prompt() -> tuple[str, str]:
    """(texto do prompt, identificador da versão)."""
    pv = PromptVersion.active(PROMPT_NAME)
    if pv:
        return pv.texto, f"{PROMPT_NAME}#{pv.pk}"
    return DEFAULT_PROMPT, f"{PROMPT_NAME}#padrao"


def _image_block(png: bytes) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(png).decode()},
    }


def validate(data) -> dict:
    """Validação defensiva além do schema (o job só grava o que passa aqui)."""
    if not isinstance(data, dict) or not isinstance(data.get("achados"), list):
        raise AIInvalidOutput("JSON sem a lista 'achados'")
    valid_dims = {d.value for d in AI_DIMENSIONS}
    valid_sev = {s.value for s in Severity}
    for item in data["achados"]:
        if item.get("dimensao") not in valid_dims or item.get("severidade") not in valid_sev:
            raise AIInvalidOutput(f"achado inválido: {item.get('titulo')!r}")
        if not item.get("titulo"):
            raise AIInvalidOutput("achado sem título")
    return data


def provider() -> str:
    """Provedor de IA ativo: AI_PROVIDER explícito ou o primeiro com chave configurada."""
    if settings.AI_PROVIDER:
        return settings.AI_PROVIDER
    if settings.GEMINI_API_KEY:
        return "gemini"
    if settings.ANTHROPIC_API_KEY:
        return "anthropic"
    if settings.AI_BASE_URL:
        return "openai_compat"
    return ""


def is_configured() -> bool:
    name = provider()
    if name == "gemini":
        return bool(settings.GEMINI_API_KEY)
    if name == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    if name == "openai_compat":
        return bool(settings.AI_BASE_URL)
    return False


def model_name() -> str:
    name = provider()
    if name == "anthropic":
        return settings.ANTHROPIC_MODEL
    if name == "gemini":
        return settings.AI_MODEL or "gemini-flash-latest"
    return settings.AI_MODEL


def analyze(*, empresa, categoria, cidade, desktop_png, mobile_png, texto, achados_regras) -> dict:
    if not is_configured():
        raise AIUnavailable("IA não configurada (defina GEMINI_API_KEY, ANTHROPIC_API_KEY ou AI_BASE_URL)")
    costs.check_budget()

    template, version = active_prompt()
    prompt = template.format(
        empresa=empresa, categoria=categoria or "negócio local", cidade=cidade or "cidade não informada",
        achados_regras="\n".join(f"- {t}" for t in achados_regras) or "- (nenhum)",
        texto=texto[:12000],
    )
    images = [(label, png) for label, png in (
        ("Captura desktop (1440 px, primeira tela):", desktop_png),
        ("Captura celular (390 px, primeira tela):", mobile_png),
    ) if png]

    call = _call_anthropic if provider() == "anthropic" else _call_openai_compat
    last_error = None
    for attempt in range(2):  # 1 tentativa + 1 nova tentativa se o JSON vier inválido
        try:
            text, used_model = call(prompt, images, attempt)
            data = validate(json.loads(_strip_fences(text)))
        except AIRefused:
            raise
        except (json.JSONDecodeError, AIInvalidOutput) as exc:
            last_error = exc
            logger.warning("JSON inválido da IA (tentativa %s): %s", attempt + 1, exc)
            continue
        data["_versao_prompt"] = version
        data["_modelo"] = used_model
        return data
    raise AIInvalidOutput(str(last_error))


def complete_json(prompt: str, schema: dict, validator=None) -> tuple[dict, str]:
    """Pede à IA configurada um JSON no `schema` dado (sem imagens). Devolve (dados, modelo usado)."""
    if not is_configured():
        raise AIUnavailable("IA não configurada")
    costs.check_budget()
    call = _call_anthropic if provider() == "anthropic" else _call_openai_compat
    last_error = None
    for attempt in range(2):
        try:
            text, used_model = call(prompt, [], attempt, schema)
            data = json.loads(_strip_fences(text))
            if validator:
                data = validator(data)
            return data, used_model
        except AIRefused:
            raise
        except (json.JSONDecodeError, AIInvalidOutput, ValueError) as exc:
            last_error = exc
            logger.warning("JSON inválido da IA (tentativa %s): %s", attempt + 1, exc)
    raise AIInvalidOutput(str(last_error))


def _strip_fences(text: str) -> str:
    """Alguns modelos devolvem o JSON dentro de ```json ... ```."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _call_anthropic(prompt, images, attempt, schema=OUTPUT_SCHEMA) -> tuple[str, str]:
    import anthropic

    content = []
    for label, png in images:
        content += [{"type": "text", "text": label}, _image_block(png)]
    content.append({"type": "text", "text": prompt})
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    model = settings.ANTHROPIC_MODEL
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
        # Em caso de recusa por política, a API reexecuta num modelo alternativo.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    costs.record(
        "anthropic", "messages",
        costs.anthropic_cost(model, response.usage.input_tokens, response.usage.output_tokens),
        modelo=response.model, tentativa=attempt + 1,
    )
    if response.stop_reason == "refusal":
        raise AIRefused("A IA recusou a análise deste site")
    if response.stop_reason == "max_tokens":
        raise AIInvalidOutput("resposta truncada")
    return next((b.text for b in response.content if b.type == "text"), ""), response.model


GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def _call_openai_compat(prompt, images, attempt, schema=OUTPUT_SCHEMA) -> tuple[str, str]:
    """Gemini, Ollama, OpenRouter, Groq etc. pelo formato de chat compatível com a API da OpenAI."""
    import requests

    if provider() == "gemini":
        base_url, api_key, provedor = GEMINI_OPENAI_URL, settings.GEMINI_API_KEY, "gemini"
    else:
        base_url, api_key, provedor = settings.AI_BASE_URL.rstrip("/"), settings.AI_API_KEY, "openai_compat"
    model = model_name()
    if not model:
        raise AIUnavailable("Defina AI_MODEL com o nome do modelo")

    content = []
    for label, png in images:
        content += [
            {"type": "text", "text": label},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + base64.standard_b64encode(png).decode()}},
        ]
    content.append({"type": "text", "text": prompt + "\n\nResponda somente com um objeto JSON neste schema:\n"
                    + json.dumps(schema, ensure_ascii=False)})
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # Servidores gratuitos às vezes respondem 500/502/503 por excesso de demanda: espera e tenta de novo.
    for wait in (0, 5, 15, 30):
        if wait:
            logger.info("IA ocupada (HTTP %s); nova tentativa em %s s", resp.status_code, wait)
            time.sleep(wait)
        resp = requests.post(f"{base_url}/chat/completions", json=body, headers=headers,
                             timeout=settings.AI_TIMEOUT)
        if resp.status_code not in (500, 502, 503):
            break
    if resp.status_code == 429:
        raise AIUnavailable("Limite gratuito da IA atingido no momento; tente de novo mais tarde (Rodar IA)")
    if resp.status_code >= 400:
        raise AIUnavailable(f"IA respondeu {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    usage = data.get("usage") or {}
    costs.record(provedor, "chat.completions", Decimal("0"),
                 modelo=model, tentativa=attempt + 1, tokens_entrada=usage.get("prompt_tokens"),
                 tokens_saida=usage.get("completion_tokens"))
    choice = (data.get("choices") or [{}])[0]
    if choice.get("finish_reason") == "length":
        raise AIInvalidOutput("resposta truncada")
    return (choice.get("message") or {}).get("content") or "", data.get("model") or model
