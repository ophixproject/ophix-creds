plugin_category = "module"
plugin_sort = 100

default_app_config = "ophix_creds.apps.OphixCredsConfig"


def install_configure(conf, command):
    """
    configure_install hook: generate or collect CRED_ENCRYPTION_KEY, and
    contribute this domain's backup target.

    For a fresh install the key is auto-generated. For a venv rebuild on an
    existing database the operator must supply the original key, otherwise all
    stored credentials become unreadable.
    """
    existing_enc_targets = conf.get("backup", "targets_encrypted_extra", fallback="")
    conf.set("backup", "targets_encrypted_extra", ",".join(filter(None, [existing_enc_targets, "creds"])))

    if not conf.has_section("ophix_creds"):
        conf.add_section("ophix_creds")

    existing = conf.get("ophix_creds", "cred_encryption_key", fallback="")
    if existing:
        command.stdout.write("  CRED_ENCRYPTION_KEY: already configured\n")
        keep = input("  Keep existing key? [Y/n]: ").strip().lower()
        if keep not in ("n", "no"):
            return

    command.stdout.write(
        "  Options:\n"
        "  [G] Generate a new key  (default — use for fresh installs)\n"
        "  [S] Supply existing key (use when rebuilding venv on an existing database)\n"
        "\n"
        "  WARNING: If encrypted credentials already exist in the database,\n"
        "           you MUST supply the original key or they will be unreadable.\n\n"
    )
    choice = input("  Choice [G/s]: ").strip().lower()

    if choice in ("s", "supply"):
        import getpass
        key = getpass.getpass("  Paste existing CRED_ENCRYPTION_KEY: ").strip()
        if not key:
            command.stdout.write(command.style.ERROR("  No key entered — skipping.\n"))
            return
        try:
            from cryptography.fernet import Fernet
            Fernet(key.encode())
        except Exception:
            command.stdout.write(command.style.ERROR("  Not a valid Fernet key — skipping.\n"))
            return
        command.stdout.write(command.style.SUCCESS("  Existing key accepted.\n"))
    else:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        command.stdout.write(command.style.SUCCESS("  New CRED_ENCRYPTION_KEY generated.\n"))
        command.stdout.write(
            command.style.WARNING(
                "  Back up this key securely — losing it means losing all stored credentials.\n"
            )
        )

    conf.set("ophix_creds", "cred_encryption_key", key)


def install_run(conf, command):
    """
    run_install hook: write CRED_ENCRYPTION_KEY to .env before migrate.

    Migration 0002 encrypts existing plaintext secret_json values using this key,
    so it must be present in .env before migrate runs.
    """
    from pathlib import Path
    from dotenv import find_dotenv, set_key

    key = conf.get("ophix_creds", "cred_encryption_key", fallback="")
    if not key:
        command.stdout.write(
            command.style.WARNING(
                "  CRED_ENCRYPTION_KEY not configured — "
                "add it to .env manually before running migrate.\n"
            )
        )
        return

    env_file = find_dotenv(usecwd=True) or str(Path.cwd() / ".env")
    set_key(env_file, "CRED_ENCRYPTION_KEY", key, quote_mode="always")
    command.stdout.write(command.style.SUCCESS("  CRED_ENCRYPTION_KEY written to .env\n"))


def get_doc_tokens():
    """
    Optional hook discovered by ophix-docs (if installed), for {{ token }}
    substitution in shared markdown like the Client Quickstart doc.
    """
    return {
        "client_package": "ophix-cred-client",
        "client_command": "cred-client",
        "client_venv": ".cred-env",
        "client_env": ".cred.env",
    }


def get_revisions_targets():
    """
    Optional hook discovered by ophix-revisions (if installed). stable=False
    until Phase B (deterministic encryption) lands — export_creds's Fernet
    encryption is non-deterministic by design, so --stable isn't meaningful here yet.
    """
    return [
        {
            "name": "creds",
            "app_label": "ophix_creds",
            "export_command": "export_creds",
            "encrypted": True,
            "stable": False,
        },
    ]
