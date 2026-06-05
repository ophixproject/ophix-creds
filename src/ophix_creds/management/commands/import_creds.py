"""
ophix-manage import_creds
~~~~~~~~~~~~~~~~~~~~~~~~~
Import Credential records from a JSON file produced by export_creds.

Idempotent: credentials are matched by name. Existing credentials are updated
only when a field value differs; identical records are skipped. The secret_json
is always written on update — this is intentional for migration/recovery.

If the file includes client_links and --include-client-links is passed, the
ClientCredential join records are also imported. Referenced clients and hosts
must already exist — run import_hosts and import_clients first.

If the file was exported with --passphrase, provide the same passphrase here.
The passphrase is validated before any database changes are made.

Examples
--------
Import from encrypted file:
    ophix-manage import_creds --input-file creds.json --passphrase "secret"

Import with client links:
    ophix-manage import_creds --input-file creds.json --passphrase "secret" --include-client-links

Preview without writing:
    ophix-manage import_creds --input-file creds.json --passphrase "secret" --dry-run
"""

import base64
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


class Command(BaseCommand):
    help = "Import Credential records from a JSON file produced by export_creds."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-file",
            required=True,
            metavar="FILE",
            help="Source file path (JSON produced by export_creds).",
        )
        parser.add_argument(
            "--passphrase",
            nargs="?",
            const="",
            metavar="PASSPHRASE",
            default=None,
            help="Passphrase to decrypt secrets (required if file was exported with --passphrase). Omit the value to be prompted securely (input is hidden).",
        )
        parser.add_argument(
            "--include-client-links",
            action="store_true",
            help="Also import ClientCredential join records from the file (if present).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created or updated without making any changes.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress per-record output. Summary line is always shown.",
        )

    def handle(self, *args, **options):
        from ophix_creds.models import Credential, ClientCredential

        input_path    = Path(options["input_file"])
        passphrase    = options["passphrase"]
        if passphrase == "":
            import getpass
            passphrase = getpass.getpass("Passphrase: ")
            if not passphrase:
                raise CommandError("Passphrase cannot be empty.")
        import_links  = options["include_client_links"]
        dry_run       = options["dry_run"]
        quiet         = options["quiet"]

        if not input_path.exists():
            raise CommandError(f"Input file not found: {input_path}")

        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {input_path}: {exc}")

        if not isinstance(payload, dict) or "credentials" not in payload:
            raise CommandError("Unrecognised file format — expected export_creds output.")

        encrypted = payload.get("encrypted", False)

        # Validate passphrase and build Fernet instance before touching the DB.
        fernet = None
        if encrypted:
            if not passphrase:
                raise CommandError(
                    "This file contains encrypted secrets. Provide --passphrase to import."
                )
            try:
                from cryptography.fernet import Fernet, InvalidToken
                salt = base64.urlsafe_b64decode(payload["salt"])
                fernet = Fernet(_derive_key(passphrase, salt))
                # Validate key against the first secret we can find.
                for rec in payload["credentials"]:
                    if rec.get("secret_json"):
                        fernet.decrypt(rec["secret_json"].encode())
                        break
            except InvalidToken:
                raise CommandError("Incorrect passphrase — could not decrypt secrets.")
            except Exception as exc:
                raise CommandError(f"Failed to initialise decryption: {exc}")
        elif passphrase and not quiet:
            self.stderr.write(self.style.WARNING(
                "Warning: file is not encrypted but --passphrase was provided — ignoring."
            ))

        records = payload["credentials"]
        if not isinstance(records, list):
            raise CommandError("Expected 'credentials' to be a JSON array.")

        created = updated = unchanged = skipped = 0
        links_created = links_updated = links_unchanged = links_skipped = 0

        for i, rec in enumerate(records, 1):
            name = (rec.get("name") or "").strip()
            if not name:
                self.stderr.write(f"  Record {i}: missing 'name' — skipped.")
                skipped += 1
                continue

            # Decrypt and parse secret_json.
            raw_secret = rec.get("secret_json", "")
            if fernet and raw_secret:
                try:
                    from cryptography.fernet import InvalidToken
                    raw_secret = fernet.decrypt(raw_secret.encode()).decode()
                except InvalidToken:
                    self.stderr.write(f"  {name}: secret decryption failed — skipped.")
                    skipped += 1
                    continue
            try:
                secret_value = json.loads(raw_secret) if raw_secret else {}
            except (ValueError, TypeError) as exc:
                self.stderr.write(f"  {name}: invalid secret JSON — {exc} — skipped.")
                skipped += 1
                continue

            fields = {
                "description": rec.get("description") or None,
                "secret_json": secret_value,
                "enabled":     bool(rec.get("enabled", True)),
            }

            # Create or update credential.
            cred_obj = None
            try:
                cred_obj = Credential.objects.get(name=name)
                # Compare fields. secret_json comparison uses JSON round-trip.
                existing_secret = json.dumps(cred_obj.secret_json, sort_keys=True)
                new_secret = json.dumps(secret_value, sort_keys=True)
                changed = {}
                if cred_obj.description != fields["description"]:
                    changed["description"] = fields["description"]
                if existing_secret != new_secret:
                    changed["secret_json"] = secret_value
                if cred_obj.enabled != fields["enabled"]:
                    changed["enabled"] = fields["enabled"]

                if not changed:
                    unchanged += 1
                    if not quiet:
                        self.stdout.write(f"  {name}: unchanged.")
                else:
                    changed_names = list(changed.keys())
                    has_secret = "secret_json" in changed_names
                    visible = [f for f in changed_names if f != "secret_json"]
                    label = ", ".join(visible)
                    if has_secret:
                        label = (label + ", secret" if label else "secret")
                    if not quiet:
                        self.stdout.write(f"  {name}: updating {label}.")
                    if not dry_run:
                        try:
                            for f, v in changed.items():
                                setattr(cred_obj, f, v)
                            cred_obj.full_clean()
                            cred_obj.save()
                        except Exception as exc:
                            self.stderr.write(f"  {name}: save failed — {exc}")
                            skipped += 1
                            continue
                    updated += 1

            except Credential.DoesNotExist:
                if not quiet:
                    self.stdout.write(f"  {name}: creating.")
                if not dry_run:
                    try:
                        cred_obj = Credential(name=name, **fields)
                        cred_obj.full_clean()
                        cred_obj.save()
                    except Exception as exc:
                        self.stderr.write(f"  {name}: save failed — {exc}")
                        skipped += 1
                        continue
                created += 1

            # Import client links if requested.
            if import_links and rec.get("client_links"):
                if dry_run or cred_obj is None:
                    # In dry run mode, cred_obj may not exist yet.
                    # Count links as they would be processed.
                    links_created += len(rec["client_links"])
                    continue

                from ophix.core.models import Client, Host
                for link_rec in rec["client_links"]:
                    client_name = (link_rec.get("client") or "").strip()
                    host_name   = (link_rec.get("host") or "").strip()

                    if not client_name or not host_name:
                        self.stderr.write(
                            f"  {name} → link: missing client or host — skipped."
                        )
                        links_skipped += 1
                        continue

                    try:
                        host   = Host.objects.get(name=host_name)
                        client = Client.objects.get(name=client_name, host=host)
                    except Host.DoesNotExist:
                        self.stderr.write(
                            f"  {name} → {host_name}/{client_name}: "
                            f"host '{host_name}' not found — skipped."
                        )
                        links_skipped += 1
                        continue
                    except Client.DoesNotExist:
                        self.stderr.write(
                            f"  {name} → {host_name}/{client_name}: "
                            f"client not found — skipped."
                        )
                        links_skipped += 1
                        continue

                    link_fields = {
                        "enabled":    bool(link_rec.get("enabled", True)),
                        "can_update": bool(link_rec.get("can_update", False)),
                        "can_delete": bool(link_rec.get("can_delete", False)),
                        "can_share":  bool(link_rec.get("can_share", False)),
                        "notes":      link_rec.get("notes") or None,
                    }

                    try:
                        link = ClientCredential.objects.get(client=client, credential=cred_obj)
                        link_changed = {
                            f: v for f, v in link_fields.items()
                            if getattr(link, f) != v
                        }
                        if not link_changed:
                            links_unchanged += 1
                        else:
                            if not quiet:
                                self.stdout.write(
                                    f"  {name} → {host_name}/{client_name}: "
                                    f"updating {', '.join(link_changed)}."
                                )
                            try:
                                for f, v in link_changed.items():
                                    setattr(link, f, v)
                                link.save()
                            except Exception as exc:
                                self.stderr.write(
                                    f"  {name} → {host_name}/{client_name}: "
                                    f"save failed — {exc}"
                                )
                                links_skipped += 1
                                continue
                            links_updated += 1

                    except ClientCredential.DoesNotExist:
                        if not quiet:
                            self.stdout.write(
                                f"  {name} → {host_name}/{client_name}: creating link."
                            )
                        try:
                            ClientCredential.objects.create(
                                client=client, credential=cred_obj, **link_fields
                            )
                        except Exception as exc:
                            self.stderr.write(
                                f"  {name} → {host_name}/{client_name}: "
                                f"save failed — {exc}"
                            )
                            links_skipped += 1
                            continue
                        links_created += 1

        # Build summary.
        parts = []
        if created:
            parts.append(f"{created} created")
        if updated:
            parts.append(f"{updated} updated")
        if unchanged:
            parts.append(f"{unchanged} unchanged")
        if skipped:
            parts.append(f"{skipped} skipped")
        summary = ", ".join(parts) if parts else "nothing to do"

        if import_links:
            link_parts = []
            if links_created:
                link_parts.append(f"{links_created} created")
            if links_updated:
                link_parts.append(f"{links_updated} updated")
            if links_unchanged:
                link_parts.append(f"{links_unchanged} unchanged")
            if links_skipped:
                link_parts.append(f"{links_skipped} skipped")
            link_summary = ", ".join(link_parts) if link_parts else "none"
            summary += f" | links: {link_summary}"

        if dry_run:
            self.stdout.write(f"Dry run: {summary}.")
        else:
            self.stdout.write(self.style.SUCCESS(f"{summary.capitalize()}."))
