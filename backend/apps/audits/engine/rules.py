"""Regras automáticas de auditoria.

Cada regra lê só o que as etapas 1–7 mediram (AuditContext) e devolve:
- None: não foi possível medir (a regra não conta na nota);
- Outcome(passed=True): aprovada;
- Outcome(passed=False, ...): gera um achado com evidência, impacto em linguagem
  de negócio e a melhoria correspondente para o site novo.

Os textos usam {variáveis} preenchidas com os valores medidos.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from apps.catalog.models import Dimension, Severity

from .context import AuditContext

RULES_VERSION = "2026.09-1"

PHONE_RE = re.compile(r"(?:\+?55\s?)?\(?\b[1-9]{2}\)?\s?(?:9\s?)?\d{4}[-.\s]?\d{4}\b")
CEP_RE = re.compile(r"\b\d{5}-?\d{3}\b")
ADDRESS_RE = re.compile(
    r"\b(rua|r\.|av\.|avenida|travessa|tv\.|pra[çc]a|rodovia|alameda|estrada|largo)\s+[^\n,]{2,60},?\s*(n[º°o.]?\s*)?\d+",
    re.I,
)
HOURS_RE = re.compile(
    r"(hor[áa]rio|atendimento|funcionamento).{0,40}(\d{1,2}\s?(h|:\d{2}))|seg(unda)?\.?\s*(a|à|-)\s*sex",
    re.I,
)
TESTIMONIAL_RE = re.compile(r"depoimento|o que (nossos )?(clientes|pacientes) dizem|avalia[çc][õo]es|testemunho", re.I)
ABOUT_RE = re.compile(r"sobre|quem somos|a empresa|nossa hist[óo]ria|institucional|conhe[çc]a", re.I)
PRIVACY_RE = re.compile(r"privacidade|privacy|prote[çc][ãa]o de dados", re.I)
CONSENT_RE = re.compile(r"privacidade|consent|lgpd|concordo|autorizo|termos", re.I)
SCHEDULING_RE = re.compile(
    r"agend|marque (sua|uma)|doctoralia|calendly|simplesagenda|agendor|feegow|iclinic|booking|reserv", re.I
)
GENERIC_TITLES = {"home", "inicio", "início", "pagina inicial", "página inicial", "index", "site", "untitled",
                  "novo site", "meu site", "wordpress"}
LOCAL_BUSINESS_TYPES = re.compile(
    r"LocalBusiness|Organization|Dentist|MedicalClinic|Physician|LegalService|Attorney|AccountingService|"
    r"ProfessionalService|Store|Restaurant|HealthAndBeautyBusiness|HomeAndConstructionBusiness|MedicalBusiness|"
    r"AutomotiveBusiness|FinancialService|RealEstateAgent|EducationalOrganization|School",
)


@dataclass
class Outcome:
    passed: bool
    evidence: dict = field(default_factory=dict)
    vars: dict = field(default_factory=dict)
    severity: str | None = None


@dataclass
class Rule:
    code: str
    dimension: str
    severity: str
    title: str
    impact: str
    improvement: str
    check: Callable[[AuditContext], Outcome | None]
    description: str = ""

    def render(self, template: str, outcome: Outcome) -> str:
        values = defaultdict(lambda: "?", outcome.vars)
        return template.format_map(values)


RULES: list[Rule] = []


def rule(code, dimension, severity, title, impact, improvement, description=""):
    def register(fn):
        RULES.append(Rule(code, dimension, severity, title, impact, improvement, fn, description or title))
        return fn

    return register


def ok():
    return Outcome(True)


def fail(evidence=None, severity=None, **vars):
    return Outcome(False, evidence or {}, vars, severity)


def _metric(value, reference=None, unit=""):
    return {"tipo": "metrica", "valor": value, "referencia": reference, "unidade": unit}


def _screenshot(kind, boxes=None, label=None):
    return {"tipo": "captura", "artefato": kind, "caixas": boxes or [], "legenda": label}


def _html(snippet):
    return {"tipo": "html", "trecho": (snippet or "")[:400]}


# ---------------------------------------------------------------- Desempenho

@rule("PERF-001", Dimension.PERFORMANCE, Severity.HIGH,
      "O site leva {lcp_s} s para mostrar o conteúdo principal no celular",
      "53% dos visitantes no celular desistem de um site que demora mais de 3 s para carregar. "
      "Cada segundo a mais é cliente indo para o concorrente.",
      "Site novo com imagens otimizadas (WebP/AVIF), carregamento sob demanda e hospedagem com CDN, "
      "com meta de exibir o conteúdo principal em até 2,5 s no 4G.")
def perf_lcp(ctx):
    lcp = ctx.lh("mobile").get("metricas", {}).get("lcp_ms")
    source = "Lighthouse (mobile, 4G simulado)"
    if lcp is None and ctx.mobile:
        lcp = ctx.mobile.metrics.get("lcp_ms")
        source = "Navegador real (390 px)"
    if lcp is None:
        return None
    if lcp <= 4000:
        return ok()
    return fail(_metric(round(lcp), 2500, "ms") | {"fonte": source},
                Severity.CRITICAL if lcp > 8000 else None, lcp_s=f"{lcp / 1000:.1f}".replace(".", ","))


@rule("PERF-002", Dimension.PERFORMANCE, Severity.MEDIUM,
      "A página inicial pesa {mb} MB",
      "Páginas pesadas consomem o plano de dados do cliente e carregam devagar em redes móveis.",
      "Orçamento de peso de até 1,5 MB na home, com imagens redimensionadas e scripts enxutos.")
def perf_weight(ctx):
    size = ctx.lh("mobile").get("metricas", {}).get("peso_bytes")
    if size is None and ctx.mobile:
        size = ctx.mobile.bytes_total or None
    if not size:
        return None
    if size <= 3_000_000:
        return ok()
    return fail(_metric(size, 1_500_000, "bytes"), Severity.HIGH if size > 6_000_000 else None,
                mb=f"{size / 1_000_000:.1f}".replace(".", ","))


@rule("PERF-003", Dimension.PERFORMANCE, Severity.LOW,
      "A página faz {n} requisições para carregar",
      "Muitos arquivos separados deixam o carregamento lento, principalmente no celular.",
      "Agrupar e reduzir scripts de terceiros; carregar só o necessário em cada página.")
def perf_requests(ctx):
    if not ctx.mobile or not ctx.mobile.requests:
        return None
    n = ctx.mobile.requests
    return ok() if n <= 120 else fail(_metric(n, 80), n=n)


@rule("PERF-004", Dimension.PERFORMANCE, Severity.MEDIUM,
      "{n} imagens são muito maiores do que o espaço onde aparecem",
      "Imagens superdimensionadas são a causa mais comum de lentidão em sites institucionais.",
      "Imagens responsivas (srcset) em formatos modernos, geradas no tamanho de exibição.")
def perf_images(ctx):
    if not ctx.desktop:
        return None
    n = ctx.desktop.layout.get("images_oversized", 0)
    return ok() if n < 3 else fail(_metric(n, 0), n=n)


@rule("PERF-005", Dimension.PERFORMANCE, Severity.MEDIUM,
      "O servidor demora {s} s para começar a responder",
      "Um servidor lento atrasa tudo o que vem depois, em todas as páginas.",
      "Hospedagem de qualidade com cache de página e servidor no Brasil.")
def perf_ttfb(ctx):
    ttfb = ctx.desktop.metrics.get("ttfb_ms") if ctx.desktop else None
    if ttfb is None:
        return None
    return ok() if ttfb <= 1800 else fail(_metric(ttfb, 800, "ms"), s=f"{ttfb / 1000:.1f}".replace(".", ","))


# ---------------------------------------------------------------- Mobile

@rule("MOB-001", Dimension.MOBILE, Severity.CRITICAL,
      "O site não foi feito para celular (sem ajuste de tela)",
      "No celular o site aparece miniaturizado, obrigando o cliente a dar zoom — a maioria desiste.",
      "Layout responsivo pensado primeiro para celular.")
def mob_viewport(ctx):
    if not ctx.home:
        return None
    meta = ctx.home.soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    return ok() if meta and "width" in (meta.get("content") or "") else fail(_html("<head> sem <meta name=viewport>"))


@rule("MOB-002", Dimension.MOBILE, Severity.HIGH,
      "No celular, o conteúdo ultrapassa ou é cortado na borda da tela",
      "O visitante precisa arrastar a página para os lados para ler — sinal claro de site mal adaptado.",
      "Layout fluido testado em larguras de 360 a 430 px.")
def mob_overflow(ctx):
    if not ctx.mobile:
        return None
    layout = ctx.mobile.layout
    if not layout.get("overflow_horizontal") and layout.get("clipped_text", 0) < 2:
        return ok()
    return fail(_screenshot("screenshot_mobile", label="Conteúdo passa da borda da tela")
                | {"largura_tela": layout.get("viewport_width"), "largura_conteudo": layout.get("scroll_width"),
                   "textos_cortados": layout.get("clipped_text", 0)})


@rule("MOB-003", Dimension.MOBILE, Severity.MEDIUM,
      "{pct}% dos textos são pequenos demais para ler no celular",
      "Letras miúdas cansam e afastam o leitor, principalmente o público acima de 40 anos.",
      "Corpo de texto com no mínimo 16 px e hierarquia tipográfica clara.")
def mob_font(ctx):
    if not ctx.mobile:
        return None
    ratio = ctx.mobile.layout.get("small_text_ratio", 0)
    return ok() if ratio <= 0.2 else fail(_metric(round(ratio * 100), 5, "%"), pct=round(ratio * 100))


@rule("MOB-004", Dimension.MOBILE, Severity.MEDIUM,
      "{n} botões ou links são pequenos demais para tocar com o dedo",
      "Botões pequenos geram toques errados e frustração justamente na hora de entrar em contato.",
      "Áreas de toque de pelo menos 44×44 px, bem espaçadas.")
def mob_tap(ctx):
    if not ctx.mobile:
        return None
    n = ctx.mobile.layout.get("small_tap_targets", 0)
    if n <= 10:
        return ok()
    return fail(_screenshot("screenshot_mobile_full", ctx.mobile.layout.get("small_tap_target_boxes"),
                            "Áreas de toque pequenas"), n=n)


@rule("MOB-005", Dimension.MOBILE, Severity.CRITICAL,
      "O site usa tecnologia obsoleta (Flash) que não abre em celulares",
      "Parte do site simplesmente não aparece para quem acessa pelo celular ou por navegadores atuais.",
      "Recursos visuais em HTML5/CSS modernos.")
def mob_flash(ctx):
    if not ctx.tech:
        return None
    flash = any(t["nome"] == "Flash" for t in ctx.tech.get("tecnologias", []))
    return fail() if flash else ok()


# ---------------------------------------------------------------- SEO

@rule("SEO-001", Dimension.SEO, Severity.HIGH,
      "O título da página no Google está ausente ou genérico",
      "O título é a primeira coisa que aparece na busca do Google; sem ele, o site perde cliques para concorrentes.",
      "Título único por página com serviço + cidade (ex.: “Clínica odontológica em {cidade}”).")
def seo_title(ctx):
    if not ctx.home:
        return None
    title = (ctx.home.soup.title.string or "").strip() if ctx.home.soup.title else ""
    bad = len(title) < 10 or title.lower() in GENERIC_TITLES
    return fail(_html(f"<title>{title}</title>"), cidade=ctx.city or "sua cidade") if bad else ok()


@rule("SEO-002", Dimension.SEO, Severity.MEDIUM,
      "A página não tem descrição para o Google",
      "Sem descrição, o Google mostra um trecho aleatório do site — menos convincente para quem pesquisa.",
      "Meta description persuasiva em cada página, com serviço, cidade e chamada para contato.")
def seo_description(ctx):
    if not ctx.home:
        return None
    meta = ctx.home.soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    content = (meta.get("content") or "").strip() if meta else ""
    return ok() if len(content) >= 50 else fail(_html(f'<meta name="description" content="{content}">'))


@rule("SEO-003", Dimension.SEO, Severity.MEDIUM,
      "A estrutura de títulos da página está incorreta ({n} títulos principais)",
      "O Google usa o título principal (H1) para entender do que trata a página.",
      "Um H1 por página, com o serviço principal, e subtítulos organizados.")
def seo_h1(ctx):
    if not ctx.home:
        return None
    n = len(ctx.home.soup.find_all("h1"))
    return ok() if n == 1 else fail(_metric(n, 1), n=n)


@rule("SEO-004", Dimension.SEO, Severity.LOW,
      "O site não tem mapa do site (sitemap.xml)",
      "O Google demora mais para encontrar e atualizar as páginas do site.",
      "Sitemap gerado automaticamente e enviado ao Google Search Console.")
def seo_sitemap(ctx):
    if ctx.sitemap_ok is None:
        return None
    return ok() if ctx.sitemap_ok else fail()


@rule("SEO-005", Dimension.SEO, Severity.CRITICAL,
      "O arquivo robots.txt impede o Google de ler o site",
      "O site pode estar invisível nas buscas do Google.",
      "robots.txt revisado, liberando as páginas públicas.")
def seo_robots(ctx):
    if not ctx.crawl or ctx.crawl.robots_txt is None:
        return None
    from urllib.robotparser import RobotFileParser

    body = ctx.crawl.robots_txt
    parser = RobotFileParser()
    parser.parse(body.splitlines())
    home = ctx.home.final_url if ctx.home else ctx.url
    return ok() if parser.can_fetch("Googlebot", home) else fail(_html(body[:300]))


@rule("SEO-006", Dimension.SEO, Severity.MEDIUM,
      "O site não informa ao Google os dados do negócio local",
      "Sem dados estruturados, o Google tem menos segurança para mostrar endereço, horário e avaliações na busca.",
      "Dados estruturados LocalBusiness (schema.org) com nome, endereço, telefone, horário e área atendida.")
def seo_schema(ctx):
    if not ctx.pages:
        return None
    for page in ctx.pages:
        for script in page.soup.find_all("script", type="application/ld+json"):
            if LOCAL_BUSINESS_TYPES.search(script.string or script.get_text() or ""):
                return ok()
        if page.soup.find(attrs={"itemtype": LOCAL_BUSINESS_TYPES}):
            return ok()
    return fail()


@rule("SEO-007", Dimension.SEO, Severity.MEDIUM,
      "A cidade ({cidade}) não aparece na página inicial",
      "Quem pesquisa “serviço + cidade” no Google dificilmente encontra um site que não cita a cidade.",
      "Textos e títulos com a cidade e os bairros atendidos.")
def seo_city(ctx):
    if not ctx.home or not ctx.city:
        return None
    from apps.core.text import normalize

    return ok() if normalize(ctx.city) in normalize(ctx.home_text) else fail(cidade=ctx.city)


@rule("SEO-008", Dimension.SEO, Severity.CRITICAL,
      "A página inicial está marcada para não aparecer no Google (noindex)",
      "O site não aparece nas buscas — é como ter uma loja sem placa na rua.",
      "Configuração de indexação revisada antes da publicação.")
def seo_noindex(ctx):
    if not ctx.home:
        return None
    meta = ctx.home.soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    header = ctx.home.headers.get("x-robots-tag", "")
    blocked = "noindex" in ((meta.get("content") or "") if meta else "").lower() or "noindex" in header.lower()
    return fail() if blocked else ok()


@rule("SEO-009", Dimension.SEO, Severity.LOW,
      "{pct}% das imagens não têm descrição (texto alternativo)",
      "O Google não entende imagens sem descrição e o site perde espaço na busca por imagens.",
      "Texto alternativo descritivo em todas as imagens relevantes.")
def seo_alt(ctx):
    imgs = [img for p in ctx.pages for img in p.soup.find_all("img")]
    if not imgs:
        return None
    missing = sum(1 for img in imgs if not (img.get("alt") or "").strip())
    ratio = missing / len(imgs)
    return ok() if ratio <= 0.3 else fail(_metric(missing, 0), pct=round(ratio * 100))


# ---------------------------------------------------------------- Acessibilidade

@rule("A11Y-001", Dimension.ACCESSIBILITY, Severity.HIGH,
      "Foram encontradas {n} barreiras graves de acessibilidade",
      "Pessoas com deficiência visual ou motora não conseguem usar partes do site — e a Lei Brasileira de "
      "Inclusão exige acessibilidade.",
      "Site novo em conformidade com WCAG 2.1 AA, testado com leitor de tela e teclado.")
def a11y_axe(ctx):
    axe = ctx.axe
    if not axe or "por_impacto" not in axe:
        return None
    grave = [v for v in axe["violacoes"] if v.get("impact") in ("critical", "serious")]
    if not grave:
        return ok()
    boxes = [b for v in grave for b in v.get("caixas", [])][:8]
    return fail(
        _screenshot("screenshot_desktop_full", boxes, "Elementos com barreiras")
        | {"violacoes": [{"id": v["id"], "descricao": v["help"], "ocorrencias": v["nodes"]} for v in grave[:6]]},
        Severity.CRITICAL if axe["por_impacto"].get("critical", 0) >= 3 else None,
        n=len(grave),
    )


@rule("A11Y-002", Dimension.ACCESSIBILITY, Severity.LOW,
      "A página não declara o idioma",
      "Leitores de tela podem ler o conteúdo com pronúncia errada.",
      "Atributo lang=\"pt-BR\" em todas as páginas.")
def a11y_lang(ctx):
    if not ctx.home:
        return None
    html = ctx.home.soup.find("html")
    return ok() if html is not None and html.get("lang") else fail(_html("<html> sem atributo lang"))


@rule("A11Y-003", Dimension.ACCESSIBILITY, Severity.MEDIUM,
      "Há textos com pouco contraste com o fundo",
      "Texto claro sobre fundo claro é difícil de ler no sol, no celular e para quem enxerga pouco.",
      "Paleta com contraste mínimo de 4,5:1 em todos os textos.")
def a11y_contrast(ctx):
    axe = ctx.axe
    if not axe or "violacoes" not in axe:
        return None
    v = next((v for v in axe["violacoes"] if v["id"] == "color-contrast"), None)
    if not v:
        return ok()
    return fail(_screenshot("screenshot_desktop_full", v.get("caixas"), "Texto com baixo contraste")
                | {"ocorrencias": v["nodes"]})


# ---------------------------------------------------------------- Segurança

@rule("SEC-001", Dimension.SECURITY, Severity.CRITICAL,
      "Site sem HTTPS: o navegador mostra “Não seguro”",
      "O aviso de “Não seguro” afasta clientes e o Google rebaixa sites sem HTTPS nas buscas.",
      "Certificado SSL gratuito com renovação automática e redirecionamento de todo o tráfego para HTTPS.")
def sec_https(ctx):
    if not ctx.security:
        return None
    return ok() if ctx.security.get("https") else fail(_screenshot("screenshot_desktop", label="Sem cadeado"))


@rule("SEC-002", Dimension.SECURITY, Severity.CRITICAL,
      "O certificado de segurança do site está com problema ({motivo})",
      "Navegadores exibem uma tela de alerta de perigo antes de abrir o site.",
      "Certificado válido com renovação automática e monitoramento de expiração.")
def sec_cert(ctx):
    cert = ctx.security.get("certificado") if ctx.security else None
    if not cert or cert.get("sem_https"):
        return None
    if not cert.get("valido"):
        return fail({"tipo": "tecnico", "erro": cert.get("erro")}, motivo="inválido")
    days = cert.get("dias_para_expirar", 99)
    if days < 0:
        return fail({"tipo": "tecnico", **cert}, motivo="expirado")
    if days < 15:
        return fail({"tipo": "tecnico", **cert}, Severity.MEDIUM, motivo=f"expira em {days} dias")
    return ok()


@rule("SEC-003", Dimension.SECURITY, Severity.HIGH,
      "O endereço sem HTTPS não redireciona para a versão segura",
      "Parte dos visitantes continua entrando pela versão “Não segura” do site.",
      "Redirecionamento permanente (301) de HTTP para HTTPS e HSTS.")
def sec_redirect(ctx):
    if not ctx.security or not ctx.security.get("https"):
        return None
    redirect = ctx.security.get("http_redireciona_https")
    if redirect is None:
        return None
    return ok() if redirect else fail()


@rule("SEC-004", Dimension.SECURITY, Severity.LOW,
      "Faltam {n} proteções básicas de segurança no servidor",
      "Sem esses cabeçalhos, o site fica mais exposto a ataques comuns, como clickjacking.",
      "Cabeçalhos HSTS, CSP, X-Frame-Options, X-Content-Type-Options e Referrer-Policy configurados.")
def sec_headers(ctx):
    headers = ctx.security.get("cabecalhos") if ctx.security else None
    if not headers:
        return None
    missing = [k for k, present in headers.items() if not present]
    return ok() if len(missing) < 3 else fail({"tipo": "tecnico", "ausentes": missing}, n=len(missing))


@rule("SEC-005", Dimension.SECURITY, Severity.HIGH,
      "O site usa versões desatualizadas: {lista}",
      "Sistemas desatualizados são o principal alvo de invasões — o site pode ser pichado ou espalhar vírus "
      "com o nome da empresa.",
      "Plataforma atualizada, com atualizações automáticas de segurança e backups.")
def sec_outdated(ctx):
    if not ctx.tech:
        return None
    alerts = [t for t in ctx.tech.get("alertas", []) if t.get("desatualizado")]
    if not alerts:
        return ok()
    lista = ", ".join(f"{t['nome']} {t['versao']}" for t in alerts)
    return fail({"tipo": "tecnico", "tecnologias": alerts}, lista=lista)


@rule("SEC-006", Dimension.SECURITY, Severity.LOW,
      "O servidor revela as versões de software em uso",
      "Informar versões facilita o trabalho de quem procura falhas conhecidas.",
      "Ocultar cabeçalhos Server/X-Powered-By detalhados.")
def sec_exposed(ctx):
    if not ctx.security:
        return None
    exposed = {k: v for k, v in ctx.security.get("versoes_expostas", {}).items() if re.search(r"\d", v)}
    return fail({"tipo": "tecnico", "cabecalhos": exposed}) if exposed else ok()


@rule("SEC-007", Dimension.SECURITY, Severity.MEDIUM,
      "A página segura carrega arquivos sem segurança (conteúdo misto)",
      "O navegador pode bloquear imagens e scripts ou remover o cadeado de segurança.",
      "Todos os recursos servidos por HTTPS.")
def sec_mixed(ctx):
    if not ctx.security or not ctx.security.get("https"):
        return None
    mixed = ctx.security.get("conteudo_misto") or []
    return fail({"tipo": "tecnico", "recursos": mixed[:5]}) if mixed else ok()


# ---------------------------------------------------------------- Conteúdo

@rule("CONT-001", Dimension.CONTENT, Severity.HIGH,
      "O telefone da empresa não aparece no site",
      "O cliente que quer ligar precisa procurar o número em outro lugar — e pode acabar ligando para o concorrente.",
      "Telefone visível no topo e no rodapé de todas as páginas, clicável no celular.")
def cont_phone(ctx):
    if not ctx.pages:
        return None
    has_tel = any(h.lower().startswith("tel:") for h, _ in ctx.links)
    return ok() if has_tel or PHONE_RE.search(ctx.all_text) else fail()


@rule("CONT-002", Dimension.CONTENT, Severity.MEDIUM,
      "O endereço completo não aparece no site",
      "Clientes locais querem saber onde a empresa fica antes de decidir; o Google também usa essa informação.",
      "Endereço completo com CEP, mapa e botão “Como chegar”.")
def cont_address(ctx):
    if not ctx.pages:
        return None
    return ok() if ADDRESS_RE.search(ctx.all_text) or CEP_RE.search(ctx.all_text) else fail()


@rule("CONT-003", Dimension.CONTENT, Severity.LOW,
      "O horário de atendimento não está informado",
      "O cliente não sabe se pode ligar ou visitar agora e deixa para depois (ou desiste).",
      "Horário de atendimento no rodapé e na página de contato, igual ao Google Business.")
def cont_hours(ctx):
    if not ctx.pages:
        return None
    return ok() if HOURS_RE.search(ctx.all_text) else fail()


@rule("CONT-004", Dimension.CONTENT, Severity.MEDIUM,
      "O site aparenta estar abandonado (última data: {ano})",
      "Um rodapé com ano antigo passa a impressão de que a empresa não cuida do próprio site — ou fechou.",
      "Conteúdo atualizado, com rodapé automático e seção de novidades.")
def cont_stale(ctx):
    if not ctx.tech or ctx.tech.get("anos_desde_copyright") is None:
        return None
    years = ctx.tech["anos_desde_copyright"]
    return ok() if years < 2 else fail(_metric(ctx.tech["ano_copyright"]), ano=ctx.tech["ano_copyright"])


@rule("CONT-005", Dimension.CONTENT, Severity.LOW,
      "O site não mostra depoimentos ou avaliações de clientes",
      "Prova social é um dos fatores que mais influenciam a decisão de contratar um serviço local.",
      "Seção de depoimentos com avaliações reais do Google.")
def cont_testimonials(ctx):
    if not ctx.pages:
        return None
    return ok() if TESTIMONIAL_RE.search(ctx.all_text) else fail()


@rule("CONT-006", Dimension.CONTENT, Severity.LOW,
      "A página inicial quase não tem fotos",
      "Sem fotos do espaço e da equipe, o cliente não cria confiança nem sabe o que esperar.",
      "Fotos profissionais do ambiente, da equipe e dos serviços.")
def cont_photos(ctx):
    if not ctx.desktop:
        return None
    n = ctx.desktop.layout.get("images", 0)
    return ok() if n >= 3 else fail(_metric(n, 5))


@rule("CONT-007", Dimension.CONTENT, Severity.LOW,
      "Não há uma página “Sobre” ou “Quem somos”",
      "Quem visita quer saber quem está por trás do serviço antes de entrar em contato.",
      "Página “Sobre” com história, equipe, registros profissionais e diferenciais.")
def cont_about(ctx):
    if not ctx.pages:
        return None
    return ok() if any(ABOUT_RE.search(f"{h} {t}") for h, t in ctx.links) else fail()


@rule("CONT-008", Dimension.CONTENT, Severity.MEDIUM,
      "A página inicial tem pouco texto ({n} palavras)",
      "Sem explicar bem os serviços, o site não convence o visitante nem aparece no Google.",
      "Textos claros sobre cada serviço, pensados para o cliente e para a busca local.")
def cont_thin(ctx):
    if not ctx.home:
        return None
    n = len(ctx.home_text.split())
    return ok() if n >= 150 else fail(_metric(n, 300, "palavras"), n=n)


# ---------------------------------------------------------------- Conversão

@rule("CONV-001", Dimension.CONVERSION, Severity.HIGH,
      "Não há botão de WhatsApp no site",
      "O WhatsApp é o canal preferido do brasileiro para pedir orçamento; sem o botão, o contato fica mais difícil.",
      "Botão flutuante de WhatsApp com mensagem pré-preenchida em todas as páginas.")
def conv_whatsapp(ctx):
    if not ctx.pages:
        return None
    has = any(re.search(r"wa\.me|api\.whatsapp\.com|whatsapp://|web\.whatsapp\.com", h, re.I) for h, _ in ctx.links)
    return ok() if has else fail()


@rule("CONV-002", Dimension.CONVERSION, Severity.MEDIUM,
      "O site não tem formulário de contato",
      "Quem visita fora do horário comercial não tem como deixar um pedido.",
      "Formulário curto (nome, telefone, mensagem) com aviso de privacidade e resposta automática.")
def conv_form(ctx):
    if not ctx.pages:
        return None
    for page in ctx.pages:
        for form in page.soup.find_all("form"):
            if form.find(["textarea"]) or form.find("input", attrs={"type": re.compile("email|tel", re.I)}):
                return ok()
    return fail()


@rule("CONV-003", Dimension.CONVERSION, Severity.HIGH,
      "No celular, não há botão de contato visível na primeira tela",
      "O visitante precisa rolar e procurar como falar com a empresa — muitos desistem antes.",
      "Chamada para ação (WhatsApp/agendar) visível logo na primeira tela do celular.")
def conv_cta_fold(ctx):
    if not ctx.mobile:
        return None
    above = [c for c in ctx.mobile.layout.get("ctas", []) if c.get("acima_da_dobra")]
    return ok() if above else fail(_screenshot("screenshot_mobile", label="Primeira tela sem botão de contato"))


@rule("CONV-004", Dimension.CONVERSION, Severity.LOW,
      "O site não tem mapa ou link “Como chegar”",
      "O cliente precisa copiar o endereço para outro aplicativo para encontrar a empresa.",
      "Mapa incorporado e botão “Como chegar” que abre o Google Maps/Waze.")
def conv_map(ctx):
    if not ctx.pages:
        return None
    has_link = any(re.search(r"google\.[a-z.]+/maps|maps\.google|goo\.gl/maps|maps\.app\.goo\.gl|waze\.com", h, re.I)
                   for h, _ in ctx.links)
    has_iframe = re.search(r"<iframe[^>]+(google\.[a-z.]+/maps|maps\.google)", ctx.all_html, re.I)
    return ok() if has_link or has_iframe else fail()


@rule("CONV-005", Dimension.CONVERSION, Severity.MEDIUM,
      "O telefone não é clicável no celular",
      "No celular, o cliente precisa decorar e digitar o número em vez de ligar com um toque.",
      "Telefones como links “tel:” e botão “Ligar agora”.")
def conv_tel_link(ctx):
    if not ctx.pages or not PHONE_RE.search(ctx.all_text):
        return None
    return ok() if any(h.lower().startswith("tel:") for h, _ in ctx.links) else fail()


@rule("CONV-006", Dimension.CONVERSION, Severity.MEDIUM,
      "Não há agendamento online",
      "Clientes esperam marcar horário sem precisar ligar; sem isso, a agenda perde encaixes fora do horário.",
      "Integração com agenda online (ex.: Google Agenda, Doctoralia) direto do site.")
def conv_scheduling(ctx):
    if not ctx.pages or not any("agend" in item.lower() for item in ctx.checklist):
        return None  # só se aplica a categorias que exigem agendamento
    has = any(SCHEDULING_RE.search(f"{h} {t}") for h, t in ctx.links)
    return ok() if has else fail()


@rule("CONV-007", Dimension.CONVERSION, Severity.LOW,
      "O site não leva para as redes sociais da empresa",
      "Redes sociais mostram que a empresa está ativa e reforçam a confiança.",
      "Links para Instagram, Facebook e perfil do Google no topo ou rodapé.")
def conv_social(ctx):
    if not ctx.pages:
        return None
    has = any(re.search(r"instagram\.com|facebook\.com|linkedin\.com|youtube\.com|tiktok\.com", h, re.I)
              for h, _ in ctx.links)
    return ok() if has else fail()


# ---------------------------------------------------------------- Conformidade (LGPD)

@rule("LGPD-001", Dimension.COMPLIANCE, Severity.HIGH,
      "O site não tem política de privacidade",
      "A LGPD exige informar como os dados dos visitantes são usados; a falta expõe a empresa a reclamações e multas.",
      "Política de privacidade clara, com canal do encarregado de dados, linkada em todas as páginas.")
def lgpd_policy(ctx):
    if not ctx.pages:
        return None
    return ok() if any(PRIVACY_RE.search(f"{h} {t}") for h, t in ctx.links) else fail()


@rule("LGPD-002", Dimension.COMPLIANCE, Severity.MEDIUM,
      "O site usa rastreadores/cookies sem aviso ao visitante",
      "Coletar dados de navegação sem avisar contraria a LGPD e as orientações da ANPD.",
      "Aviso de cookies com opção de recusar os não essenciais.")
def lgpd_cookies(ctx):
    if not ctx.tech:
        return None
    trackers = [t["nome"] for t in ctx.tech.get("tecnologias", []) if t["categoria"] in ("Análise", "Marketing")]
    if not trackers:
        return ok()
    banner = ctx.desktop.layout.get("cookie_banner") if ctx.desktop else None
    if banner is None:
        banner = bool(re.search(r"cookie", ctx.home_text, re.I))
    return ok() if banner else fail({"tipo": "tecnico", "rastreadores": trackers})


@rule("LGPD-003", Dimension.COMPLIANCE, Severity.LOW,
      "O formulário coleta dados sem mencionar privacidade ou consentimento",
      "Quem preenche não sabe para que seus dados serão usados.",
      "Texto de consentimento e link para a política de privacidade junto ao formulário.")
def lgpd_form_consent(ctx):
    forms = [f for p in ctx.pages for f in p.soup.find_all("form")
             if f.find("input", attrs={"type": re.compile("email|tel|text", re.I)})]
    if not forms:
        return None
    return ok() if any(CONSENT_RE.search(f.get_text(" ")) for f in forms) else fail()


def evaluate(ctx: AuditContext) -> list[dict]:
    """Avalia todas as regras ativas. Retorna uma linha por regra com o resultado."""
    from apps.catalog.models import Rule as RuleModel

    disabled = set(RuleModel.objects.filter(ativo=False).values_list("codigo", flat=True))
    results = []
    for r in RULES:
        if r.code in disabled:
            continue
        try:
            outcome = r.check(ctx)
        except Exception as exc:  # regra com defeito não derruba a auditoria
            results.append({"rule": r, "outcome": None, "erro": str(exc)[:200]})
            continue
        results.append({"rule": r, "outcome": outcome})
    return results


def rule_catalog() -> list[dict]:
    return [
        {"codigo": r.code, "dimensao": r.dimension.value, "descricao": r.description,
         "severidade_padrao": r.severity.value}
        for r in RULES
    ]

