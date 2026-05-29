from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OphixCredsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ophix_creds"
    verbose_name = _("Credentials")
    admin_order = 200
    is_ophix_domain = True

    def ready(self):
        from ophix.core.admin import ClientAdmin
        from .admin import ClientCredentialInlineForClient, linked_credentials
        ClientAdmin.register_inline(ClientCredentialInlineForClient)
        ClientAdmin.register_column(linked_credentials)
