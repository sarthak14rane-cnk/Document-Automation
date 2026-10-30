from django.contrib import admin

from .models import TemplateMaster


@admin.register(TemplateMaster)
class TemplateMasterAdmin(admin.ModelAdmin):
    list_display = (
        "template_id",
        "template_name",
        "config_path",
        "template_path",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("template_name", "config_path", "template_path")
    readonly_fields = ("created_at", "updated_at")
