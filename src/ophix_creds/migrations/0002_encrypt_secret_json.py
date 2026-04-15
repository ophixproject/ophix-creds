"""
Migration 0002 — encrypt secret_json at rest.

Step 1 (schema): Changes the secret_json column from JSON to TEXT/LONGTEXT.
                 The raw JSON text is preserved verbatim during the column
                 type change — no data is lost.

Step 2 (data):   Encrypts every existing plaintext JSON value using the Fernet
                 key in CRED_ENCRYPTION_KEY.  Uses raw SQL to bypass the ORM
                 field layer, which would otherwise try to decrypt values that
                 are not yet encrypted.

CRED_ENCRYPTION_KEY must be set in .env before running this migration.
Generate a key with: ophix-manage generate_cred_key
"""

import os

import ophix_creds.fields
from django.db import migrations


def _fernet_from_env():
    """Return a Fernet instance or raise with a clear message."""
    from django.core.exceptions import ImproperlyConfigured
    from cryptography.fernet import Fernet

    key = os.getenv("CRED_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured(
            "\n\nCRED_ENCRYPTION_KEY is not set.\n"
            "Generate a key first: ophix-manage generate_cred_key\n"
            "Then add CRED_ENCRYPTION_KEY=<key> to your .env and re-run migrate.\n"
        )
    return Fernet(key.encode())


def encrypt_existing_credentials(apps, schema_editor):
    """Encrypt any plaintext JSON values left over from before this migration."""
    fernet = _fernet_from_env()

    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, secret_json FROM ophix_creds_credential "
            "WHERE secret_json IS NOT NULL AND secret_json <> ''"
        )
        rows = cursor.fetchall()
        for row_id, value in rows:
            # Fernet tokens are URL-safe base64 and always start with 'gA'.
            # Plain JSON starts with '{', '[', '"', digits, etc.
            # Skip rows that are already encrypted (idempotent).
            if value and not value.startswith("gA"):
                encrypted = fernet.encrypt(value.encode()).decode()
                cursor.execute(
                    "UPDATE ophix_creds_credential SET secret_json = %s WHERE id = %s",
                    [encrypted, row_id],
                )


def decrypt_existing_credentials(apps, schema_editor):
    """Reverse: decrypt all values back to plaintext JSON."""
    fernet = _fernet_from_env()

    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, secret_json FROM ophix_creds_credential "
            "WHERE secret_json IS NOT NULL AND secret_json <> ''"
        )
        rows = cursor.fetchall()
        for row_id, value in rows:
            if value and value.startswith("gA"):
                decrypted = fernet.decrypt(value.encode()).decode()
                cursor.execute(
                    "UPDATE ophix_creds_credential SET secret_json = %s WHERE id = %s",
                    [decrypted, row_id],
                )


class Migration(migrations.Migration):

    dependencies = [
        ("ophix_creds", "0001_initial"),
    ]

    operations = [
        # Step 1: change column type from JSON to TEXT
        migrations.AlterField(
            model_name="credential",
            name="secret_json",
            field=ophix_creds.fields.EncryptedJSONField(default=dict),
        ),
        # Step 2: encrypt the now-plaintext values in the TEXT column
        migrations.RunPython(
            encrypt_existing_credentials,
            reverse_code=decrypt_existing_credentials,
        ),
    ]
