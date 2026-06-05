"""
ophix-manage export_creds
~~~~~~~~~~~~~~~~~~~~~~~~~
Export Credential records to a JSON file for backup or server migration.

Secret values are included in the export. Without --passphrase they are
written as plaintext JSON — protect the output file accordingly. With
--passphrase the secret values are encrypted using a PBKDF2-derived Fernet
key; the same passphrase is required by import_creds on the receiving server.

Use --include-client-links to also export the ClientCredential join table
(which clients have access to which credentials and with what permissions).
On import, referenced clients and hosts must already exist — run import_hosts
and import_clients first when doing a full server restore.

Examples
--------
Export with encrypted secrets (recommended):
    ophix-manage export_creds --output-file creds.json --passphrase "secret"

Export with client links included:
    ophix-manage export_creds --output-file creds.json --passphrase "secret" --include-client-links

Preview without writing:
    ophix-manage export_creds --output-file creds.json --passphrase "secret" --dry-run
"""

import base64
import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def _serialize(credential, fernet=None, include_links=False):
    secret_str = json.dumps(credential.secret_json)
    if fernet:
        secret_value = fernet.encrypt(secret_str.encode()).decode()
    else:
        secret_value = secret_str

    record = {
        "name":        credential.name,
        "description": credential.description,
        "secret_json": secret_value,
        "enabled":     credential.enabled,
    }

    if include_links:
        links = []
        for link in credential.client_links.select_related("client__host").all():
            links.append({
                "client":     link.client.name,
                "host":       link.client.host.name,
                "enabled":    link.enabled,
                "can_update": link.can_update,
                "can_delete": link.can_delete,
                "can_share":  link.can_share,
                "notes":      link.notes,
            })
        record["client_links"] = links

    return record


class Command(BaseCommand):
    help = "Export Credential records to a JSON file for backup or server migration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-file",
            required=True,
            metavar="FILE",
            help="Destination file path.",
        )
        parser.add_argument(
            "--passphrase",
            nargs="?",
            const="",
            metavar="PASSPHRASE",
            default=None,
            help="Encrypt secret values using a passphrase-derived Fernet key. Omit the value to be prompted securely (input is hidden).",
        )
        parser.add_argument(
            "--include-client-links",
            action="store_true",
            help="Also export ClientCredential join records (client access permissions).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many credentials would be exported without writing anything.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress all output.",
        )

    def handle(self, *args, **options):
        from ophix_creds.models import Credential

        output_path    = Path(options["output_file"])
        passphrase     = options["passphrase"]
        if passphrase == "":
            import getpass
            while True:
                passphrase = getpass.getpass("Passphrase: ")
                if not passphrase:
                    raise CommandError("Passphrase cannot be empty.")
                confirm = getpass.getpass("Confirm passphrase: ")
                if passphrase == confirm:
                    break
                self.stderr.write("Passphrases do not match — try again.")
        include_links  = options["include_client_links"]
        dry_run        = options["dry_run"]
        quiet          = options["quiet"]

        credentials = list(Credential.objects.order_by("name"))
        count = len(credentials)

        if dry_run:
            self.stdout.write(
                f"Dry run: {count} credential(s) would be exported to {output_path}."
            )
            return

        if count == 0:
            if not quiet:
                self.stdout.write("No credentials found — nothing to export.")
            return

        if not output_path.parent.exists():
            raise CommandError(f"Output directory does not exist: {output_path.parent}")

        fernet = None
        salt_b64 = None
        if passphrase:
            from cryptography.fernet import Fernet
            salt = os.urandom(16)
            salt_b64 = base64.urlsafe_b64encode(salt).decode()
            fernet = Fernet(_derive_key(passphrase, salt))

        if not passphrase and not quiet:
            self.stderr.write(self.style.WARNING(
                "Warning: exporting credential secrets in plaintext. "
                "Use --passphrase to encrypt. Protect this file as a credential store."
            ))

        payload = {
            "version":              1,
            "encrypted":            fernet is not None,
            "salt":                 salt_b64,
            "include_client_links": include_links,
            "credentials":          [
                _serialize(c, fernet, include_links) for c in credentials
            ],
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        if not quiet:
            enc_note = " (secrets encrypted)" if fernet else " (secrets plaintext)"
            link_note = ", with client links" if include_links else ""
            self.stdout.write(self.style.SUCCESS(
                f"Exported {count} credential(s) to {output_path}{enc_note}{link_note}."
            ))
