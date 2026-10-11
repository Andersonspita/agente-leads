"""Renderiza os arquivos do site gerado (HTML, SVGs, robots, sitemap) a partir do conteúdo editável."""
import io
import json
import zipfile
from urllib.parse import quote

from django.template.loader import render_to_string
from django.utils import timezone

ICONS = {
    "zap": '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm5.4 14.1c-.2.6-1.3 1.2-1.8 1.2-.5.1-1 .2-3.3-.7-2.8-1.1-4.6-4-4.7-4.2-.1-.2-1.1-1.5-1.1-2.9s.7-2.1 1-2.4c.3-.3.6-.3.8-.3h.6c.2 0 .4 0 .6.5l.9 2.1c.1.2.1.4 0 .5l-.4.6-.4.4c-.1.2-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.3.1.5.1.6-.1l.9-1c.2-.3.4-.2.7-.1l2 1c.3.1.5.2.5.3.1.2.1.7-.1 1.3Z"/></svg>',
    "tel": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" width="18" height="18"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>',
    "relogio": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" width="18" height="18"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
    "mail": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/></svg>',
    "check": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m8 12 3 3 5-6"/></svg>',
    "insta": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor"/></svg>',
    "face": '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M14 22v-8h3l1-4h-4V8c0-.6.4-1 1-1h3V3h-3a5 5 0 0 0-5 5v2H7v4h3v8Z"/></svg>',
}
CATEGORY_ICONS = {
    "dente": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M7 3c-2.5 0-4 2-4 4.5 0 3 1.5 4.5 2 7.5.4 2.6 1 6 2.5 6s1.8-3.5 2.5-5.5c.3-.8 1.7-.8 2 0 .7 2 1 5.5 2.5 5.5s2.1-3.4 2.5-6c.5-3 2-4.5 2-7.5C21 5 19.5 3 17 3c-2 0-3 1-5 1S9 3 7 3Z"/></svg>',
    "saude": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/><path d="M3.2 12h4.3l1.5-3 3 6 1.5-3h7.3"/></svg>',
    "balanca": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v18M5 21h14M5 7h14M3 7l-1 6a4 4 0 0 0 6 0L7 7M17 7l-1 6a4 4 0 0 0 6 0l-1-6"/></svg>',
    "grafico": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/></svg>',
    "casa": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1Z"/></svg>',
    "estrela": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m12 2 3 6.5 7 .8-5.2 4.8 1.5 7-6.3-3.6-6.3 3.6 1.5-7L2 9.3l7-.8Z"/></svg>',
    "prato": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="13" r="7"/><circle cx="12" cy="13" r="3"/><path d="M3 2v6M5 2v6M4 8v14M20 2c-1.5 1-2 3-2 6h2v14"/></svg>',
}


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(color: str) -> float:
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _darken(color: str, factor: float = 0.6) -> str:
    return "#" + "".join(f"{int(c * factor):02x}" for c in _hex_to_rgb(color))


def _fmt_phone(d: str) -> str:
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return d


def _initials(name: str) -> str:
    words = [w for w in name.split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "•"


def illustration(kind: str, c: dict) -> str:
    """Ilustrações abstratas na paleta da marca (marcadas para troca por fotos reais)."""
    cor, dest = c["cor"], c["cor_destaque"]
    icon = CATEGORY_ICONS.get(c.get("icone"), CATEGORY_ICONS["estrela"])
    inner = icon.replace('<svg viewBox="0 0 24 24"', '<svg x="{x}" y="{y}" width="{s}" height="{s}" viewBox="0 0 24 24"')
    if kind == "destaque":
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420">'
            f'<circle cx="210" cy="210" r="200" fill="#ffffff" opacity=".12"/>'
            f'<rect x="70" y="90" width="280" height="240" rx="36" fill="#ffffff"/>'
            f'<rect x="100" y="125" width="130" height="14" rx="7" fill="{cor}" opacity=".9"/>'
            f'<rect x="100" y="152" width="200" height="10" rx="5" fill="{cor}" opacity=".25"/>'
            f'<rect x="100" y="172" width="170" height="10" rx="5" fill="{cor}" opacity=".25"/>'
            f'<rect x="100" y="270" width="150" height="34" rx="17" fill="#0a7d3b"/>'
            f'<circle cx="320" cy="96" r="44" fill="{dest}"/>'
            f'<g color="{cor}">{inner.format(x=150, y=195, s=60)}</g>'
            f'<g color="#ffffff">{inner.format(x=298, y=74, s=44)}</g>'
            '</svg>'
        )
    if kind == "sobre":
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 420">'
            f'<rect width="520" height="420" rx="28" fill="{cor}" opacity=".08"/>'
            f'<circle cx="170" cy="190" r="90" fill="{cor}" opacity=".18"/>'
            f'<circle cx="340" cy="230" r="110" fill="{dest}" opacity=".25"/>'
            f'<rect x="120" y="120" width="280" height="190" rx="26" fill="#ffffff"/>'
            f'<g color="{cor}">{inner.format(x=225, y=160, s=70)}</g>'
            f'<rect x="170" y="255" width="180" height="12" rx="6" fill="{cor}" opacity=".3"/>'
            '</svg>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 300">'
        f'<rect width="520" height="300" rx="24" fill="{cor}" opacity=".07"/>'
        f'<path d="M0 210 C120 160 200 250 320 200 S470 150 520 180 V300 H0Z" fill="{cor}" opacity=".12"/>'
        f'<path d="M60 0 V300 M200 0 V300 M380 0 V300 M0 90 H520 M0 220 H520" stroke="{cor}" stroke-opacity=".12" stroke-width="10"/>'
        f'<circle cx="270" cy="140" r="36" fill="{dest}"/>'
        f'<path d="M270 205 c-28-35-48-55-48-80 a48 48 0 0 1 96 0 c0 25-20 45-48 80Z" fill="{cor}"/>'
        '<circle cx="270" cy="125" r="16" fill="#ffffff"/>'
        '</svg>'
    )


def build_context(c: dict, base_url: str) -> dict:
    tel = c.get("telefone") or ""
    zap = c.get("whatsapp") or ""
    endereco = ", ".join(p for p in (c.get("endereco"), c.get("bairro")) if p)
    cidade_uf = f"{c.get('cidade', '')} - {c.get('uf', '')}".strip(" -")
    endereco_completo = ", ".join(p for p in (endereco, cidade_uf) if p)
    if c.get("cep"):
        cep = c["cep"]
        endereco_completo += f", CEP {cep[:5]}-{cep[5:]}" if len(cep) == 8 else f", CEP {cep}"
    zap_base = f"https://wa.me/55{zap}" if zap else ""
    agendamento = bool(c.get("agendamento"))
    cnpj = c.get("cnpj") or ""
    nota = c.get("nota_google")
    return {
        "c": c,
        "base_url": base_url,
        "cor_escura": _darken(c["cor"], 0.55),
        "destaque_txt": "#111111" if _luminance(c["cor_destaque"]) > 0.25 else "#ffffff",
        "iniciais": _initials(c["empresa"]),
        "tel_link": f"tel:+55{tel}" if tel else "",
        "telefone_fmt": _fmt_phone(tel),
        "zap_base": zap_base,
        "zap_link": f"{zap_base}?text={quote('Olá! Vim pelo site e gostaria de mais informações.')}" if zap else "",
        "whatsapp_fmt": _fmt_phone(zap),
        "agendamento": agendamento,
        "endereco_completo": endereco_completo,
        "mapa_link": "https://www.google.com/maps/search/?api=1&query=" + quote(f"{c['empresa']}, {endereco_completo}"),
        "avaliacoes_link": "https://www.google.com/search?q=" + quote(f"{c['empresa']} {c.get('cidade', '')} avaliações"),
        "nota_fmt": f"{nota:.1f}".replace(".", ",") if nota else "",
        "cnpj_fmt": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}" if len(cnpj) == 14 else "",
        "sobre_paragrafos": [p.strip() for p in (c.get("sobre") or "").split("\n\n") if p.strip()],
        "hoje": timezone.localdate().strftime("%d/%m/%Y"),
        "jsonld": json.dumps(_jsonld(c, base_url, endereco, tel), ensure_ascii=False).replace("</", "<\\/"),
        **{f"icon_{k}": v for k, v in ICONS.items()},
        "icon_categoria": CATEGORY_ICONS.get(c.get("icone"), CATEGORY_ICONS["estrela"]),
    }


def _jsonld(c, base_url, endereco, tel):
    data = {
        "@context": "https://schema.org",
        "@type": ["LocalBusiness", c.get("schema_tipo") or "LocalBusiness"],
        "name": c["empresa"],
        "url": base_url,
        "description": c.get("descricao_seo", ""),
        "address": {"@type": "PostalAddress", "streetAddress": endereco, "addressLocality": c.get("cidade", ""),
                    "addressRegion": c.get("uf", ""), "postalCode": c.get("cep", ""), "addressCountry": "BR"},
        "areaServed": c.get("cidade", ""),
        "openingHours": c.get("horario", ""),
    }
    if tel:
        data["telephone"] = f"+55{tel}"
    same_as = [u for u in (c.get("instagram"), c.get("facebook")) if u]
    if same_as:
        data["sameAs"] = same_as
    if c.get("nota_google") and c.get("n_avaliacoes"):
        data["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": c["nota_google"],
                                   "reviewCount": c["n_avaliacoes"]}
    if data["@type"][1] == "LocalBusiness":
        data["@type"] = "LocalBusiness"
    return data


def favicon(c: dict) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" '
            f'fill="{c["cor"]}"/><text x="32" y="42" text-anchor="middle" font-family="Georgia,serif" '
            f'font-size="28" fill="#fff">{_initials(c["empresa"])}</text></svg>')


def render_files(content: dict, base_url: str) -> dict[str, tuple[bytes, str]]:
    """{caminho: (conteúdo, content-type)} — o mesmo conjunto serve para a prévia e para o .zip."""
    ctx = build_context(content, base_url)
    files = {
        "index.html": (render_to_string("sitebuilder/index.html", ctx), "text/html; charset=utf-8"),
        "politica-de-privacidade.html": (render_to_string("sitebuilder/privacidade.html", ctx),
                                         "text/html; charset=utf-8"),
        "favicon.svg": (favicon(content), "image/svg+xml"),
        "img/destaque.svg": (illustration("destaque", content), "image/svg+xml"),
        "img/sobre.svg": (illustration("sobre", content), "image/svg+xml"),
        "img/contato.svg": (illustration("contato", content), "image/svg+xml"),
        "robots.txt": (f"User-agent: *\nAllow: /\nSitemap: {base_url}sitemap.xml\n", "text/plain; charset=utf-8"),
        "sitemap.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{base_url}</loc></url><url><loc>{base_url}politica-de-privacidade.html</loc></url></urlset>\n",
            "application/xml",
        ),
    }
    return {path: (body.encode("utf-8") if isinstance(body, str) else body, ctype)
            for path, (body, ctype) in files.items()}


def build_zip(content: dict, base_url: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, (body, _) in render_files(content, base_url).items():
            zf.writestr(path, body)
        zf.writestr("LEIA-ME.txt", (
            f"Site de {content['empresa']}\n\n"
            "Publique estes arquivos em qualquer hospedagem com HTTPS (a pasta inteira, mantendo a estrutura).\n"
            f"Antes de publicar, ajuste o endereço em robots.txt, sitemap.xml e na tag canonical (hoje: {base_url}).\n\n"
            "Itens a confirmar com o cliente:\n" + "\n".join(f"- {i}" for i in content.get("a_confirmar", []))
        ).encode("utf-8"))
    return buf.getvalue()
