from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.core.jobs import enqueue

from .models import Search, Website


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def discover_companies(self, search_id):
    from .services import run_search

    search = Search.objects.select_related("category", "municipality").get(pk=search_id)
    try:
        run_search(search)
    except Exception as exc:
        search.status = Search.Status.FAILED
        search.erro = str(exc)[:500]
        search.save(update_fields=["status", "erro"])
        raise
    return search_id


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def enrich_website(self, website_id):
    from .services import enrich_website as enrich

    website = Website.objects.select_related("company").filter(pk=website_id).first()
    if website:
        enrich(website)
    return website_id


@shared_task(bind=True, max_retries=1)
def probe_email_domain(self, company_id, domain, names):
    """Testa o domínio do e-mail do CNPJ como site da empresa (fonte gratuita)."""
    from .models import Company
    from .services import probe_email_domain as probe

    company = Company.objects.filter(pk=company_id).first()
    if company:
        website = probe(company, domain, names)
        return website.pk if website else None
    return None


@shared_task
def recheck_sites():
    """Mensal: rechecagem de status (site fora do ar, HTTPS etc.)."""
    stale = Website.objects.filter(ultimo_check__lt=timezone.now() - timedelta(days=28)) | Website.objects.filter(
        ultimo_check__isnull=True
    )
    count = 0
    for website_id in stale.values_list("pk", flat=True):
        enqueue(enrich_website, website_id)
        count += 1
    return count
