"""Etapas 2 e 4 — capturas (1440 px e 390 px), métricas de campo e axe-core.

Usa Playwright (Chromium headless). Se o navegador não estiver instalado,
as etapas são marcadas como "não medidas" e o restante da auditoria segue.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}
MAX_FULL_HEIGHT = 8000
AXE_PATH = Path(settings.BASE_DIR) / "node_modules" / "axe-core" / "axe.min.js"

CTA_PATTERN = r"whats|zap|contato|fale|agend|marcar|or[çc]amento|ligue|ligar|solicit|reserv|compre|comprar|consulta"

METRICS_JS = """
() => new Promise(resolve => {
  let lcp = 0, cls = 0;
  try {
    new PerformanceObserver(l => { for (const e of l.getEntries()) lcp = e.startTime; })
      .observe({type: 'largest-contentful-paint', buffered: true});
    new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) cls += e.value; })
      .observe({type: 'layout-shift', buffered: true});
  } catch (e) {}
  setTimeout(() => {
    const nav = performance.getEntriesByType('navigation')[0] || {};
    resolve({
      lcp_ms: Math.round(lcp) || null,
      cls: Math.round(cls * 1000) / 1000,
      ttfb_ms: Math.round((nav.responseStart || 0) - (nav.requestStart || 0)) || null,
      dom_content_loaded_ms: Math.round(nav.domContentLoadedEventEnd || 0) || null,
      load_ms: Math.round(nav.loadEventEnd || 0) || null,
    });
  }, 1500);
})
"""

LAYOUT_JS = """
(ctaPattern) => {
  const re = new RegExp(ctaPattern, 'i');
  const vh = window.innerHeight, vw = window.innerWidth;
  const visible = el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const box = el => { const r = el.getBoundingClientRect();
    return {x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height)}; };
  const ctas = [];
  for (const el of document.querySelectorAll('a, button, [role=button]')) {
    const label = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('href') || '').trim();
    if (!re.test(label) || !visible(el)) continue;
    const r = el.getBoundingClientRect();
    ctas.push({texto: label.slice(0, 60), acima_da_dobra: r.top + scrollY < vh, ...box(el)});
  }
  let smallText = 0, textNodes = 0;
  for (const el of document.querySelectorAll('p, li, a, span, td')) {
    if (!el.innerText || !el.innerText.trim() || !visible(el)) continue;
    textNodes++;
    if (parseFloat(getComputedStyle(el).fontSize) < 12) smallText++;
  }
  const smallTargets = [];
  for (const el of document.querySelectorAll('a[href], button')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 24) smallTargets.push(box(el));
  }
  // Texto cortado na borda direita (comum quando o site esconde o excesso com overflow:hidden).
  let clipped = 0;
  for (const el of document.querySelectorAll('h1, h2, h3, p, li, a, button')) {
    if (!visible(el) || !(el.innerText || '').trim()) continue;
    const r = el.getBoundingClientRect();
    if (r.left < vw && r.right > vw + 5) clipped++;
  }
  const imgs = [...document.images];
  return {
    viewport_width: vw,
    scroll_width: document.documentElement.scrollWidth,
    overflow_horizontal: document.documentElement.scrollWidth > vw + 5,
    clipped_text: clipped,
    page_height: document.documentElement.scrollHeight,
    ctas,
    small_text_ratio: textNodes ? Math.round(smallText / textNodes * 100) / 100 : 0,
    small_tap_targets: smallTargets.length,
    small_tap_target_boxes: smallTargets.slice(0, 8),
    images: imgs.length,
    images_oversized: imgs.filter(i => i.naturalWidth > 2 * Math.max(i.clientWidth, 1) && i.naturalWidth > 1200).length,
    iframes_maps: document.querySelectorAll('iframe[src*="google.com/maps"], iframe[src*="maps.google"]').length,
    cookie_banner: [...document.querySelectorAll(
      '[id*=cookie i], [class*=cookie i], [id*=consent i], [class*=consent i], [class*=lgpd i], [id*=lgpd i]'
    )].some(visible),
  };
}
"""


@dataclass
class ViewportCapture:
    name: str
    fold_png: bytes | None = None
    full_jpg: bytes | None = None
    metrics: dict = field(default_factory=dict)
    layout: dict = field(default_factory=dict)
    bytes_total: int = 0
    requests: int = 0
    console_errors: int = 0
    mixed_content: list[str] = field(default_factory=list)
    third_party_hosts: list[str] = field(default_factory=list)


@dataclass
class BrowserResult:
    desktop: ViewportCapture | None = None
    mobile: ViewportCapture | None = None
    axe: dict = field(default_factory=dict)
    error: str = ""


def browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return True


def run_browser(url: str, extra_pages: list[str], run_axe: bool = True) -> BrowserResult:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    result = BrowserResult()
    timeout_ms = settings.CRAWLER_PAGE_TIMEOUT * 1000
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            result.desktop = _capture(browser, url, "desktop", DESKTOP, 1, timeout_ms)
            result.mobile = _capture(
                browser, url, "mobile", MOBILE, 2, timeout_ms, is_mobile=True,
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                    f"(KHTML, like Gecko) Mobile/15E148 {settings.CRAWLER_USER_AGENT}"
                ),
            )
            if run_axe and AXE_PATH.exists():
                result.axe = _run_axe(browser, [url, *extra_pages[:3]], timeout_ms)
            elif run_axe:
                result.axe = {"erro": "axe-core não instalado (rode `npm install` em backend/)"}
        except PlaywrightError as exc:
            result.error = str(exc).splitlines()[0][:300]
        finally:
            browser.close()
    return result


def _capture(browser, url, name, viewport, scale, timeout_ms, is_mobile=False, user_agent=None) -> ViewportCapture:
    from urllib.parse import urlparse

    ua = user_agent or f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 {settings.CRAWLER_USER_AGENT}"
    context = browser.new_context(
        viewport=viewport, device_scale_factor=scale, is_mobile=is_mobile, has_touch=is_mobile,
        user_agent=ua, locale="pt-BR", ignore_https_errors=True,
    )
    cap = ViewportCapture(name=name)
    page = context.new_page()
    home_host = urlparse(url).hostname or ""
    hosts = set()

    def on_finished(request):
        try:
            sizes = request.sizes()
            cap.bytes_total += sizes.get("responseBodySize", 0) + sizes.get("responseHeadersSize", 0)
        except Exception:
            pass
        cap.requests += 1
        host = urlparse(request.url).hostname or ""
        if host and not host.endswith(home_host.removeprefix("www.")):
            hosts.add(host)
        if url.startswith("https://") and request.url.startswith("http://"):
            cap.mixed_content.append(request.url[:200])

    page.on("requestfinished", on_finished)
    page.on("console", lambda msg: setattr(cap, "console_errors", cap.console_errors + (msg.type == "error")))
    page.goto(url, wait_until="load", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    cap.metrics = page.evaluate(METRICS_JS)
    cap.layout = page.evaluate(LAYOUT_JS, CTA_PATTERN)
    cap.fold_png = page.screenshot(type="png")
    height = min(cap.layout.get("page_height") or viewport["height"], MAX_FULL_HEIGHT)
    cap.full_jpg = page.screenshot(
        type="jpeg", quality=70, full_page=True,
        clip={"x": 0, "y": 0, "width": viewport["width"], "height": height},
    )
    cap.third_party_hosts = sorted(hosts)[:40]
    context.close()
    return cap


def _run_axe(browser, urls, timeout_ms) -> dict:
    script = AXE_PATH.read_text(encoding="utf-8")
    context = browser.new_context(viewport=DESKTOP, locale="pt-BR", ignore_https_errors=True)
    by_rule: dict[str, dict] = {}
    pages_ok = 0
    for target in urls:
        page = context.new_page()
        try:
            page.goto(target, wait_until="load", timeout=timeout_ms)
            page.add_script_tag(content=script)
            raw = page.evaluate(
                """async () => {
                  const r = await axe.run(document, {
                    runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']},
                    resultTypes: ['violations']});
                  return r.violations.map(v => ({
                    id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl,
                    nodes: v.nodes.length,
                    exemplos: v.nodes.slice(0, 3).map(n => ({alvo: n.target.join(' '), html: n.html.slice(0, 200)}))
                  }));
                }"""
            )
            if target == urls[0]:
                for v in raw:
                    v["caixas"] = _boxes_for(page, [ex["alvo"] for ex in v["exemplos"]])
            pages_ok += 1
            for v in raw:
                agg = by_rule.setdefault(v["id"], {**v, "nodes": 0, "paginas": []})
                agg["nodes"] += v["nodes"]
                agg["paginas"].append(target)
        except Exception as exc:
            logger.info("axe falhou em %s: %s", target, exc)
        finally:
            page.close()
    context.close()
    counts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    for v in by_rule.values():
        counts[v.get("impact") or "minor"] = counts.get(v.get("impact") or "minor", 0) + 1
    return {"paginas_analisadas": pages_ok, "violacoes": list(by_rule.values()), "por_impacto": counts}


def _boxes_for(page, selectors):
    boxes = []
    for sel in selectors:
        try:
            bb = page.locator(sel).first.bounding_box(timeout=1000)
        except Exception:
            bb = None
        if bb:
            scroll_y = page.evaluate("() => scrollY")
            boxes.append({"x": round(bb["x"]), "y": round(bb["y"] + scroll_y), "w": round(bb["width"]),
                          "h": round(bb["height"])})
    return boxes
