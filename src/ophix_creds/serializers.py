"""
ophix_creds.serializers
~~~~~~~~~~~~~~~~~~~~~~~
"""

from rest_framework import serializers
from .models import Credential


class CredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Credential
        fields = ["name", "description", "secret_json", "updated_at"]
        read_only_fields = ["name", "updated_at"]
