"""
ophix_creds.management.commands.import_legacy_credserver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
One-time migration utility: import data from a pre-refactor cred-server
database (app label 'creds', app name 'credserver') into the current
ophix-creds schema.

Old schema                    New schema
──────────────────────────    ──────────────────────────────────────────
creds_host               →    ophix_core_host
creds_client             →    ophix_core_client
creds_credential         →    ophix_creds_credential
                                  secret_json: plaintext JSON → Fernet-encrypted
creds_clientcredential   →    ophix_creds_clientcredential
                                  new columns: can_update, can_delete, can_share
                                  all default False (no permissions escalated)

Prerequisites
─────────────
  1. Run configure_install / run_install on the new server first.
     The new database must be fully migrated before running this command.
  2. CRED_ENCRYPTION_KEY must be set in .env.
     All credential values are imported from the old database in plaintext
     and encrypted with this key during import.

The old server is not modified and can remain running until the new one
is verified. This command is safe to re-run — existing records in the new
database are skipped with a warning (not overwritten).

Usage::

    ophix-manage import_legacy_credserver \\
        --db-host localhost \\
        --db-name old_credserver_db \\
        --db-user ophixuser \\
        --db-password secret

    # Test without writing:
    ophix-manage import_legacy_credserver --db-name ... --dry-run

    # PostgreSQL source database:
    ophix-manage import_legacy_credserver --db-engine postgres --db-name ...
"""

import getpass
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Import data from a legacy cred-server database into the current "
        "ophix-creds schema. Safe to re-run — existing records are skipped."
    )

    def add_arguments(self, parser):
        db = parser.add_argument_group("source database")
        db.add_argument("--db-host",     default="localhost", metavar="HOST")
        db.add_argument("--db-port",     default="",          metavar="PORT",
                        help="Default: 3306 for MariaDB/MySQL, 5432 for PostgreSQL")
        db.add_argument("--db-engine",   default="mariadb",   metavar="ENGINE",
                        choices=["mariadb", "mysql", "postgres"],
                        help="mariadb (default) | mysql | postgres")
        db.add_argument("--db-name",     required=True,       metavar="NAME")
        db.add_argument("--db-user",     default="",          metavar="USER")
        db.add_argument("--db-password", default=None,        metavar="PASSWORD",
                        help="Prompted interactively if omitted")

        parser.add_argument(
            "--dry-run", action="store_true",
            help="Check and report what would be imported without writing anything",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry-run mode — no changes will be written.\n"))
        else:
            self.stdout.write("\nImporting legacy credserver data\n")
        self.stdout.write("=" * 60 + "\n\n")

        # ------------------------------------------------------------------ #
        # Pre-flight checks
        # ------------------------------------------------------------------ #

        # 1. CRED_ENCRYPTION_KEY must be set
        from cryptography.fernet import Fernet
        raw_key = os.getenv("CRED_ENCRYPTION_KEY", "")
        if not raw_key:
            raise CommandError(
                "CRED_ENCRYPTION_KEY is not set in .env.\n"
                "Generate one first: ophix-manage generate_cred_key\n"
                "Then re-run configure_install (or set it manually in .env) "
                "before running this command."
            )
        try:
            fernet = Fernet(raw_key.encode())
        except Exception as exc:
            raise CommandError(f"CRED_ENCRYPTION_KEY is not a valid Fernet key: {exc}")

        self.stdout.write(self.style.SUCCESS("  CRED_ENCRYPTION_KEY: OK\n"))

        # 2. New database must be fully migrated
        self._check_new_db_migrated()
        self.stdout.write(self.style.SUCCESS("  New database migrations: OK\n\n"))

        # ------------------------------------------------------------------ #
        # Connect to old database
        # ------------------------------------------------------------------ #

        engine = options["db_engine"]
        host   = options["db_host"]
        port   = options["db_port"] or ("5432" if engine == "postgres" else "3306")
        name   = options["db_name"]
        user   = options["db_user"]
        password = options["db_password"]
        if password is None:
            password = getpass.getpass(f"  Password for {user}@{host}/{name}: ")

        self.stdout.write(f"Connecting to source database {user}@{host}:{port}/{name}\n")
        conn = self._connect(engine, host, port, name, user, password)
        self.stdout.write(self.style.SUCCESS("  Connected.\n\n"))

        # ------------------------------------------------------------------ #
        # Read source tables
        # ------------------------------------------------------------------ #

        hosts          = self._fetch_all(conn, "SELECT id, name, ipv4_address, description, enabled FROM creds_host")
        clients        = self._fetch_all(conn, "SELECT id, host_id, name, deployment_ref, venv_name, venv_path, enabled, api_token, last_token_rotation FROM creds_client")
        credentials    = self._fetch_all(conn, "SELECT id, name, description, secret_json, enabled, updated_at FROM creds_credential")
        links          = self._fetch_all(conn, "SELECT id, client_id, credential_id, enabled, notes FROM creds_clientcredential")
        conn.close()

        self.stdout.write(
            f"Source data:\n"
            f"  Hosts:          {len(hosts)}\n"
            f"  Clients:        {len(clients)}\n"
            f"  Credentials:    {len(credentials)}\n"
            f"  Client links:   {len(links)}\n\n"
        )

        if dry_run:
            self._dry_run_report(hosts, clients, credentials, links)
            return

        # ------------------------------------------------------------------ #
        # Import
        # ------------------------------------------------------------------ #

        from django.contrib.auth import get_user_model
        from ophix.core.models import Host, Client
        from ophix_creds.models import ClientCredential, Credential

        counters = {"hosts": 0, "clients": 0, "credentials": 0, "links": 0}
        skipped  = {"hosts": 0, "clients": 0, "credentials": 0, "links": 0}

        with transaction.atomic():

            # --- Hosts ---
            self.stdout.write("Importing hosts\n")
            for row in hosts:
                pk, hname, ip, desc, enabled = row
                if Host.objects.filter(ipv4_address=ip).exists():
                    self.stdout.write(
                        self.style.WARNING(f"  Skip (exists): host '{hname}' ({ip})\n")
                    )
                    skipped["hosts"] += 1
                    continue
                Host.objects.create(
                    id=pk, name=hname, ipv4_address=ip,
                    description=desc, enabled=bool(enabled),
                )
                self.stdout.write(self.style.SUCCESS(f"  Imported: {hname} ({ip})\n"))
                counters["hosts"] += 1

            # --- Clients ---
            self.stdout.write("\nImporting clients\n")
            for row in clients:
                pk, host_id, cname, dep_ref, venv_name, venv_path, enabled, token, last_rot = row
                if Client.objects.filter(api_token=token).exists():
                    self.stdout.write(
                        self.style.WARNING(f"  Skip (exists): client '{cname}' (token already present)\n")
                    )
                    skipped["clients"] += 1
                    continue
                Client.objects.create(
                    id=pk,
                    host_id=host_id,
                    name=cname,
                    deployment_ref=dep_ref,
                    venv_name=venv_name,
                    venv_path=venv_path,
                    enabled=bool(enabled),
                    api_token=token,
                    last_token_rotation=last_rot,
                )
                self.stdout.write(self.style.SUCCESS(f"  Imported: {cname}\n"))
                counters["clients"] += 1

            # --- Credentials ---
            self.stdout.write("\nImporting credentials\n")
            for row in credentials:
                pk, cred_name, desc, secret_json_raw, enabled, updated_at = row

                if Credential.objects.filter(name=cred_name).exists():
                    self.stdout.write(
                        self.style.WARNING(f"  Skip (exists): credential '{cred_name}'\n")
                    )
                    skipped["credentials"] += 1
                    continue

                # secret_json_raw is a dict (JSONField) or a string — normalise to
                # a JSON string, then encrypt it for the new EncryptedJSONField.
                if isinstance(secret_json_raw, dict):
                    plaintext = json.dumps(secret_json_raw)
                elif isinstance(secret_json_raw, str):
                    # Validate it's actually JSON
                    try:
                        json.loads(secret_json_raw)
                        plaintext = secret_json_raw
                    except (ValueError, TypeError):
                        plaintext = json.dumps({})
                        self.stdout.write(
                            self.style.WARNING(
                                f"  Warning: credential '{cred_name}' had invalid JSON "
                                f"— imported as empty object.\n"
                            )
                        )
                else:
                    plaintext = json.dumps({})

                encrypted = fernet.encrypt(plaintext.encode()).decode()

                # Use raw SQL to bypass the ORM's EncryptedJSONField decrypt-on-read,
                # inserting the already-encrypted token directly.
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO ophix_creds_credential
                            (id, name, description, secret_json, enabled, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        [pk, cred_name, desc, encrypted, bool(enabled), updated_at],
                    )

                self.stdout.write(self.style.SUCCESS(f"  Imported: {cred_name}\n"))
                counters["credentials"] += 1

            # --- ClientCredential links ---
            self.stdout.write("\nImporting client-credential links\n")
            for row in links:
                pk, client_id, cred_id, enabled, notes = row
                if ClientCredential.objects.filter(client_id=client_id, credential_id=cred_id).exists():
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Skip (exists): link client={client_id} → credential={cred_id}\n"
                        )
                    )
                    skipped["links"] += 1
                    continue
                ClientCredential.objects.create(
                    id=pk,
                    client_id=client_id,
                    credential_id=cred_id,
                    enabled=bool(enabled),
                    can_update=False,
                    can_delete=False,
                    can_share=False,
                    notes=notes,
                )
                counters["links"] += 1

        # ------------------------------------------------------------------ #
        # Summary
        # ------------------------------------------------------------------ #
        self.stdout.write("\n")
        self.stdout.write(self.style.SUCCESS("=" * 60 + "\n"))
        self.stdout.write(self.style.SUCCESS("Import complete.\n\n"))
        self.stdout.write(
            f"  Imported:  {counters['hosts']} hosts, {counters['clients']} clients, "
            f"{counters['credentials']} credentials, {counters['links']} links\n"
        )
        if any(skipped.values()):
            self.stdout.write(
                self.style.WARNING(
                    f"  Skipped:   {skipped['hosts']} hosts, {skipped['clients']} clients, "
                    f"{skipped['credentials']} credentials, {skipped['links']} links "
                    f"(already present)\n"
                )
            )
        self.stdout.write(
            "\nAll credential values are encrypted with the current CRED_ENCRYPTION_KEY.\n"
            "Existing fleet clients can reconnect using their current tokens — "
            "no re-registration required.\n"
        )

    # ---------------------------------------------------------------------- #
    # Helpers
    # ---------------------------------------------------------------------- #

    def _check_new_db_migrated(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM django_migrations "
                "WHERE app = 'ophix_creds' AND name = '0002_encrypt_secret_json'"
            )
            count = cursor.fetchone()[0]
        if not count:
            raise CommandError(
                "The new database does not have ophix_creds migration 0002 applied.\n"
                "Run: ophix-manage migrate"
            )

    def _connect(self, engine, host, port, name, user, password):
        if engine == "postgres":
            try:
                import psycopg2
            except ImportError:
                raise CommandError(
                    "psycopg2 is not installed. "
                    "Run: pip install ophix-dbengine-postgres"
                )
            try:
                return psycopg2.connect(
                    host=host, port=int(port), dbname=name,
                    user=user, password=password, connect_timeout=5,
                )
            except Exception as exc:
                raise CommandError(f"Could not connect to source database: {exc}")
        else:
            try:
                import MySQLdb
            except ImportError:
                raise CommandError(
                    "mysqlclient is not installed. "
                    "Ensure ophix-server-base is installed correctly."
                )
            try:
                return MySQLdb.connect(
                    host=host, port=int(port), db=name,
                    user=user, passwd=password, connect_timeout=5,
                )
            except Exception as exc:
                raise CommandError(f"Could not connect to source database: {exc}")

    def _fetch_all(self, conn, sql):
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        return rows

    def _dry_run_report(self, hosts, clients, credentials, links):
        from ophix.core.models import Host, Client
        from ophix_creds.models import ClientCredential, Credential

        def _check(label, items, model, check_fn):
            new = sum(1 for r in items if not check_fn(r))
            exist = len(items) - new
            self.stdout.write(f"  {label:<25} {new:>4} to import,  {exist:>4} already exist\n")

        self.stdout.write("Dry-run summary\n")
        self.stdout.write("-" * 50 + "\n")
        _check("Hosts", hosts,
               Host, lambda r: Host.objects.filter(ipv4_address=r[2]).exists())
        _check("Clients", clients,
               Client, lambda r: Client.objects.filter(api_token=r[7]).exists())
        _check("Credentials", credentials,
               Credential, lambda r: Credential.objects.filter(name=r[1]).exists())
        _check("Client-credential links", links,
               ClientCredential,
               lambda r: ClientCredential.objects.filter(client_id=r[1], credential_id=r[2]).exists())
        self.stdout.write("\nRun without --dry-run to perform the import.\n")
