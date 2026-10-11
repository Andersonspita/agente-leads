from django.contrib import admin

from .models import Briefing, Report, ReportView


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "audit", "criado_em", "enviado_em", "expira_em", "revogado"]


admin.site.register(ReportView)
admin.site.register(Briefing)
