"""
ophix_creds.models
~~~~~~~~~~~~~~~~~~
Domain models for the Ophix Credentials server.

Credential
    A named secret stored as arbitrary JSON.

ClientCredential
    Join table linking a Client to a Credential with per-link
    permission flags inherited from ClientArtifactBase.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from ophix.core.models import ClientArtifactBase
from .fields import EncryptedJSONField


class Credential(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    description = models.TextField(_("description"), blank=True, null=True)
    secret_json = EncryptedJSONField(_("secret JSON"), default=dict)
    enabled = models.BooleanField(_("enabled"), default=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Credential")
        verbose_name_plural = _("Credentials")

    def __str__(self) -> str:
        return self.name


class ClientCredential(ClientArtifactBase):
    credential = models.ForeignKey(
        Credential,
        verbose_name=_("credential"),
        on_delete=models.CASCADE,
        related_name="client_links",
    )

    class Meta:
        unique_together = ("client", "credential")
        verbose_name = _("Client Credential")
        verbose_name_plural = _("Client Credentials")

    def __str__(self) -> str:
        return f"{self.client} → {self.credential}"
