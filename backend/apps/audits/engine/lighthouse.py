"""Etapa 3 — Lighthouse (mobile e desktop), mediana de N execuções."""
import json
import os
import shlex
import shutil
import statistics
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]
METRIC_AUDITS = {
    "lcp_ms": "largest-contentful-paint",
    "cls": "cumulative-layout-shift",
    "tbt_ms": "total-blocking-time",
    "fcp_ms": "first-contentful-paint",
    "si_ms": "speed-index",
    "peso_bytes": "total-byte-weight",
}


def lighthouse_command() -> list[str] | None:
    if settings.LIGHTHOUSE_CMD:
        return shlex.split(settings.LIGHTHOUSE_CMD, posix=os.name != "nt")
    local = Path(settings.BASE_DIR) / "node_modules" / ".bin" / ("lighthouse.cmd" if os.name == "nt" else "lighthouse")
    if local.exists():
        return [str(local)]
    found = shutil.which("lighthouse")
    return [found] if found else None


def chrome_path() -> str | None:
    if os.getenv("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return p.chromium.executable_path
    except Exception:
        return None


def _run_once(cmd, url, preset, timeout) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report.json"
        args = [
            *cmd, url, "--output=json", f"--output-path={out}", "--quiet",
            "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage",
            f"--only-categories={','.join(CATEGORIES)}",
            "--locale=pt-BR", "--max-wait-for-load=45000",
        ]
        if preset == "desktop":
            args.append("--preset=desktop")
        env = {**os.environ}
        if chrome := chrome_path():
            env["CHROME_PATH"] = chrome
        subprocess.run(args, check=True, timeout=timeout, capture_output=True, env=env)
        return json.loads(out.read_text(encoding="utf-8"))


def summarize(report: dict) -> dict:
    cats = report.get("categories", {})
    audits = report.get("audits", {})
    return {
        "scores": {c: round((cats.get(c, {}).get("score") or 0) * 100) for c in CATEGORIES if c in cats},
        "metricas": {k: audits.get(a, {}).get("numericValue") for k, a in METRIC_AUDITS.items()},
        "oportunidades": [
            {"id": a["id"], "titulo": a.get("title"), "economia_ms": a.get("details", {}).get("overallSavingsMs")}
            for a in audits.values()
            if a.get("details", {}).get("type") == "opportunity" and (a.get("score") or 1) < 0.9
        ][:8],
    }


LOCK_PATH = Path(tempfile.gettempdir()) / "auditor-lighthouse.lock"
LOCK_STALE_SECONDS = 180  # uma execução tem limite de 120 s; trava mais velha é de processo que caiu


@contextmanager
def machine_lock(timeout: float):
    """Uma execução do Lighthouse por máquina (vale entre threads e processos/workers).

    Execuções simultâneas do Lighthouse no mesmo computador falham (NO_NAVSTART) ou distorcem as
    métricas, como alerta a própria documentação do Lighthouse.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - LOCK_PATH.stat().st_mtime > LOCK_STALE_SECONDS:
                    LOCK_PATH.unlink(missing_ok=True)  # trava esquecida por um processo que caiu
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError("Lighthouse ocupado com outra auditoria")
            time.sleep(1)
    try:
        yield
    finally:
        LOCK_PATH.unlink(missing_ok=True)


def _error_text(exc) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        tail = (exc.stderr or b"").decode(errors="ignore").strip().splitlines()
        return tail[-1][:200] if tail else f"código {exc.returncode}"
    return str(exc)[:200]


def run_lighthouse(url: str, runs: int | None = None, timeout: int = 120, wait: float = 240) -> dict:
    """Roda Lighthouse mobile e desktop (uma execução por vez na máquina) e guarda a mediana de cada um."""
    cmd = lighthouse_command()
    if not cmd:
        return {"indisponivel": "Lighthouse não instalado (npm install em backend/ ou LIGHTHOUSE_CMD)"}
    runs = runs or settings.LIGHTHOUSE_RUNS
    result = {}
    for preset in ("mobile", "desktop"):
        summaries, raw_reports = [], []
        for _ in range(runs):
            try:
                with machine_lock(wait):
                    raw = _run_once(cmd, url, preset, timeout)
            except (subprocess.SubprocessError, OSError, json.JSONDecodeError, TimeoutError) as exc:
                result.setdefault("erros", []).append(f"{preset}: {_error_text(exc)}")
                continue
            summaries.append(summarize(raw))
            raw_reports.append(raw)
        if summaries:
            perf = [x["scores"].get("performance", 0) for x in summaries]
            idx = perf.index(statistics.median_low(perf))
            result[preset] = summaries[idx]
            result[f"{preset}_raw"] = raw_reports[idx]
    return result
