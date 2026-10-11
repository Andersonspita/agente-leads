from dataclasses import dataclass, field
from functools import cached_property

from .crawler import CrawlResult, Page


@dataclass
class AuditContext:
    """Tudo o que as etapas mediram; as regras só leem daqui (a IA nunca fornece números)."""

    url: str
    crawl: CrawlResult | None = None
    browser: object | None = None  # BrowserResult
    lighthouse: dict = field(default_factory=dict)
    security: dict = field(default_factory=dict)
    tech: dict = field(default_factory=dict)
    sitemap_ok: bool | None = None
    city: str = ""
    checklist: list[str] = field(default_factory=list)

    @property
    def pages(self) -> list[Page]:
        return [p for p in (self.crawl.pages if self.crawl else []) if p.ok]

    @property
    def home(self) -> Page | None:
        return self.pages[0] if self.pages else None

    @cached_property
    def all_html(self) -> str:
        return "\n".join(p.html for p in self.pages)

    @cached_property
    def all_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    @cached_property
    def home_text(self) -> str:
        return self.home.text if self.home else ""

    @cached_property
    def links(self) -> list[tuple[str, str]]:
        """(href, texto) de todos os links rastreados."""
        out = []
        for page in self.pages:
            for a in page.soup.find_all("a", href=True):
                out.append((a["href"].strip(), a.get_text(" ", strip=True)))
        return out

    @property
    def mobile(self):
        return getattr(self.browser, "mobile", None)

    @property
    def desktop(self):
        return getattr(self.browser, "desktop", None)

    @property
    def axe(self) -> dict:
        return getattr(self.browser, "axe", {}) or {}

    def lh(self, preset: str) -> dict:
        return self.lighthouse.get(preset) or {}
