"""Orquestra as 9 etapas de uma auditoria (TRD 2.4).

Cada etapa é independente: se uma falha, as outras seguem e o relatório indica
o que não pôde ser medido. Lighthouse roda em paralelo com o rastreio/capturas
para caber no limite de 5 minutos por auditoria.
"""
import json
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.audits.models import STEPS, Artifact, Audit, AuditStep, Finding
from apps.leads.models import LeadStatus

from . import ai, rules, scoring, security, tech
from .browser import DESKTOP, MAX_FULL_HEIGHT, MOBILE, browser_available, run_browser
from .context import AuditContext
from .crawler import Crawler
from .lighthouse import lighthouse_command, run_lighthouse

logger = logging.getLogger(__name__)


class StepSkipped(Exception):
    """A etapa não pôde ser medida (ferramenta ausente, site bloqueou etc.)."""


class AuditAborted(Exception):
    pass


class AuditRunner:
    def __init__(self, audit: Audit):
        self.audit = audit
        self.website = audit.website
        self.company = self.website.company
        self.deadline = time.monotonic() + settings.AUDIT_TIMEOUT
        category = self.company.category
        self.ctx = AuditContext(
            url=self.website.url_final or self.website.url,
            city=self.company.municipality.nome if self.company.municipality else "",
            checklist=list(category.checklist.values_list("item", flat=True)) if category else [],
        )
        self.weights = category.weights() if category else _default_weights()

    # ------------------------------------------------------------ infraestrutura

    def _ensure_steps(self):
        for order, key, _ in STEPS:
            AuditStep.objects.get_or_create(audit=self.audit, etapa=key, defaults={"ordem": order})

    @contextmanager
    def step(self, key, always=False):
        step = AuditStep.objects.get(audit=self.audit, etapa=key)
        if time.monotonic() > self.deadline and not always:
            step.status = AuditStep.Status.SKIPPED
            step.erro = "Tempo máximo da auditoria atingido"
            step.save()
            yield None
            return
        step.status = AuditStep.Status.RUNNING
        step.save(update_fields=["status"])
        started = time.monotonic()
        try:
            yield step
            if step.status == AuditStep.Status.RUNNING:
                step.status = AuditStep.Status.DONE
        except StepSkipped as exc:
            step.status = AuditStep.Status.SKIPPED
            step.erro = str(exc)
        except AuditAborted:
            step.status = AuditStep.Status.FAILED
            raise
        except Exception as exc:
            logger.exception("Etapa %s falhou na auditoria %s", key, self.audit.pk)
            step.status = AuditStep.Status.FAILED
            step.erro = f"{type(exc).__name__}: {str(exc)[:500]}"
        finally:
            step.duracao_ms = int((time.monotonic() - started) * 1000)
            step.save()

    def _save_artifact(self, kind, content: bytes, ext: str, meta=None):
        if not content:
            return None
        artifact = Artifact(audit=self.audit, tipo=kind, tamanho=len(content), meta=meta or {})
        artifact.arquivo.save(f"{secrets.token_hex(12)}_{kind}.{ext}", ContentFile(content), save=True)
        return artifact

    # ------------------------------------------------------------ execução

    def run(self):
        audit = self.audit
        audit.status = Audit.Status.RUNNING
        audit.iniciado_em = timezone.now()
        audit.versao_regras = rules.RULES_VERSION
        audit.save(update_fields=["status", "iniciado_em", "versao_regras"])
        self._ensure_steps()

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lighthouse")
        try:
            self._step_crawl()
            self._step_browser()
            # Lighthouse depois das capturas (Chromium disputando CPU distorce as métricas) e só se o site
            # respondeu; enquanto ele roda, seguem as etapas leves.
            lh_future = pool.submit(self._lighthouse_job, self.ctx.url) if lighthouse_command() else None
            self._step_accessibility()
            self._step_security()
            self._step_tech()
            self._step_lighthouse(lh_future)
            self._step_rules()  # depois do Lighthouse: as regras de desempenho usam as métricas dele
            self._step_scoring()  # sempre roda: é instantâneo e a nota não depende da IA
            audit.status = Audit.Status.DONE
        except AuditAborted as exc:
            audit.status = Audit.Status.FAILED
            audit.erro = str(exc)
            AuditStep.objects.filter(audit=audit, status=AuditStep.Status.PENDING).update(
                status=AuditStep.Status.SKIPPED, erro="Auditoria interrompida"
            )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            audit.concluido_em = timezone.now()
            audit.save()
        if audit.status == Audit.Status.DONE and self.company.status_lead == LeadStatus.FOUND:
            self.company.status_lead = LeadStatus.AUDITED
            self.company.save(update_fields=["status_lead", "atualizado_em"])
        if audit.status == Audit.Status.DONE:
            self._queue_ai()
        return audit

    def _queue_ai(self):
        """Etapa 8 em job próprio (fila "ai"): a auditoria termina com nota sem esperar a IA."""
        from apps.core.jobs import enqueue

        from ..tasks import ai_analysis

        step = AuditStep.objects.get(audit=self.audit, etapa="ia")
        if not ai.is_configured():
            step.status = AuditStep.Status.SKIPPED
            step.erro = "IA desativada (configure GEMINI_API_KEY no .env)"
            step.save(update_fields=["status", "erro"])
            return
        step.status = AuditStep.Status.PENDING
        step.erro = ""
        step.iniciado_em = timezone.now()
        step.save(update_fields=["status", "erro", "iniciado_em"])
        enqueue(ai_analysis, self.audit.pk)

    @staticmethod
    def _lighthouse_job(url):
        close_old_connections()
        try:
            return run_lighthouse(url)
        finally:
            close_old_connections()

    def _step_crawl(self):
        with self.step("rastreio") as step:
            if step is None:
                raise AuditAborted("Tempo esgotado antes do rastreio")
            try:
                crawl = Crawler().crawl(self.ctx.url)
            except Exception as exc:
                self.website.online = False
                self.website.ultimo_check = timezone.now()
                self.website.save(update_fields=["online", "ultimo_check"])
                raise AuditAborted(f"Site fora do ar ou inacessível: {str(exc)[:200]}") from exc
            self.ctx.crawl = crawl
            home = crawl.home
            self.website.status_http = home.status
            self.website.url_final = home.final_url[:500]
            self.website.https = home.final_url.startswith("https://")
            self.website.online = home.status < 500
            self.website.ultimo_check = timezone.now()
            if crawl.blocked:
                self.website.auditavel = False
            self.website.save()
            self.ctx.url = home.final_url
            step.resultado = {
                "paginas": [{"url": p.final_url, "status": p.status, "ms": p.elapsed_ms} for p in crawl.pages],
                "robots_txt": crawl.robots_txt is not None,
                "robots_permite": crawl.robots_allows_home,
                "sitemaps": crawl.sitemap_urls,
                # Texto das páginas para a análise de IA, que roda em job separado depois da auditoria.
                "textos": [{"url": p.final_url, "texto": p.text[:3000]} for p in crawl.pages[:6] if p.ok],
            }
            if crawl.blocked:
                raise AuditAborted("O site bloqueou o robô (Cloudflare/captcha). Marque como não auditável "
                                   "ou envie capturas manualmente.")
            if not crawl.robots_allows_home:
                raise AuditAborted("O robots.txt do site não permite o rastreio; auditoria não realizada.")
            if not home.ok:
                raise AuditAborted(f"A página inicial respondeu com status {home.status}.")

    def _step_browser(self):
        with self.step("capturas") as step:
            if step is None:
                return
            if not browser_available():
                raise StepSkipped("Playwright não instalado")
            extra = [p.final_url for p in self.ctx.pages[1:]]
            result = run_browser(self.ctx.url, extra)
            self.ctx.browser = result
            if result.error and not result.desktop:
                raise StepSkipped(f"Navegador não conseguiu abrir o site: {result.error}")
            for cap, fold_kind, full_kind, viewport in (
                (result.desktop, Artifact.Kind.SCREENSHOT_DESKTOP, Artifact.Kind.SCREENSHOT_DESKTOP_FULL, DESKTOP),
                (result.mobile, Artifact.Kind.SCREENSHOT_MOBILE, Artifact.Kind.SCREENSHOT_MOBILE_FULL, MOBILE),
            ):
                if cap:
                    full_height = min(cap.layout.get("page_height") or viewport["height"], MAX_FULL_HEIGHT)
                    self._save_artifact(fold_kind, cap.fold_png, "png", {"largura": viewport["width"],
                                                                         "altura": viewport["height"]})
                    self._save_artifact(full_kind, cap.full_jpg, "jpg", {"largura": viewport["width"],
                                                                         "altura": full_height})
            step.resultado = {
                name: {"metricas": cap.metrics, "layout": {k: v for k, v in cap.layout.items() if "boxes" not in k},
                       "bytes": cap.bytes_total, "requisicoes": cap.requests, "erros_console": cap.console_errors,
                       "terceiros": cap.third_party_hosts}
                for name, cap in (("desktop", result.desktop), ("mobile", result.mobile)) if cap
            }

    def _step_lighthouse(self, future):
        with self.step("lighthouse") as step:
            if step is None:
                return
            if future is None:
                raise StepSkipped("Lighthouse não instalado")
            remaining = max(5, self.deadline - time.monotonic() - 30)
            try:
                result = future.result(timeout=remaining)
            except FutureTimeout as exc:
                raise StepSkipped("Lighthouse excedeu o tempo disponível") from exc
            for preset in ("mobile", "desktop"):
                raw = result.pop(f"{preset}_raw", None)
                if raw:
                    self._save_artifact(Artifact.Kind.LIGHTHOUSE_JSON, json.dumps(raw).encode(), f"{preset}.json")
            self.ctx.lighthouse = result
            step.resultado = result
            if not result.get("mobile") and not result.get("desktop"):
                raise StepSkipped("; ".join(result.get("erros", [])) or result.get("indisponivel", "sem resultado"))

    def _step_accessibility(self):
        with self.step("acessibilidade") as step:
            if step is None:
                return
            axe = self.ctx.axe
            if not axe or "por_impacto" not in axe:
                raise StepSkipped(axe.get("erro") if axe else "Capturas indisponíveis; axe não executado")
            step.resultado = {
                "paginas_analisadas": axe["paginas_analisadas"],
                "por_impacto": axe["por_impacto"],
                "violacoes": [{k: v for k, v in item.items() if k != "caixas"} for item in axe["violacoes"]],
            }

    def _step_security(self):
        with self.step("seguranca") as step:
            if step is None:
                return
            if self.website.origem == "gerado":
                raise StepSkipped("Site gerado em prévia: HTTPS, certificado e cabeçalhos de segurança são "
                                  "configurados na hospedagem, ao publicar")
            home = self.ctx.home
            mixed = self.ctx.desktop.mixed_content if self.ctx.desktop else []
            self.ctx.security = security.check_security(self.ctx.url, home.final_url, home.headers, mixed)
            step.resultado = self.ctx.security

    def _step_tech(self):
        with self.step("tecnologia") as step:
            if step is None:
                return
            home = self.ctx.home
            self.ctx.tech = tech.detect(self.ctx.all_html, home.headers)
            self.website.tecnologias = self.ctx.tech["tecnologias"]
            self.website.save(update_fields=["tecnologias"])
            step.resultado = self.ctx.tech

    def _probe_sitemap(self):
        crawler = Crawler()
        candidates = self.ctx.crawl.sitemap_urls or []
        base = self.ctx.url.split("/", 3)
        root = "/".join(base[:3])
        candidates = [*candidates, f"{root}/sitemap.xml", f"{root}/sitemap_index.xml"]
        for url in candidates[:3]:
            try:
                resp = crawler.get(url, timeout=15)
            except Exception:
                continue
            head = resp.text[:2000]
            if resp.status_code == 200 and ("<urlset" in head or "<sitemapindex" in head):
                return True
        return False

    def _step_rules(self):
        with self.step("conteudo") as step:
            if step is None:
                return
            self.ctx.sitemap_ok = self._probe_sitemap()
            results = rules.evaluate(self.ctx)
            findings = []
            summary = {"aprovadas": [], "reprovadas": [], "nao_medidas": []}
            for item in results:
                r, outcome = item["rule"], item["outcome"]
                if outcome is None:
                    summary["nao_medidas"].append(r.code)
                    continue
                if outcome.passed:
                    summary["aprovadas"].append(r.code)
                    continue
                summary["reprovadas"].append(r.code)
                findings.append(Finding(
                    audit=self.audit,
                    dimensao=r.dimension,
                    rule_id=r.code,
                    origem=Finding.Origin.RULE,
                    severidade=outcome.severity or r.severity,
                    titulo=r.render(r.title, outcome)[:200],
                    descricao=r.description,
                    impacto_negocio=r.render(r.impact, outcome),
                    melhoria_proposta=r.render(r.improvement, outcome),
                    evidencia=outcome.evidence,
                    # Achados de regra são medidos, então nascem confirmados; o analista pode descartar.
                    status_revisao=Finding.Review.CONFIRMED,
                ))
            with transaction.atomic():
                Finding.objects.filter(audit=self.audit, origem=Finding.Origin.RULE).delete()
                Finding.objects.bulk_create(findings)
            self._rule_results = [
                (i["rule"].dimension, (i["outcome"].severity or i["rule"].severity), i["outcome"].passed)
                for i in results if i["outcome"] is not None
            ]
            step.resultado = summary

    def _step_scoring(self):
        with self.step("pontuacao", always=True) as step:
            if step is None:
                return
            mobile_metrics = self.ctx.mobile.metrics if self.ctx.mobile else None
            base = scoring.base_scores(self.ctx.lighthouse, self.ctx.axe, mobile_metrics)
            dims = scoring.dimension_scores(getattr(self, "_rule_results", []), base)
            overall = scoring.overall_score(dims, self.weights)
            self.audit.notas_dimensao = dims
            self.audit.nota_geral = overall
            self.audit.pesos_usados = self.weights
            self.audit.metricas = self._key_metrics()
            step.resultado = {"base_ferramentas": {str(k): round(v) for k, v in base.items()},
                              "notas": dims, "geral": overall}

    def _key_metrics(self) -> dict:
        lh_m = self.ctx.lh("mobile")
        mobile = self.ctx.mobile
        return {
            "lcp_mobile_ms": lh_m.get("metricas", {}).get("lcp_ms") or (mobile.metrics.get("lcp_ms") if mobile else None),
            "cls_mobile": lh_m.get("metricas", {}).get("cls") if lh_m else (mobile.metrics.get("cls") if mobile else None),
            "peso_bytes": lh_m.get("metricas", {}).get("peso_bytes") or (mobile.bytes_total if mobile else None),
            "requisicoes": mobile.requests if mobile else None,
            "lighthouse": {p: self.ctx.lh(p).get("scores") for p in ("mobile", "desktop") if self.ctx.lh(p)},
            "https": self.ctx.security.get("https") if self.ctx.security else None,
            "cms": self.ctx.tech.get("cms") if self.ctx.tech else None,
            "paginas_rastreadas": len(self.ctx.pages),
            "violacoes_acessibilidade": self.ctx.axe.get("por_impacto"),
        }


def run_ai_analysis(audit: Audit, ctx: AuditContext | None, step: AuditStep):
    """Etapa 8. Com ctx=None (reexecução isolada), usa artefatos e texto salvos."""
    if not ai.is_configured():
        raise StepSkipped("IA desativada (configure GEMINI_API_KEY no .env)")
    company = audit.website.company
    desktop_png = mobile_png = None
    texto = ""
    if ctx is not None:
        desktop_png = ctx.desktop.fold_png if ctx.desktop else None
        mobile_png = ctx.mobile.fold_png if ctx.mobile else None
        texto = "\n\n".join(f"[{p.final_url}]\n{p.text[:3000]}" for p in ctx.pages[:6])
    else:
        for art in audit.artifacts.filter(tipo__in=[Artifact.Kind.SCREENSHOT_DESKTOP, Artifact.Kind.SCREENSHOT_MOBILE]):
            with art.arquivo.open("rb") as fh:
                if art.tipo == Artifact.Kind.SCREENSHOT_DESKTOP:
                    desktop_png = fh.read()
                else:
                    mobile_png = fh.read()
        crawl_step = audit.steps.filter(etapa="rastreio").first()
        pages = (crawl_step.resultado or {}).get("paginas", []) if crawl_step else []
        textos = (crawl_step.resultado or {}).get("textos", []) if crawl_step else []
        texto = ("\n\n".join(f"[{t['url']}]\n{t['texto']}" for t in textos)
                 or "Páginas: " + ", ".join(p["url"] for p in pages))
    if not desktop_png and not mobile_png and not texto:
        raise StepSkipped("Sem capturas nem texto para analisar")

    try:
        data = ai.analyze(
            empresa=company.nome,
            categoria=company.category.nome if company.category else "",
            cidade=str(company.municipality) if company.municipality else "",
            desktop_png=desktop_png, mobile_png=mobile_png, texto=texto,
            achados_regras=list(audit.findings.filter(origem=Finding.Origin.RULE).values_list("titulo", flat=True)),
        )
    except ai.AIUnavailable as exc:
        raise StepSkipped(str(exc)) from exc

    with transaction.atomic():
        audit.findings.filter(origem=Finding.Origin.AI, status_revisao=Finding.Review.PENDING).delete()
        Finding.objects.bulk_create([
            Finding(
                audit=audit, dimensao=item["dimensao"], origem=Finding.Origin.AI, severidade=item["severidade"],
                titulo=item["titulo"][:200], descricao=item["descricao"], impacto_negocio=item["impacto_negocio"],
                melhoria_proposta=item["melhoria_proposta"],
                evidencia={"tipo": "captura", "artefato": f"screenshot_{item['captura']}",
                           "legenda": item["local_na_captura"], "caixas": []},
                status_revisao=Finding.Review.PENDING,
            )
            for item in data["achados"]
        ])
    audit.versao_prompt = data["_versao_prompt"]
    audit.save(update_fields=["versao_prompt"])
    step.resultado = {"resumo": data["resumo"], "pontos_fortes": data["pontos_fortes"],
                      "achados": len(data["achados"]), "modelo": data["_modelo"]}


def _default_weights():
    from apps.catalog.models import DEFAULT_WEIGHTS

    return {d.value: float(w) for d, w in DEFAULT_WEIGHTS.items()}
