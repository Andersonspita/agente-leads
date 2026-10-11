"""Etapa 6 — detecção de tecnologia (CMS, versão, plugins, ano do copyright).

Assinaturas no estilo do Wappalyzer, mantidas localmente para não depender de
bibliotecas abandonadas. Cada item: nome, categoria, padrões e extrator de versão.
"""
import re
from datetime import date

SIGNATURES = [
    # nome, categoria, padrões no HTML, padrões em cabeçalhos, regex de versão
    ("WordPress", "CMS", [r"/wp-content/", r"/wp-includes/"], [], r'content="WordPress ([\d.]+)"'),
    ("Joomla", "CMS", [r"/media/jui/", r"Joomla!"], [], r'content="Joomla! ([\d.]+)'),
    ("Drupal", "CMS", [r"/sites/default/files/", r"Drupal.settings"], ["x-drupal-cache", "x-generator"], r'content="Drupal (\d+)'),
    ("Wix", "Construtor de sites", [r"static\.wixstatic\.com", r"wix\.com"], ["x-wix-request-id"], None),
    ("Squarespace", "Construtor de sites", [r"static1\.squarespace\.com"], [], None),
    ("Webflow", "Construtor de sites", [r"webflow\.js", r"data-wf-site"], [], None),
    ("Shopify", "E-commerce", [r"cdn\.shopify\.com"], [], None),
    ("Nuvemshop", "E-commerce", [r"nuvemshop", r"tiendanube"], [], None),
    ("Elementor", "Plugin WordPress", [r"/plugins/elementor/"], [], r"elementor(?:-pro)?/assets/[^\"']*\?ver=([\d.]+)"),
    ("WPBakery", "Plugin WordPress", [r"js_composer"], [], r"js_composer[^\"']*\?ver=([\d.]+)"),
    ("Contact Form 7", "Plugin WordPress", [r"/plugins/contact-form-7/"], [], r"contact-form-7[^\"']*\?ver=([\d.]+)"),
    ("Yoast SEO", "Plugin WordPress", [r"yoast"], [], r"Yoast SEO(?: plugin)? v([\d.]+)"),
    ("Revolution Slider", "Plugin WordPress", [r"revslider"], [], r"revslider[^\"']*\?ver=([\d.]+)"),
    ("jQuery", "Biblioteca JS", [r"jquery[\w.-]*\.js"], [],
     r"jquery[.-]([\d.]+)(?:\.min)?\.js|jquery(?:\.min)?\.js\?ver=([\d.]+)"),
    ("Bootstrap", "Framework CSS", [r"bootstrap(?:\.min)?\.(?:css|js)"], [], r"bootstrap[@/-]([\d.]+)"),
    ("React", "Framework JS", [r"data-reactroot", r"__NEXT_DATA__", r"react-dom"], [], None),
    ("Next.js", "Framework JS", [r"__NEXT_DATA__", r"/_next/"], ["x-nextjs-cache"], None),
    ("Vue.js", "Framework JS", [r"data-v-[0-9a-f]{8}", r"__NUXT__"], [], None),
    ("Google Analytics", "Análise", [r"googletagmanager\.com/gtag", r"google-analytics\.com"], [], None),
    ("Google Tag Manager", "Análise", [r"googletagmanager\.com/gtm\.js"], [], None),
    ("Meta Pixel", "Marketing", [r"connect\.facebook\.net/.*/fbevents\.js"], [], None),
    ("reCAPTCHA", "Segurança", [r"google\.com/recaptcha"], [], None),
    ("Cloudflare", "CDN", [r"cdnjs\.cloudflare\.com"], ["cf-ray"], None),
    ("PHP", "Linguagem", [], ["x-powered-by:php"], r"PHP/([\d.]+)"),
    ("Flash", "Obsoleto", [r"\.swf[\"']", r"application/x-shockwave-flash"], [], None),
]

# Versões abaixo destas são consideradas desatualizadas (revise periodicamente).
MIN_SAFE_VERSIONS = {
    "WordPress": (6, 4),
    "Joomla": (4, 4),
    "Drupal": (10,),
    "jQuery": (3, 5),
    "PHP": (8, 1),
    "Bootstrap": (4, 6),
}

COPYRIGHT_RE = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", re.I)


def _version_tuple(v: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", v)[:3])


def detect(html: str, headers: dict) -> dict:
    found = []
    header_blob = "\n".join(f"{k}:{v}" for k, v in headers.items()).lower()
    for name, category, html_patterns, header_patterns, version_re in SIGNATURES:
        hit = any(re.search(p, html, re.I) for p in html_patterns) or any(
            p.lower() in header_blob for p in header_patterns
        )
        if not hit:
            continue
        version = None
        if version_re:
            m = re.search(version_re, html, re.I) or re.search(version_re, header_blob, re.I)
            if m:
                version = next((g for g in m.groups() if g), "").strip(".") or None
        outdated = None
        if version and name in MIN_SAFE_VERSIONS:
            outdated = _version_tuple(version) < MIN_SAFE_VERSIONS[name]
        found.append({"nome": name, "categoria": category, "versao": version, "desatualizado": outdated})

    years = [int(y) for y in COPYRIGHT_RE.findall(html)]
    copyright_year = max(years) if years else None
    return {
        "tecnologias": found,
        "cms": next((t["nome"] for t in found if t["categoria"] in ("CMS", "Construtor de sites")), None),
        "ano_copyright": copyright_year,
        "anos_desde_copyright": (date.today().year - copyright_year) if copyright_year else None,
        "alertas": [t for t in found if t["desatualizado"] or t["categoria"] == "Obsoleto"],
    }
