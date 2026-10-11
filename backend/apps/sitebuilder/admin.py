from django.contrib import admin

from .models import SiteProject


@admin.register(SiteProject)
class SiteProjectAdmin(admin.ModelAdmin):
    list_display = ["company", "gerado_por_ia", "criado_em", "atualizado_em"]
