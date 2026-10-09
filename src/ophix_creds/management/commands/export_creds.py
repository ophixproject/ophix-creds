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

Use --stable together with --passphrase/--passphrase-env to produce
deterministic output (unchanged secrets always encrypt to the same
ciphertext on this server) — intended for ophix-revisions' git-backed
history, where an unchanged credential should produce an empty diff.

Examples
--------
Export with encrypted secrets (recommended):
    ophix-manage export_creds --output-file creds.json --passphrase "secret"

Export with client links included:
    ophix-manage export_creds --output-file creds.json --passphrase "secret" --include-client-links

Deterministic export (for ophix-revisions):
    ophix-manage export_creds --output-file creds.json --passphrase-env BACKUP_PASSPHRASE --stable

Preview without writing:
    ophix-manage export_creds --output-file creds.json --passphrase "secret" --dry-run
"""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ophix.core import crypto


def _build_meta(domain: str, command: str) -> dict:
    import datetime
    import os
    import socket
    from django.conf import settings
    try:
        import pwd
        run_by = pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        run_by = os.environ.get("USER") or os.environ.get("LOGNAME")
    ssh_raw = os.environ.get("SSH_CLIENT", "")
    return {
        "created_at":     datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "server_name":    getattr(settings, "SERVER_NAME", None),
        "server_version": getattr(settings, "SERVER_VERSION", None),
        "hostname":       socket.gethostname(),
        "domain":         domain,
        "command":        command,
        "run_by":         run_by,
        "login_user":     os.environ.get("SUDO_USER") or None,
        "ssh_origin":     ssh_raw.split()[0] if ssh_raw else None,
    }


def _serialize(credential, cipher=None, include_links=False):
    secret_str = json.dumps(credential.secret_json)
    secret_value = cipher.encrypt(secret_str) if cipher else secret_str

    record = {
        "name":        credential.name,
        "description": credential.description,
        "secret_json": secret_value,
        "enabled":     credential.enabled,
    }

    if include_links:
        links = []
        for link in credential.client_links.select_related("client__host").order_by(
            "client__host__name", "client__name"
        ):
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
        passphrase_group = parser.add_mutually_exclusive_group()
        passphrase_group.add_argument(
            "--passphrase",
            nargs="?",
            const="",
            metavar="PASSPHRASE",
            default=None,
            help="Encrypt secret values using a passphrase-derived Fernet key. Omit the value to be prompted securely (input is hidden).",
        )
        passphrase_group.add_argument(
            "--passphrase-env",
            metavar="ENVVAR",
            default=None,
            help="Read the passphrase from the named environment variable (for automated use).",
        )
        parser.add_argument(
            "--include-client-links",
            action="store_true",
            help="Also export ClientCredential join records (client access permissions).",
        )
        parser.add_argument(
            "--stable",
            action="store_true",
            help=(
                "Produce deterministic output — unchanged secrets always encrypt "
                "to the same ciphertext on this server. For use with ophix-revisions "
                "or any other git-backed history of this export."
            ),
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
        passphrase_env = options["passphrase_env"]
        if passphrase_env:
            passphrase = os.environ.get(passphrase_env)
            if not passphrase:
                raise CommandError(
                    f"Environment variable '{passphrase_env}' is not set or empty."
                )
        elif passphrase == "":
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
        stable         = options["stable"]
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

        cipher = crypto.build_export_cipher(passphrase, stable=stable)

        if not passphrase and not quiet:
            self.stderr.write(self.style.WARNING(
                "Warning: exporting credential secrets in plaintext. "
                "Use --passphrase to encrypt. Protect this file as a credential store."
            ))

        payload = {
            "version":              1,
            "encrypted":            cipher is not None,
            "cipher":               cipher.name if cipher else None,
            "salt":                 cipher.salt_b64 if cipher else None,
            "include_client_links": include_links,
            "credentials":          [
                _serialize(c, cipher, include_links) for c in credentials
            ],
        }
        if not stable:
            payload["meta"] = _build_meta("creds", "export_creds")

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=stable)

        if not quiet:
            enc_note = " (secrets encrypted)" if cipher else " (secrets plaintext)"
            link_note = ", with client links" if include_links else ""
            self.stdout.write(self.style.SUCCESS(
                f"Exported {count} credential(s) to {output_path}{enc_note}{link_note}."
            ))
