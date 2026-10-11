from django.contrib import admin

from .models import ActivityLog, ApiUsage, BrandSettings, PromptVersion


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["criado_em", "user", "acao", "entidade", "entidade_id"]
    list_filter = ["acao", "entidade"]
    readonly_fields = [f.name for f in ActivityLog._meta.fields]


@admin.register(ApiUsage)
class ApiUsageAdmin(admin.ModelAdmin):
    list_display = ["data", "provedor", "endpoint", "custo_estimado"]
    list_filter = ["provedor"]


admin.site.register(PromptVersion)
admin.site.register(BrandSettings)
