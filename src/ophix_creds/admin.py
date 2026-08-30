"""
ophix_creds.admin
~~~~~~~~~~~~~~~~~
Admin registrations for Credential and ClientCredential.
"""

from django.contrib import admin
from django.conf import settings
from django import forms
from django.db import models
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _

from ophix.core.admin import CleanSaveMessageMixin
from .models import Credential, ClientCredential


# ============================================================
# Client ↔ Credential inlines
# ============================================================

class ClientCredentialInlineForClient(admin.TabularInline):
    """
    Inline shown on Client admin: manage which credentials are attached to this client.
    Registered into ClientAdmin via AppConfig.ready().
    """
    model = ClientCredential
    extra = 0
    autocomplete_fields = ('credential',)
    fields = ('credential', 'enabled', 'notes')
    classes = ('collapse',)
    verbose_name = _("Credential")
    verbose_name_plural = _("Credentials")
    formfield_overrides = {
        models.TextField: {
            'widget': forms.Textarea(attrs={'rows': 2, 'cols': 120})
        }
    }


class ClientCredentialInlineForCredential(admin.TabularInline):
    """
    Inline shown on Credential admin: manage which clients use this credential.
    """
    model = ClientCredential
    extra = 0
    autocomplete_fields = ('client',)
    fields = ('client', 'enabled', 'notes')
    classes = ('collapse',)
    verbose_name = _("Client")
    verbose_name_plural = _("Clients")
    formfield_overrides = {
        models.TextField: {
            'widget': forms.Textarea(attrs={'rows': 2, 'cols': 120})
        }
    }


# ============================================================
# ClientAdmin column — contributed via register_column()
# ============================================================

def linked_credentials(self, obj):
    links = ClientCredential.objects.filter(client=obj).select_related('credential')
    if not links:
        return "—"

    items = []
    for cc in links:
        label = cc.credential.name
        if cc.enabled and cc.credential.enabled:
            items.append(f"• {label}")
        else:
            items.append(
                format_html(
                    "• <span style='color: var(--admin-interface-disabled-color); font-weight: 600;'>{}</span>",
                    label,
                )
            )

    return format_html(
        "<div style='display: flex; flex-wrap: wrap; gap: 0.5em; white-space: normal;'>{}</div>",
        mark_safe(" ".join(items)),
    )

linked_credentials.short_description = _("Authorised Credentials")


# ============================================================
# CredentialAdmin
# ============================================================

@admin.register(Credential)
class CredentialAdmin(CleanSaveMessageMixin, admin.ModelAdmin):
    list_display = (
        'name',           # identity
        'description',    # human context
        'enabled',        # state (consistent position)
        'linked_clients', # relationships (consistent position)
    )
    list_editable = ('enabled',)
    list_filter = ('enabled',)
    search_fields = ('name', 'description')
    ordering = ('name',)
    readonly_fields = ('updated_at',)
    inlines = [ClientCredentialInlineForCredential]
    actions = None

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'secret_json':
            try:
                from ophix_codemirror.widgets import JSONCodeMirrorWidget
                kwargs['widget'] = JSONCodeMirrorWidget()
            except ImportError:
                pass
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    formfield_overrides = {
        models.TextField: {
            'widget': forms.Textarea(attrs={'cols': 120, 'rows': 3})
        },
    }

    def linked_clients(self, obj):
        links = obj.client_links.select_related('client')
        if not links:
            return "—"

        items = []
        for cc in links:
            label = cc.client.name
            if cc.enabled and cc.client.enabled:
                items.append(f"• {label}")
            else:
                items.append(
                    format_html(
                        "• <span style='color: var(--admin-interface-disabled-color); font-weight: 600;'>{}</span>",
                        label,
                    )
                )

        return format_html(
            "<div style='display: flex; flex-wrap: wrap; gap: 0.5em; white-space: normal;'>{}</div>",
            mark_safe(" ".join(items)),
        )

    linked_clients.short_description = _("Authorised Clients")


# ============================================================
# ClientCredentialAdmin (audit / debug only)
# ============================================================

if getattr(settings, "SHOW_CLIENT_ARTIFACT_MODEL", False):

    @admin.register(ClientCredential)
    class ClientCredentialAdmin(CleanSaveMessageMixin, admin.ModelAdmin):
        """
        Exists primarily for auditing and debugging.
        Day-to-day management should be done via inlines.
        """
        list_display = (
            'client',
            'credential',
            'enabled',
            'short_notes',
        )
        list_editable = ('enabled',)
        list_filter = ('enabled', 'client__host', 'client', 'credential')
        search_fields = ('client__name', 'credential__name', 'notes')
        actions = None

        def short_notes(self, obj):
            return (obj.notes[:50] + '…') if obj.notes and len(obj.notes) > 50 else obj.notes
        short_notes.short_description = _('Notes')
