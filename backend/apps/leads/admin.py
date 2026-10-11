from django.contrib import admin

from .models import CnpjEstablishment, Company, LeadNote, Search, SearchResult, Website


class WebsiteInline(admin.TabularInline):
    model = Website
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["nome", "municipality", "category", "status_lead", "telefone"]
    list_filter = ["status_lead", "category"]
    search_fields = ["nome", "cnpj", "telefone"]
    inlines = [WebsiteInline]


@admin.register(Search)
class SearchAdmin(admin.ModelAdmin):
    list_display = ["id", "category", "municipality", "termo_livre", "status", "total_encontrado", "criado_em"]


admin.site.register(SearchResult)
admin.site.register(LeadNote)
admin.site.register(CnpjEstablishment)
