from django.apps import AppConfig


class OphixCredsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ophix_creds"
    verbose_name = "Credentials"
    is_ophix_domain = True

    def ready(self):
        from ophix.core.admin import ClientAdmin
        from .admin import ClientCredentialInlineForClient, linked_credentials
        ClientAdmin.register_inline(ClientCredentialInlineForClient)
        ClientAdmin.register_column(linked_credentials)
