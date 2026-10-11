from django.contrib import admin

from .models import Category, CategoryChecklistItem, CategoryWeight, Rule


class WeightInline(admin.TabularInline):
    model = CategoryWeight
    extra = 0


class ChecklistInline(admin.TabularInline):
    model = CategoryChecklistItem
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["nome", "ativo"]
    inlines = [WeightInline, ChecklistInline]
    prepopulated_fields = {"slug": ["nome"]}


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ["codigo", "dimensao", "descricao", "severidade_padrao", "ativo"]
    list_filter = ["dimensao", "ativo"]
