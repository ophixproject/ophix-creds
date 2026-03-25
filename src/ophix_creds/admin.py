"""
ophix_creds.admin
~~~~~~~~~~~~~~~~~
Admin registrations for Credential and ClientCredential.
"""

from django.contrib import admin
from django.conf import settings

from .models import Credential, ClientCredential


class ClientCredentialInline(admin.TabularInline):
    model = ClientCredential
    extra = 0
    fields = ("client", "enabled", "can_update", "can_delete", "can_share", "notes")
    readonly_fields = ()


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "enabled", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("updated_at",)
    inlines = [ClientCredentialInline]

    def get_inlines(self, request, obj=None):
        if not getattr(settings, "SHOW_CLIENT_ARTIFACT_MODEL", False):
            return []
        return self.inlines


@admin.register(ClientCredential)
class ClientCredentialAdmin(admin.ModelAdmin):
    list_display = (
        "client", "credential", "enabled",
        "can_update", "can_delete", "can_share",
    )
    list_filter = ("enabled", "can_update", "can_delete")
    search_fields = ("client__name", "credential__name")

    def get_model_perms(self, request):
        # Hide from admin index unless explicitly enabled.
        if not getattr(settings, "SHOW_CLIENT_ARTIFACT_MODEL", False):
            return {}
        return super().get_model_perms(request)
