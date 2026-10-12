"""Etapa 1 — rastreio responsável: home + até N páginas internas.

Respeita robots.txt, no máximo 1 requisição/s por domínio, User-Agent identificado
e apenas páginas públicas (PRD 1.6).
"""
import ipaddress
import socket
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from django.conf import settings

PRIORITY_WORDS = (
    "contato", "fale", "sobre", "quem-somos", "quem somos", "empresa", "servico", "serviço",
    "especialidade", "equipe", "agend", "privacidade", "localiza", "onde",
)
SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".doc", ".docx",
                   ".xls", ".xlsx", ".mp4", ".mp3")


class BlockedURL(requests.RequestException):
    """Endereço interno (rede privada, loopback, metadados da nuvem): o robô não acessa."""


def is_public_url(url: str) -> bool:
    """O robô só visita endereços públicos da internet (proteção contra SSRF).

    Exceção: as prévias de sites gerados (/s/...) no host configurado em SITES_BASE_URL.
    shortcut: resolve o DNS antes do acesso, sem fixar o IP; um DNS que muda entre a checagem e a
    conexão (DNS rebinding) passaria. Se virar risco real, conectar no IP já validado.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    sites = urlparse(settings.SITES_BASE_URL)
    if parsed.netloc == sites.netloc and parsed.path.startswith("/s/"):
        return True
    if settings.CRAWLER_ALLOW_PRIVATE:
        return True
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return True  # não resolve: a própria requisição falha logo em seguida
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def check_public(url: str):
    if not is_public_url(url):
        raise BlockedURL(f"Endereço interno bloqueado: {url}")


def friendly_error(exc: Exception) -> str:
    """Erro de acesso ao site em linguagem de gente (o detalhe técnico fica no log)."""
    text = str(exc)
    if isinstance(exc, BlockedURL):
        return "O endereço aponta para uma rede interna e não pode ser auditado."
    if isinstance(exc, requests.exceptions.SSLError):
        return "O certificado de segurança (HTTPS) do site é inválido e a versão sem HTTPS também não abriu."
    if isinstance(exc, requests.Timeout):
        return "O site demorou demais para responder."
    if isinstance(exc, requests.TooManyRedirects):
        return "O site entra em redirecionamento sem fim e não carrega."
    if isinstance(exc, requests.ConnectionError):
        if any(s in text for s in ("NameResolution", "getaddrinfo", "Name or service not known", "nodename")):
            return "O domínio não existe ou não está apontado para nenhum servidor (DNS não encontrado)."
        return "O servidor do site recusou a conexão ou está fora do ar."
    return "O site está fora do ar ou inacessível."


MAX_REDIRECTS = 5
MAX_BODY_BYTES = 3_000_000


def _read_limited(resp: requests.Response):
    """Lê no máximo MAX_BODY_BYTES e por no máximo CRAWLER_PAGE_TIMEOUT segundos no total.

    O timeout do requests vale por leitura: um site que manda 1 byte a cada poucos segundos nunca
    estoura. read1 devolve o que chegou, então o prazo total é conferido a cada pedaço.
    shortcut: com gzip, um pedaço que não descomprime nada é lido dentro do urllib3 sem conferir o
    prazo; se aparecer na prática, ler sem decodificar e descomprimir aqui.
    """
    deadline = time.monotonic() + settings.CRAWLER_PAGE_TIMEOUT
    chunks, size = [], 0
    while size < MAX_BODY_BYTES:
        if time.monotonic() > deadline:
            resp.close()
            raise requests.Timeout(f"A página levou mais de {settings.CRAWLER_PAGE_TIMEOUT} s para chegar")
        chunk = resp.raw.read1(64 * 1024, decode_content=True)
        if not chunk:  # fim da resposta
            break
        chunks.append(chunk)
        size += len(chunk)
    resp._content = b"".join(chunks)[:MAX_BODY_BYTES]  # .text e .content passam a usar só o lido
    resp.close()


class DomainRateLimiter:
    """Garante intervalo mínimo entre requisições ao mesmo domínio, entre threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}

    def wait(self, domain: str):
        with self._lock:
            now = time.monotonic()
            ready_at = self._last.get(domain, 0) + settings.CRAWLER_MIN_INTERVAL
            delay = max(0.0, ready_at - now)
            self._last[domain] = now + delay
        if delay:
            time.sleep(delay)


rate_limiter = DomainRateLimiter()


@dataclass
class Page:
    url: str
    final_url: str
    status: int
    headers: dict
    html: str
    elapsed_ms: int
    redirects: list[str] = field(default_factory=list)
    _soup: BeautifulSoup | None = None

    @property
    def soup(self) -> BeautifulSoup:
        if self._soup is None:
            self._soup = BeautifulSoup(self.html or "", "lxml")
        return self._soup

    @property
    def text(self) -> str:
        soup = BeautifulSoup(self.html or "", "lxml")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return " ".join(soup.get_text(" ").split())

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400 and "html" in self.headers.get("content-type", "html").lower()


@dataclass
class CrawlResult:
    start_url: str
    pages: list[Page]
    robots_txt: str | None
    robots_allows_home: bool
    sitemap_urls: list[str]
    blocked: bool = False
    error: str = ""

    @property
    def home(self) -> Page | None:
        return self.pages[0] if self.pages else None


class Crawler:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
        })

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET que confere cada endereço, inclusive cada redirecionamento, antes de acessar."""
        kwargs.setdefault("timeout", settings.CRAWLER_PAGE_TIMEOUT)
        kwargs.pop("allow_redirects", None)
        history = []
        for _ in range(MAX_REDIRECTS + 1):
            check_public(url)
            rate_limiter.wait(urlparse(url).hostname or "")
            resp = self.session.get(url, allow_redirects=False, stream=True, **kwargs)
            if not resp.is_redirect:
                resp.history = history
                _read_limited(resp)
                return resp
            resp.close()
            history.append(resp)
            url = urljoin(url, resp.headers["location"])
        raise requests.TooManyRedirects(f"Mais de {MAX_REDIRECTS} redirecionamentos")

    def fetch_page(self, url: str) -> Page:
        started = time.monotonic()
        resp = self.get(url)
        elapsed = int((time.monotonic() - started) * 1000)
        content_type = resp.headers.get("content-type", "")
        html = resp.text if "html" in content_type.lower() or not content_type else ""
        return Page(
            url=url,
            final_url=resp.url,
            status=resp.status_code,
            headers={k.lower(): v for k, v in resp.headers.items()},
            html=html,
            elapsed_ms=elapsed,
            redirects=[r.url for r in resp.history],
        )

    def load_robots(self, base: str) -> tuple[RobotFileParser, str | None]:
        parser = RobotFileParser()
        robots_url = urljoin(base, "/robots.txt")
        try:
            resp = self.get(robots_url, timeout=15)
            body = resp.text if resp.status_code == 200 else None
        except requests.RequestException:
            body = None
        parser.parse((body or "").splitlines())
        return parser, body

    def crawl(self, url: str, max_pages: int | None = None) -> CrawlResult:
        max_pages = max_pages or settings.CRAWLER_MAX_PAGES + 1  # home + 10 internas
        if "://" not in url:
            url = "https://" + url
        try:
            home = self.fetch_page(url)
        except requests.exceptions.SSLError:
            # Certificado inválido: tenta HTTP para ainda auditar o conteúdo.
            url = "http://" + url.split("://", 1)[1]
            home = self.fetch_page(url)

        base = f"{urlparse(home.final_url).scheme}://{urlparse(home.final_url).netloc}"
        robots, robots_body = self.load_robots(base)
        ua = settings.CRAWLER_USER_AGENT
        allows_home = robots.can_fetch(ua, home.final_url) if robots_body else True
        sitemaps = list(robots.site_maps() or []) if robots_body else []

        result = CrawlResult(url, [home], robots_body, allows_home, sitemaps)
        if home.status in (401, 403, 429, 503) and _looks_like_bot_wall(home):
            result.blocked = True
            return result
        if not allows_home or not home.ok:
            return result

        seen = {_canonical(home.final_url), _canonical(url)}
        for link in self._internal_links(home, base):
            if len(result.pages) >= max_pages:
                break
            key = _canonical(link)
            if key in seen or (robots_body and not robots.can_fetch(ua, link)):
                continue
            seen.add(key)
            try:
                page = self.fetch_page(link)
            except requests.RequestException:
                continue
            final_key = _canonical(page.final_url)
            if page.ok and (final_key == key or final_key not in seen):
                result.pages.append(page)
                seen.add(final_key)
        return result

    def _internal_links(self, page: Page, base: str) -> list[str]:
        host = urlparse(base).hostname
        links: list[tuple[int, str]] = []
        in_nav = {id(a) for nav in page.soup.select("nav, header, [role=navigation], .menu") for a in nav.find_all("a")}
        for a in page.soup.find_all("a", href=True):
            href = urldefrag(urljoin(page.final_url, a["href"].strip()))[0]
            parsed = urlparse(href)
            if parsed.scheme not in ("http", "https") or _strip_www(parsed.hostname) != _strip_www(host):
                continue
            if parsed.path.lower().endswith(SKIP_EXTENSIONS):
                continue
            label = f"{href} {a.get_text(' ', strip=True)}".lower()
            score = 0 if any(w in label for w in PRIORITY_WORDS) else 2
            if id(a) in in_nav:
                score -= 1
            links.append((score, href))
        links.sort(key=lambda item: item[0])
        ordered, seen = [], set()
        for _, href in links:
            if href not in seen:
                ordered.append(href)
                seen.add(href)
        return ordered


def _strip_www(host):
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def _canonical(url: str) -> str:
    parsed = urlparse(url)
    return f"{_strip_www(parsed.hostname)}{parsed.path.rstrip('/') or '/'}?{parsed.query}"


def _looks_like_bot_wall(page: Page) -> bool:
    body = (page.html or "").lower()
    return any(s in body for s in ("cf-challenge", "captcha", "attention required", "just a moment"))


def check_url(url: str) -> dict:
    """Checagem rápida de enriquecimento: status, redirecionamentos, HTTPS."""
    crawler = Crawler()
    if "://" not in url:
        url = "https://" + url
    try:
        page = crawler.fetch_page(url)
    except requests.exceptions.SSLError:
        try:
            page = crawler.fetch_page("http://" + url.split("://", 1)[1])
        except requests.RequestException as exc:
            return {"online": False, "erro": friendly_error(exc)}
    except requests.RequestException as exc:
        return {"online": False, "erro": friendly_error(exc)}
    return {
        "online": page.status < 500,
        "status_http": page.status,
        "url_final": page.final_url,
        "https": page.final_url.startswith("https://"),
        "html": page.html,
    }
