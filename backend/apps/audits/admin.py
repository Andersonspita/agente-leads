from django.contrib import admin

from .models import Artifact, Audit, AuditStep, Finding


class StepInline(admin.TabularInline):
    model = AuditStep
    extra = 0


@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
    list_display = ["id", "website", "status", "nota_geral", "criado_em", "concluido_em"]
    list_filter = ["status"]
    inlines = [StepInline]


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ["titulo", "audit", "dimensao", "severidade", "origem", "status_revisao"]
    list_filter = ["origem", "status_revisao", "dimensao"]


admin.site.register(Artifact)
