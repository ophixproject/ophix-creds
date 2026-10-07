# Ophix Creds Release Notes

## 2026.10.07.01

- Added `get_doc_tokens()` hook, discovered by `ophix-docs` (if installed) for
  `{{ token }}` substitution in shared markdown. Contributes `client_package`
  (`ophix-cred-client`) and `client_command` (`cred-client`) so the generic
  Client Quickstart doc in `ophix-server-base` can render this domain's correct
  example instead of staying generic.

## 2026.10.05.04

- Fixed the `Tier 2 usage` example in the `credentials` inline doc: `from ophix_cred_client
  import get_cred` was never valid — the pip package `ophix-cred-client` strips its `ophix-`
  prefix for the actual Python module name (`cred_client`), and nothing is re-exported at the
  package root, so even the correctly-spelled version would have raised `ImportError`. Found
  while sweeping git history for a public-release pass; `cred_client.core.get_cred`'s own
  docstring already documents the correct form. Now reads `from cred_client.core import
  get_cred`.

## 2026.10.05.03

- Added the `Programming Language :: Python :: 3.14` classifier, after real verification
  (not a rubber-stamp add): a fresh Python 3.14 venv, a live `migrate` through this
  package's full migration history, real HTTP requests against every registered admin
  page (changelist with disabled-row styling, add-form, change-form), a real
  `export_creds`/`import_creds` round trip, and `generate_cred_key`/`rotate_cred_key`
  executed for real against a live database. All passed.
- Found and fixed a real (non-3.14-specific) portability bug along the way: `_build_meta()`
  in `export_creds.py` had `import pwd` as an unconditional top-level import inside a
  function whose own surrounding `try/except` was clearly meant to tolerate exactly this
  failure mode (the existing fallback to `os.environ.get("USER")`/`"LOGNAME"`). Since `pwd`
  is POSIX-only, this crashed outright on any non-POSIX platform before the `try` could ever
  run. Never a problem on production (Linux) servers, but it blocked `export_creds` from
  running at all during local development/testing on Windows. Moved the import inside the
  `try`.

## 2026.10.05.02

- Dropped an unnecessary `str(...)` around the two `_()`-wrapped fleet-API error strings in
  `views.py` added in `2026.10.05.01` — `err_response`'s own docstring in `ophix-server-base`
  documents the canonical usage as plain `_(...)` with no explicit coercion (DRF's JSON encoder
  already handles lazy translation proxies directly). No functional change; just matches the
  documented pattern exactly, consistent with the same fix in `ophix-confs`.

## 2026.10.05.01

- i18n regression sweep, ahead of this domain's own public-release pass: wrapped the
  `ValidationError` raised on invalid JSON in `EncryptedJSONField` (`fields.py`), and the two
  fleet-API error strings in `CredentialDetailView` (`views.py` — "Credential already exists"
  and "Credential deletion is disabled on this server."), which had been left unwrapped
  intentionally to match a sibling-domain convention. That convention was corrected during the
  taskserver wave's own i18n pass after confirming every known Tier 1 client branches purely on
  HTTP status code and never parses the JSON body text for control flow, so wrapping these is
  safe. Everything else in the package — `models.py`, `admin.py`, `apps.py`, `serializers.py` —
  was already fully wrapped from an earlier pass.

## 2026.08.30.01

- Disabled-client/disabled-credential styling in the "Authorised Credentials"
  (Client admin) and "Authorised Clients" (Credential admin) linked-artifact
  columns changed from an italic red-tinted mix
  (`color-mix(..., var(--admin-interface-delete-button-background-color) ...)`)
  to the theme's dedicated disabled colour at a heavier weight, italic kept
  (`var(--admin-interface-disabled-color); font-weight: 600; font-style:
  italic`), matching the same treatment applied fleet-wide to changelist
  disabled rows.

## 2026.08.04.01

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
