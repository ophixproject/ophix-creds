"""
ophix_creds.fields
~~~~~~~~~~~~~~~~~~
EncryptedJSONField — a TextField that transparently encrypts and decrypts its
JSON content using Fernet symmetric encryption (from the cryptography package).

The encryption key is read lazily from the CRED_ENCRYPTION_KEY environment
variable each time the field is accessed.  The key must be a valid Fernet key,
generated with: ophix-manage generate_cred_key

From the caller's perspective (admin, serializer, ORM queries) the field
behaves exactly like JSONField: it accepts and returns Python dicts/lists/etc.
The encrypted Fernet token is what is actually stored in the database column.
"""

import json
import os

from django.db import models


def _get_fernet():
    """
    Return a Fernet instance using CRED_ENCRYPTION_KEY.

    Raises ImproperlyConfigured if the key is missing or invalid.
    Imported lazily so that importing this module never fails even if the
    cryptography package is not yet installed.
    """
    from django.core.exceptions import ImproperlyConfigured

    key = os.getenv("CRED_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured(
            "CRED_ENCRYPTION_KEY is not set in .env. "
            "Generate a key with: ophix-manage generate_cred_key\n"
            "Then add CRED_ENCRYPTION_KEY=<key> to your .env file."
        )
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception:
        raise ImproperlyConfigured(
            "CRED_ENCRYPTION_KEY is not a valid Fernet key. "
            "Generate a new one with: ophix-manage generate_cred_key"
        )


class EncryptedJSONField(models.TextField):
    """
    Stores JSON data encrypted at rest using Fernet symmetric encryption.

    Database column type is TEXT/LONGTEXT (not JSON) — the encrypted Fernet
    token is an opaque base64 string.  The Python-level value is always a
    dict (or whatever JSON-serialisable type was stored), identical in
    behaviour to Django's JSONField from application code.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return {}
        decrypted = _get_fernet().decrypt(value.encode()).decode()
        return json.loads(decrypted)

    def get_prep_value(self, value):
        if value is None:
            return None
        if not isinstance(value, str):
            value = json.dumps(value)
        return _get_fernet().encrypt(value.encode()).decode()

    def formfield(self, **kwargs):
        # Use Django's JSONFormField so the admin displays and validates JSON
        # text rather than the raw encrypted string.
        from django.forms import JSONField as JSONFormField
        kwargs.setdefault("form_class", JSONFormField)
        return super().formfield(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        path = "ophix_creds.fields.EncryptedJSONField"
        return name, path, args, kwargs
