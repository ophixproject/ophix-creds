"""
ophix-manage generate_cred_key
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generates a new Fernet encryption key for CRED_ENCRYPTION_KEY.

Run this once before deploying or upgrading to encrypted credentials:

    ophix-manage generate_cred_key

Copy the printed key into your .env file, then run:

    ophix-manage migrate

WARNING: The key is the only means of decrypting stored credentials.
Keep it safe.  Losing it means losing access to all credential data.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a new Fernet encryption key for CRED_ENCRYPTION_KEY"

    def handle(self, *args, **options):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()

        self.stdout.write("\nGenerated CRED_ENCRYPTION_KEY:\n")
        self.stdout.write(self.style.SUCCESS(f"  {key}\n"))
        self.stdout.write("\nAdd this line to your .env file:\n")
        self.stdout.write(f"  CRED_ENCRYPTION_KEY={key}\n")
        self.stdout.write(
            self.style.WARNING(
                "\nWARNING: Store this key securely and back it up.\n"
                "Losing it means losing access to all stored credentials.\n"
            )
        )
