from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from rest_framework.routers import DefaultRouter

from apps.accounts import views as auth_views
from apps.accounts.admin_views import UserViewSet
from apps.audits.views import AuditViewSet, FindingViewSet
from apps.catalog.views import CategoryViewSet, RuleViewSet
from apps.core import views as core_views
from apps.geo.views import municipalities
from apps.leads.views import CompanyViewSet, LeadNoteViewSet, SearchViewSet
from apps.reports.views import BriefingViewSet, ReportViewSet, legal_page, public_report, report_preview
from apps.sitebuilder.views import SiteProjectViewSet, robots_for, serve_site

if settings.REQUIRE_2FA:
    from django_otp.admin import OTPAdminSite

    admin.site.__class__ = OTPAdminSite  # o /admin também exige o código do autenticador

router = DefaultRouter(trailing_slash=False)
router.register("categories", CategoryViewSet)
router.register("rules", RuleViewSet)
router.register("searches", SearchViewSet)
router.register("companies", CompanyViewSet)
router.register("notes", LeadNoteViewSet)
router.register("audits", AuditViewSet)
router.register("findings", FindingViewSet)
router.register("reports", ReportViewSet)
router.register("briefings", BriefingViewSet)
router.register("users", UserViewSet)
router.register("prompts", core_views.PromptVersionViewSet)
router.register("sites", SiteProjectViewSet)

api = [
    path("auth/me", auth_views.me),
    path("auth/login", auth_views.login_view),
    path("auth/logout", auth_views.logout_view),
    path("auth/2fa/setup", auth_views.totp_setup),
    path("auth/2fa/confirm", auth_views.totp_confirm),
    path("municipalities", municipalities),
    path("dashboard", core_views.dashboard),
    path("settings/brand", core_views.brand),
    path("settings/capabilities", core_views.capabilities),
    path("api-usage", core_views.api_usage),
    path("health", core_views.health),
    path("", include(router.urls)),
]

urlpatterns = [
    # Painel e relatórios não são indexados; no host das prévias de sites gerados, só /s/ é liberado.
    path("robots.txt", robots_for),
    path("admin/", admin.site.urls),
    path("api/", include(api)),
    path("r/<str:token>", public_report, name="public-report"),
    path("s/<str:token>/", serve_site, name="site-preview"),
    re_path(r"^s/(?P<token>[\w-]+)/(?P<path>[\w./-]+)$", serve_site),
    path("preview/relatorio/<int:pk>", report_preview, name="report-preview"),
    path("privacidade", legal_page("legal/privacidade.html"), name="privacy"),
    path("exclusao-de-dados", legal_page("legal/exclusao.html"), name="data-deletion"),
]

# Arquivos enviados (capturas, PDFs). Em produção com S3 as URLs apontam direto para o bucket.
urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

# Painel React compilado (frontend/dist), servido pelo próprio Django em produção.
if settings.FRONTEND_DIST.exists():
    from django.views.generic import TemplateView

    urlpatterns += [
        re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": settings.FRONTEND_DIST / "assets"}),
        re_path(r"^(?P<path>favicon\.svg)$", serve, {"document_root": settings.FRONTEND_DIST}),
        re_path(r"^(?!api/|admin/|r/|s/|media/|static/|privacidade|exclusao-de-dados).*$",
                TemplateView.as_view(template_name="index.html")),
    ]
