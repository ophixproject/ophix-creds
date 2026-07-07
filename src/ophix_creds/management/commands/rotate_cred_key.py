"""
ophix-manage rotate_cred_key
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Re-encrypts all Credential.secret_json values with a new Fernet key.

Usage::

    ophix-manage rotate_cred_key              # generate a new key automatically
    ophix-manage rotate_cred_key --new-key <key>  # supply your own key

Safety guarantees:

- All re-encryption happens inside a single database transaction.  If anything
  fails, the database rolls back and the existing key remains valid.
- The new key is printed to stdout BEFORE the .env file is updated.  If the
  .env write fails for any reason, the operator can set CRED_ENCRYPTION_KEY
  manually — no credentials are lost.
- The .env file is updated only after the transaction has committed.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from dotenv import find_dotenv, set_key


class Command(BaseCommand):
    help = "Re-encrypt all credentials with a new Fernet key"

    def add_arguments(self, parser):
        parser.add_argument(
            "--new-key",
            metavar="KEY",
            help=(
                "New Fernet key to encrypt with. "
                "If omitted, a new key is generated automatically."
            ),
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Skip the confirmation prompt (for scripted use).",
        )

    def handle(self, *args, **options):
        try:
            self._handle(*args, **options)
        except KeyboardInterrupt:
            self.stdout.write("")
            self.stdout.write("Cancelled.")
            raise SystemExit(1)

    def _handle(self, *args, **options):
        from cryptography.fernet import Fernet, InvalidToken

        # --- Validate old key ---
        old_key_str = os.getenv("CRED_ENCRYPTION_KEY", "")
        if not old_key_str:
            raise CommandError(
                "CRED_ENCRYPTION_KEY is not set in .env. "
                "Nothing to rotate."
            )
        try:
            old_fernet = Fernet(old_key_str.encode())
        except Exception:
            raise CommandError(
                "CRED_ENCRYPTION_KEY is not a valid Fernet key. "
                "Cannot rotate."
            )

        # --- Prepare new key ---
        new_key_str = options.get("new_key") or Fernet.generate_key().decode()
        try:
            new_fernet = Fernet(new_key_str.encode())
        except Exception:
            raise CommandError("--new-key is not a valid Fernet key.")

        if new_key_str == old_key_str:
            raise CommandError("New key is identical to the current key. Nothing to do.")

        # --- Count records ---
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM ophix_creds_credential "
                "WHERE secret_json IS NOT NULL AND secret_json <> ''"
            )
            count = cursor.fetchone()[0]

        self.stdout.write(f"\nCredentials to re-encrypt: {count}")

        # --- Confirm ---
        if not options["no_input"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis will re-encrypt all credentials in a single transaction.\n"
                    "The .env file will be updated with the new key after the DB commits.\n"
                )
            )
            confirm = input("Proceed? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                self.stdout.write("Aborted — no changes made.\n")
                return

        # --- Re-encrypt in a single transaction ---
        self.stdout.write("\nRe-encrypting... ")
        self.stdout.flush()

        from django.db import transaction
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, secret_json FROM ophix_creds_credential "
                        "WHERE secret_json IS NOT NULL AND secret_json <> ''"
                    )
                    rows = cursor.fetchall()
                    for row_id, value in rows:
                        if not value:
                            continue
                        try:
                            # decrypt returns bytes; pass directly to encrypt
                            plaintext_bytes = old_fernet.decrypt(value.encode())
                        except InvalidToken:
                            raise CommandError(
                                f"\nCredential id={row_id} could not be decrypted with the "
                                "current key. Database has been rolled back — no changes made.\n"
                                "Ensure CRED_ENCRYPTION_KEY matches the key used to encrypt "
                                "this record."
                            )
                        re_encrypted = new_fernet.encrypt(plaintext_bytes).decode()
                        cursor.execute(
                            "UPDATE ophix_creds_credential SET secret_json = %s WHERE id = %s",
                            [re_encrypted, row_id],
                        )
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(
                f"\nRe-encryption failed: {exc}\n"
                "Database has been rolled back — no changes made."
            )

        self.stdout.write(self.style.SUCCESS("OK\n"))

        # --- Print new key BEFORE updating .env ---
        self.stdout.write(self.style.SUCCESS(f"\nNew key: {new_key_str}\n"))
        self.stdout.write(
            self.style.WARNING(
                "Record this key now. If the .env update below fails,\n"
                "set CRED_ENCRYPTION_KEY manually before restarting the server.\n"
            )
        )

        # --- Update .env ---
        env_file = find_dotenv(usecwd=True)
        if env_file:
            set_key(env_file, "CRED_ENCRYPTION_KEY", new_key_str, quote_mode="always")
            self.stdout.write(self.style.SUCCESS(f"Updated {env_file}\n"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "No .env file found — could not update automatically.\n"
                    f"Set manually: CRED_ENCRYPTION_KEY={new_key_str}\n"
                )
            )

        self.stdout.write(
            "Restart the server for the new key to take effect.\n"
        )
