from django.contrib import admin

from .models import Municipality


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ["codigo_ibge", "nome", "uf"]
    list_filter = ["uf"]
    search_fields = ["nome", "codigo_ibge"]
