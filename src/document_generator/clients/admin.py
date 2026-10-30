from django.contrib import admin

from clients.models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "client_name",
        "client_short_name",
        "client_spoc_name",
        "client_spoc_email",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("client_name", "client_short_name")
    readonly_fields = ("created_at", "updated_at")
