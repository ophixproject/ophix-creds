# Ophix Creds Release Notes

## Unreleased

- `ophix_creds` gains `get_revisions_targets()`, declaring its own `creds` target for
  `ophix-revisions` (if installed) to discover at runtime — no separate registration
  needed anywhere else. Declared `stable=False` for now: `export_creds`'s Fernet
  encryption is non-deterministic by design (random IV/timestamp per token, random KDF
  salt per run), so `--stable` isn't meaningful here until a deterministic-encryption
  scheme is built.

## 2026.07.07.01

- `CRED_ENCRYPTION_KEY` is now written to `.env` with single-quote wrapping
  (`quote_mode="always"`), both at install time and during `rotate_cred_key`.
  Previously written unquoted; special shell characters in the value could corrupt
  the key when the file was `source`d by the backup script.

## 2026.06.09.01

- Added "Scheduled backups" section to `credential-backup.md` with recommended `.env` values.

## 2026.06.05.03

- `export_creds`: export file now includes a `meta` block with `created_at`, `server_name`, `server_version`, `hostname`, `domain`, `command`, `run_by`, `login_user`, and `ssh_origin`.
- `export_creds`, `import_creds`: `--passphrase` now accepts no value to prompt securely (export confirms twice); `--passphrase-env ENVVAR` reads the passphrase from an environment variable for automated use. Both options are mutually exclusive.

## 2026.05.30.03

- `rotate_cred_key` now handles Ctrl+C gracefully — prints "Cancelled." instead of a stack trace.

## 2026.05.30.02

- Added inline documentation page "Credential Backup and Migration" covering
  `export_creds` and `import_creds`, including restore dependency order,
  passphrase encryption, the distinction between transport encryption and
  `CRED_ENCRYPTION_KEY`, and full restore workflow.

## 2026.05.30.01

- Added `export_creds` management command — exports Credential records to JSON.
  Secrets can be encrypted with `--passphrase` (PBKDF2-derived Fernet, same
  scheme as `export_clients`). Use `--include-client-links` to also export
  ClientCredential join records (client access and permission flags).
- Added `import_creds` management command — imports from an `export_creds` file.
  Idempotent (matched by credential name); existing records updated only when
  changed. `--include-client-links` imports join records; referenced clients and
  hosts must already exist (run `import_hosts` + `import_clients` first).
  Supports `--dry-run` and `--quiet`.

## 2026.05.22.01

- Removed `import_legacy_credserver` management command — legacy migration is
  complete and the command is no longer needed.

## 2026.05.03.02

- Added `OPHIX_RELEASE_NOTES.md` for release notes delivery.
