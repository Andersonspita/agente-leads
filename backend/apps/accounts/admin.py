from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "role", "is_active", "last_login"]
    fieldsets = BaseUserAdmin.fieldsets + (("Auditor", {"fields": ("role", "failed_logins", "locked_until")}),)
