"""Etapa 5 — segurança: HTTPS, certificado, cabeçalhos e conteúdo misto."""
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from django.conf import settings

SECURITY_HEADERS = {
    "strict-transport-security": "HSTS",
    "content-security-policy": "CSP",
    "x-frame-options": "X-Frame-Options",
    "x-content-type-options": "X-Content-Type-Options",
    "referrer-policy": "Referrer-Policy",
}


def certificate_info(host: str, port: int = 443, timeout: int = 10) -> dict:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                version = tls.version()
    except ssl.SSLCertVerificationError as exc:
        return {"valido": False, "erro": exc.verify_message or str(exc)}
    except (OSError, ssl.SSLError) as exc:
        return {"valido": False, "erro": str(exc)[:200], "sem_https": True}
    expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    issuer = dict(item[0] for item in cert.get("issuer", ()))
    return {
        "valido": True,
        "expira_em": expires.isoformat(),
        "dias_para_expirar": (expires - datetime.now(timezone.utc)).days,
        "emissor": issuer.get("organizationName", ""),
        "protocolo": version,
    }


def http_redirects_to_https(host: str) -> bool | None:
    from .crawler import Crawler

    try:
        resp = Crawler().get(f"http://{host}/", timeout=15)
    except requests.RequestException:
        return None
    return resp.url.startswith("https://")  # url da última resposta, depois dos redirecionamentos


def check_security(home_url: str, final_url: str, headers: dict, mixed_content: list[str]) -> dict:
    host = urlparse(final_url).hostname or urlparse(home_url).hostname
    uses_https = final_url.startswith("https://")
    cert = certificate_info(host) if host else {"valido": False, "erro": "host inválido"}
    present = {label: (name in headers) for name, label in SECURITY_HEADERS.items()}
    exposed = {k: headers[k] for k in ("server", "x-powered-by", "x-aspnet-version") if k in headers}
    return {
        "https": uses_https,
        "http_redireciona_https": http_redirects_to_https(host) if host else None,
        "certificado": cert,
        "cabecalhos": present,
        "versoes_expostas": exposed,
        "conteudo_misto": mixed_content[:10],
    }
