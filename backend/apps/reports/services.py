"""Montagem do relatório do cliente, comparativo e briefing do site novo."""
import base64
import hashlib
import logging
import mimetypes

from django.conf import settings
from django.db.models import OuterRef, Subquery
from django.template.loader import render_to_string
from django.utils import timezone

from apps.audits.engine.scoring import score_band
from apps.audits.models import Artifact, Audit, Finding
from apps.catalog.models import Dimension, Severity
from apps.core.models import BrandSettings
from apps.leads.models import Website

logger = logging.getLogger(__name__)

TOP_N = 5
REFERENCE_SCORE = 85  # padrão de referência: meta do site entregue (PRD 1.2)
SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
RISK_DIMENSIONS = {Dimension.SECURITY, Dimension.COMPLIANCE}
GAINS = {
    Dimension.PERFORMANCE: "Menos desistências e melhor posição no Google",
    Dimension.MOBILE: "Experiência agradável para quem chega pelo celular",
    Dimension.SEO: "Mais gente encontrando a empresa no Google",
    Dimension.ACCESSIBILITY: "Site utilizável por todos, dentro da lei",
    Dimension.SECURITY: "Confiança do visitante e proteção da marca",
    Dimension.CONTENT: "Mais credibilidade na primeira visita",
    Dimension.CONVERSION: "Mais pedidos de orçamento e agendamentos",
    Dimension.COMPLIANCE: "Tranquilidade jurídica com a LGPD",
}


def confirmed_findings(audit: Audit, order: list[int] | None = None) -> list[Finding]:
    findings = list(audit.findings.filter(status_revisao=Finding.Review.CONFIRMED))
    if order:
        position = {fid: i for i, fid in enumerate(order)}
        return sorted(findings, key=lambda f: (position.get(f.pk, 999), SEVERITY_ORDER.get(f.severidade, 9)))
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severidade, 9), f.origem != "regra", f.pk))


def latest_audits_for(category_id, municipality_id, exclude_website_id=None):
    latest = Audit.objects.filter(website=OuterRef("pk"), status=Audit.Status.DONE).order_by("-concluido_em")
    sites = (
        Website.objects.filter(company__category_id=category_id, company__municipality_id=municipality_id)
        .exclude(pk=exclude_website_id)
        .annotate(audit_id=Subquery(latest.values("pk")[:1]))
        .filter(audit_id__isnull=False)
    )
    return Audit.objects.filter(pk__in=[s.audit_id for s in sites]).select_related("website__company")


def competitors(audit: Audit, chosen_ids: list[int] | None = None, limit: int = 5) -> list[dict]:
    """Concorrentes da mesma categoria e cidade com auditoria concluída (RF10)."""
    company = audit.website.company
    audits = latest_audits_for(company.category_id, company.municipality_id, audit.website_id)
    if chosen_ids:
        audits = audits.filter(website__company_id__in=chosen_ids)
    audits = sorted(audits, key=lambda a: -(a.nota_geral or 0))[:limit]
    return [
        {"company_id": a.website.company_id, "nome": a.website.company.nome, "nota": a.nota_geral,
         "dominio": a.website.dominio, "audit_id": a.pk, **score_band(a.nota_geral)}
        for a in audits
    ]


def comparison(audit: Audit, chosen_ids=None, show_names=True) -> dict:
    comps = competitors(audit, chosen_ids)
    company = audit.website.company
    rows = [{"nome": company.nome, "nota": audit.nota_geral, "destaque": True, **score_band(audit.nota_geral)}]
    for i, c in enumerate(comps, start=1):
        rows.append({**c, "nome": c["nome"] if show_names else f"Concorrente {i}", "destaque": False})
    rows.sort(key=lambda r: -(r["nota"] or 0))
    scored = [r["nota"] for r in rows if r["nota"] is not None]
    city_all = latest_audits_for(company.category_id, company.municipality_id)
    city_scores = [a.nota_geral for a in city_all if a.nota_geral is not None]
    return {
        "linhas": rows,
        "posicao": next((i + 1 for i, r in enumerate(rows) if r["destaque"]), None),
        "total": len(rows),
        "media_local": round(sum(city_scores) / len(city_scores)) if city_scores else None,
        "referencia": REFERENCE_SCORE,
        "maior_nota": max(scored) if scored else None,
    }


def artifact_map(audit: Audit, inline: bool = False) -> dict:
    out = {}
    for art in audit.artifacts.exclude(tipo=Artifact.Kind.LIGHTHOUSE_JSON):
        if inline:
            try:
                with art.arquivo.open("rb") as fh:
                    data = base64.b64encode(fh.read()).decode()
                mime = mimetypes.guess_type(art.arquivo.name)[0] or "image/png"
                url = f"data:{mime};base64,{data}"
            except (OSError, ValueError):
                continue
        else:
            url = art.arquivo.url
        out[art.tipo] = {"url": url, "largura": art.meta.get("largura"), "altura": art.meta.get("altura")}
    return out


def default_summary(audit: Audit, findings: list[Finding]) -> str:
    company = audit.website.company
    band = score_band(audit.nota_geral)["rotulo"].lower()
    top = [f.titulo.rstrip(".") for f in findings[:2]]
    parts = [f"O site da {company.nome} tirou {audit.nota_geral}/100 na nossa avaliação ({band})."]
    if top:
        parts.append("Os pontos que mais custam clientes hoje: " + "; ".join(t[0].lower() + t[1:] for t in top) + ".")
    parts.append("Um site novo resolve esses problemas e transforma mais visitas em contatos.")
    return " ".join(parts)


def build_report_context(report, inline_images: bool = False) -> dict:
    audit = report.audit
    company = audit.website.company
    findings = confirmed_findings(audit, report.achados_ids)
    artifacts = artifact_map(audit, inline=inline_images)
    for f in findings:
        kind = f.evidencia.get("artefato") if isinstance(f.evidencia, dict) else None
        f.captura = artifacts.get(kind) if kind else None
        f.gain = GAINS.get(f.dimensao, "")
    dims = [
        {"chave": d.value, "nome": d.label, "nota": audit.notas_dimensao.get(d.value),
         **score_band(audit.notas_dimensao.get(d.value))}
        for d in Dimension
    ]
    brand = BrandSettings.get()
    return {
        "report": report,
        "audit": audit,
        "company": company,
        "website": audit.website,
        "brand": brand,
        "band": score_band(audit.nota_geral),
        "resumo": report.resumo or default_summary(audit, findings),
        "top": findings[:TOP_N],
        "outros": findings[TOP_N:],
        "riscos": [f for f in findings if f.dimensao in RISK_DIMENSIONS],
        "solucoes": findings[:10],
        "dimensoes": dims,
        "nao_medidas": [s for s in audit.steps.all() if s.status in ("nao_medido", "falhou")],
        "comparativo": comparison(audit, report.concorrentes_ids, report.exibir_nomes_concorrentes),
        "capturas": artifacts,
        "metricas": audit.metricas,
        "hoje": timezone.localdate(),
        "whatsapp_link": f"https://wa.me/{brand.whatsapp}?text="
                         f"Olá! Vi o diagnóstico do site da {company.nome} e quero conversar." if brand.whatsapp else "",
        "pdf_mode": inline_images,
    }


def hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()


def render_pdf(report) -> bytes:
    html = render_to_string("reports/public.html", build_report_context(report, inline_images=True))
    try:
        from weasyprint import HTML

        return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    except (ImportError, OSError):
        logger.info("WeasyPrint indisponível; gerando PDF com Chromium")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        pdf = page.pdf(format="A4", print_background=True,
                       margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        browser.close()
    return pdf


# ---------------------------------------------------------------- Briefing do site novo

BASE_PAGES = ["Início", "Sobre / Quem somos", "Serviços", "Contato", "Política de privacidade"]
BASE_INTEGRATIONS = [
    "Botão de WhatsApp com mensagem pré-preenchida",
    "Google Maps (mapa + “Como chegar”)",
    "Google Analytics 4 com aviso de cookies (consentimento)",
    "Google Business Profile e Search Console",
]
BASE_GOALS = [
    {"meta": "Nota do Auditor", "alvo": f"≥ {REFERENCE_SCORE}/100 e +30 pontos sobre o site atual"},
    {"meta": "Conteúdo principal no celular (LCP)", "alvo": "≤ 2,5 s em 4G"},
    {"meta": "Estabilidade visual (CLS)", "alvo": "≤ 0,1"},
    {"meta": "Peso da página inicial", "alvo": "≤ 1,5 MB"},
    {"meta": "Lighthouse (todas as categorias)", "alvo": "≥ 90"},
    {"meta": "Acessibilidade", "alvo": "WCAG 2.1 AA, sem violações críticas"},
    {"meta": "Segurança", "alvo": "HTTPS com HSTS e cabeçalhos de segurança"},
    {"meta": "LGPD", "alvo": "Política de privacidade, aviso de cookies e consentimento nos formulários"},
]


def build_briefing(company, audit: Audit | None) -> dict:
    """Briefing técnico do site novo: cada falha apontada vira um requisito (RF09)."""
    category = company.category
    checklist = list(category.checklist.all()) if category else []
    pages = list(BASE_PAGES)
    sections = ["Primeira tela com proposta de valor clara, cidade e botão de contato",
                "Depoimentos / avaliações do Google", "Rodapé com endereço, telefone, horário e redes sociais"]
    integrations = list(BASE_INTEGRATIONS)
    for item in checklist:
        target = {"pagina": pages, "secao": sections, "integracao": integrations}.get(item.tipo)
        if target is not None and item.item not in target:
            target.append(item.item + ("" if item.obrigatorio else " (opcional)"))

    requirements = []
    if audit:
        for f in confirmed_findings(audit):
            requirements.append({
                "achado_id": f.pk, "dimensao": Dimension(f.dimensao).label, "severidade": f.severidade,
                "problema": f.titulo, "requisito": f.melhoria_proposta,
            })
    goals = list(BASE_GOALS)
    for item in checklist:
        if item.tipo == "meta":
            goals.append({"meta": item.item, "alvo": "Obrigatório" if item.obrigatorio else "Desejável"})
    return {
        "empresa": {"nome": company.nome, "cidade": str(company.municipality or ""),
                    "categoria": category.nome if category else "", "site_atual": getattr(
                        company.main_website, "url", "")},
        "nota_atual": audit.nota_geral if audit else None,
        "paginas": pages,
        "secoes": sections,
        "integracoes": integrations,
        "requisitos": requirements,
        "metas": goals,
        "conteudo_necessario": [
            "Logo em alta resolução e cores da marca",
            "Fotos reais do espaço, equipe e serviços",
            "Lista de serviços com descrição curta",
            "Depoimentos autorizados de clientes",
            "Dados de contato, horário e endereço oficiais",
        ],
    }


def briefing_markdown(briefing) -> str:
    c = briefing.conteudo
    emp = c["empresa"]
    lines = [f"# Briefing do site novo — {emp['nome']}", "",
             f"- **Categoria:** {emp['categoria'] or '—'}", f"- **Cidade:** {emp['cidade'] or '—'}",
             f"- **Site atual:** {emp['site_atual'] or 'sem site'}",
             f"- **Nota atual:** {c['nota_atual'] if c['nota_atual'] is not None else 'não auditado'}",
             f"- **Versão:** {briefing.versao} ({briefing.criado_em:%d/%m/%Y})", ""]
    for title, key in (("Páginas", "paginas"), ("Seções obrigatórias", "secoes"), ("Integrações", "integracoes"),
                       ("Conteúdo a solicitar ao cliente", "conteudo_necessario")):
        lines += [f"## {title}", "", *[f"- [ ] {item}" for item in c[key]], ""]
    if c["requisitos"]:
        lines += ["## Requisitos a partir do diagnóstico", "", "| Severidade | Problema no site atual | Requisito no site novo |",
                  "|---|---|---|"]
        for r in c["requisitos"]:
            lines.append(f"| {r['severidade']} | {r['problema']} | {r['requisito']} |")
        lines.append("")
    lines += ["## Metas de qualidade", "", "| Meta | Alvo |", "|---|---|",
              *[f"| {g['meta']} | {g['alvo']} |" for g in c["metas"]], ""]
    return "\n".join(lines)
