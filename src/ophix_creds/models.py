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
from ophix.core.models import ClientArtifactBase


class Credential(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    secret_json = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ClientCredential(ClientArtifactBase):
    credential = models.ForeignKey(
        Credential,
        on_delete=models.CASCADE,
        related_name="client_links",
    )

    class Meta:
        unique_together = ("client", "credential")

    def __str__(self) -> str:
        return f"{self.client} → {self.credential}"
