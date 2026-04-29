---
title: Upgrading from Legacy credserver
slug: legacy-upgrade
order: 110
section: Credentials
---

This page covers upgrading from the pre-refactor `cred-server` package (app label `creds`) to the current `ophix-creds` package. If you installed ophix-creds from scratch, this page does not apply.

---

## What changed

The legacy `cred-server` and current `ophix-creds` are structurally incompatible — you cannot run `migrate` against an old database and have it work. The key differences are:

| Area | Legacy (`cred-server`) | Current (`ophix-creds`) |
| --- | --- | --- |
| App label | `creds` | `ophix_creds` |
| Table names | `creds_*` | `ophix_creds_*` / `ophix_core_*` |
| Host / Client models | In `creds` app | In `ophix_core` (ophix-server-base) |
| `secret_json` storage | Plaintext JSONField | Fernet-encrypted TextField |
| `ClientCredential` | `enabled`, `notes` only | + `can_update`, `can_delete`, `can_share` |

The `can_update`, `can_delete`, and `can_share` permission columns are all imported as `False` — no permissions are escalated during migration.

---

## Upgrade path

The recommended approach is a **side-by-side migration**: keep the old server running until the new one is fully verified, then decommission it.

### 1. Set up the new credserver

Follow the standard installation guide — fresh venv, fresh database:

```bash
pip install ophix-server-base ophix-creds
ophix-manage configure_install credserver
ophix-manage run_install credserver
sudo bash credserver_sudo_install.sh
```

At the `configure_install` step you will be prompted to generate a `CRED_ENCRYPTION_KEY`. Generate a new key — do not try to reuse anything from the old server, which had no encryption.

### 2. Verify the new server is running

Check the admin UI at `https://your.new.hostname/admin/` before proceeding. Confirm migrations are applied:

```bash
ophix-manage migrate --check
```

### 3. Run the import command

The `import_legacy_credserver` command connects directly to the old database, reads all data, encrypts credentials in-flight with the new `CRED_ENCRYPTION_KEY`, and writes into the new schema.

```bash
ophix-manage import_legacy_credserver \
    --db-host <old-db-host> \
    --db-name <old-db-name> \
    --db-user <old-db-user> \
    --db-password <old-db-password>
```

Use `--dry-run` first to see what will be imported without writing anything:

```bash
ophix-manage import_legacy_credserver --db-name credserver_db --dry-run
```

For a PostgreSQL source database:

```bash
ophix-manage import_legacy_credserver --db-engine postgres --db-name ...
```

The command is safe to re-run — records that already exist in the new database are skipped with a warning, not overwritten.

### 4. Verify imported data

Log into the new admin UI and confirm:

- All Hosts appear under **Clients & Hosts → Hosts**
- All Clients appear under **Clients & Hosts → Clients**
- All Credentials appear under **Credentials → Credentials**
- Client-credential links are intact

Test that an existing fleet client can fetch a credential against the new server:

```bash
cred-client get <credential-name>
```

Existing clients do **not** need to re-register — their tokens are imported verbatim and continue to work.

### 5. Update client configuration

Fleet clients currently point at the old server URL. Update `.cred.env` on each host:

```bash
cred-client set server https://new.credserver.hostname
cred-client download ca-cert   # if TLS CA has changed
```

Or use `cred-client quickstart` to re-bootstrap against the new URL, which re-downloads the CA cert and verifies connectivity without issuing a new token.

### 6. Decommission the old server

Once all clients are verified against the new server, stop and remove the old one.

---

## Notes

- **Tokens are preserved.** The import carries over `api_token` values verbatim, so clients reconnect without re-registering.
- **Encryption.** The `CRED_ENCRYPTION_KEY` on the new server is unrelated to anything on the old server. All imported credentials are re-encrypted with the new key. Back this key up securely.
- **New permission columns.** `can_update`, `can_delete`, and `can_share` all default to `False` on import. Review them in the admin UI if client-driven writes are needed.
- **The old database is not modified** at any point during the import.
