---
title: Credential Backup and Migration
slug: credential-backup
order: 110
section: Credentials
---

Credential records can be exported to a JSON file and imported on another server. This supports server migration, disaster recovery, and environment cloning (e.g. staging from production).

Because credentials contain secrets, the export file should be encrypted with a passphrase and stored securely.

---

## Restore dependency order

Credential imports reference clients by name. The full restore sequence for a credential server is:

```
import_hosts  →  import_clients  →  import_creds
```

Run `import_hosts` and `import_clients` (from `ophix-server-base`) before importing credentials with client links. See [Server Backup and Migration](server-backup) for the base-layer commands.

If you are only restoring credentials themselves (no client links), `import_creds` can run independently.

---

## Exporting credentials

**Export with encrypted secrets (recommended):**

```bash
ophix-manage export_creds --output-file creds.json --passphrase 'your-passphrase'
```

**Also export client access links:**

```bash
ophix-manage export_creds --output-file creds.json --passphrase 'your-passphrase' --include-client-links
```

**Preview without writing:**

```bash
ophix-manage export_creds --output-file creds.json --passphrase 'your-passphrase' --dry-run
```

Without `--passphrase`, secrets are written as plaintext JSON. The command prints a warning. Treat an unencrypted export file as a credential store — restrict access accordingly.

> **Note:** Always use single quotes around passphrases in bash. Double-quoted strings allow bash to interpret `!` as a history event, which corrupts a passphrase containing an exclamation mark.

| Flag | Description |
| --- | --- |
| `--output-file FILE` | _(required)_ Destination path |
| `--passphrase PASSPHRASE` | Encrypt secret values using a PBKDF2-derived Fernet key |
| `--include-client-links` | Also export `ClientCredential` join records (client access and permission flags) |
| `--dry-run` | Show how many credentials would be exported without writing |
| `--quiet` | Suppress all output |

### What is exported

Each credential record includes:

- `name` — the unique credential identifier
- `description` — optional description text
- `secret_json` — the secret payload (encrypted if `--passphrase` was used)
- `enabled` — whether the credential is active

With `--include-client-links`, each record also includes its `ClientCredential` join records, capturing which clients have access and with what permission flags (`enabled`, `can_update`, `can_delete`, `can_share`, `notes`).

### How secret encryption works

Each `secret_json` value is serialised to JSON, then encrypted individually using a Fernet key derived from the passphrase via PBKDF2-HMAC-SHA256 (480,000 iterations). A random 16-byte salt is generated per export and stored in the file. The passphrase is not stored — you must provide it again on import.

This transport encryption is independent of the server's `CRED_ENCRYPTION_KEY`. The import command decrypts using the export passphrase, then re-encrypts at rest using whatever `CRED_ENCRYPTION_KEY` is configured on the target server. You can restore to a server with a different encryption key without any extra steps.

---

## Importing credentials

```bash
ophix-manage import_creds --input-file creds.json --passphrase 'your-passphrase'
```

**Also import client links:**

```bash
ophix-manage import_creds --input-file creds.json --passphrase 'your-passphrase' --include-client-links
```

**Preview without writing:**

```bash
ophix-manage import_creds --input-file creds.json --passphrase 'your-passphrase' --dry-run
```

The passphrase is validated against the first secret in the file before any database changes are made. An incorrect passphrase stops the import immediately.

Credentials are matched by name. Existing credentials are updated only when a field value differs; identical records are skipped. The `secret_json` is always written on update. The import is idempotent — safe to re-run.

For client links, referenced hosts and clients must already exist on the target server. Missing hosts or clients are reported per-record and skipped; the credential itself is still imported.

| Flag | Description |
| --- | --- |
| `--input-file FILE` | _(required)_ Source path (JSON produced by `export_creds`) |
| `--passphrase PASSPHRASE` | Decrypt secrets (required if file was exported with `--passphrase`) |
| `--include-client-links` | Also import `ClientCredential` join records from the file |
| `--dry-run` | Show what would be created or updated without making any changes |
| `--quiet` | Suppress per-record output; summary line always shown |

---

## Full credential server restore workflow

```bash
# 1. Export from the source server
ophix-manage export_hosts --output-file hosts.json
ophix-manage export_clients --output-file clients.json --passphrase 'client-passphrase'
ophix-manage export_creds --output-file creds.json --passphrase 'cred-passphrase' --include-client-links

# 2. Transfer all three files to the target server

# 3. Ensure the target server has CRED_ENCRYPTION_KEY set in .env and migrations run

# 4. Import on the target server in dependency order
ophix-manage import_hosts --input-file hosts.json
ophix-manage import_clients --input-file clients.json --passphrase 'client-passphrase'
ophix-manage import_creds --input-file creds.json --passphrase 'cred-passphrase' --include-client-links
```

Fleet clients can reconnect and retrieve credentials immediately after the restore without re-registering or re-linking.

---

## Notes on the encryption key

The `CRED_ENCRYPTION_KEY` in `.env` controls at-rest encryption in the database. It is **not** the same as the export passphrase.

- The export passphrase protects the export file in transit and storage
- The `CRED_ENCRYPTION_KEY` protects secrets in the database on the running server

Both must be kept secure. If you lose `CRED_ENCRYPTION_KEY`, the credentials in the database cannot be recovered — the export file (if encrypted with a known passphrase) is the only recovery path.

Back up the encryption key separately from the database dump.

---

## Scheduled backups

`ophix-manage create_backup_script` generates `ophix-backup.sh` — a cron-ready wrapper that reads `BACKUP_TARGETS` and `BACKUP_TARGETS_ENCRYPTED` from `.env` and runs the corresponding export commands.

Add to `.env` to include credentials in the scheduled backup:

```ini
BACKUP_TARGETS_ENCRYPTED=creds
```

Credentials contain secrets — always keep `BACKUP_PASSPHRASE` set when `creds` is in `BACKUP_TARGETS_ENCRYPTED`. The backup script logs a warning and exports without encryption if `BACKUP_PASSPHRASE` is absent.
