---
title: Credentials
slug: credentials
order: 100
section: Credentials
---

The credentials domain stores named JSON secrets and distributes them to authorised clients over HTTPS. Secrets are fetched on demand and used in memory only — they are never written to disk on the client side.

Each credential is a named object containing arbitrary JSON (`secret_json`). Access is controlled per-client: a client can only retrieve credentials it has been explicitly linked to by an administrator.

---

## Encryption at rest

The `secret_json` field is encrypted at rest in the database using Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256). The encrypted token is what is stored in the database column — the plaintext secret is never written to disk in readable form.

Encryption and decryption happen transparently: the admin interface, the API, and client tools all work with the plaintext JSON value as normal.

### Initial setup

Before running `migrate` for the first time, generate an encryption key:

```bash
ophix-manage generate_cred_key
```

This prints a key. Add it to your `.env`:

```ini
CRED_ENCRYPTION_KEY=<generated key>
```

Then run migrations:

```bash
ophix-manage migrate
```

The migration encrypts any existing plaintext records. If `CRED_ENCRYPTION_KEY` is not set, the migration will stop with a clear error before making any changes.

### Upgrading an existing deployment

If you are adding encryption to a credential server that already has data:

1. `ophix-manage generate_cred_key` — generate and record the key
2. Add `CRED_ENCRYPTION_KEY=<key>` to `.env`
3. `ophix-manage migrate` — encrypts all existing `secret_json` values in place
4. Restart the server

### Key management

- The key is a 32-byte Fernet key, stored as URL-safe base64 in `.env`
- **Back up the key separately from the database.** Losing the key means losing access to all stored credentials — the ciphertext cannot be recovered without it

### Key rotation

To replace the encryption key and re-encrypt all credentials in place:

```bash
ophix-manage rotate_cred_key
```

This generates a new key automatically. To supply your own:

```bash
ophix-manage rotate_cred_key --new-key <key>
```

The command:

1. Re-encrypts all credentials in a **single database transaction** — if anything fails, the database rolls back and the current key remains valid
2. Prints the new key to stdout **before** updating `.env` — if the file write fails, you can set `CRED_ENCRYPTION_KEY` manually without losing any data
3. Updates `CRED_ENCRYPTION_KEY` in `.env` after the transaction commits

After rotation, restart the server for the new key to take effect. Use `--no-input` for scripted/scheduled rotation.

---

## cred-client

`cred-client` is the Tier 1 command-line client for the Ophix credential server. Configuration is stored in `.cred.env`.

| Variable | Description |
| --- | --- |
| `CREDSERVER_URL` | Credential server base URL |
| `CREDSERVER_CA_CERT` | Path to the server CA certificate |
| `CREDSERVER_API_TOKEN` | 64-character hex API token |

### Installation

```bash
pip install ophix-cred-client
```

### Bootstrapping

```bash
# One step
cred-client quickstart https://credserver.internal my-client-name

# Step by step
cred-client set server https://credserver.internal
cred-client download ca-cert
cred-client register my-client-name
```

### Token rotation

```bash
cred-client rotate-token
```

Validates the new token before overwriting `.cred.env`. Safe to run from cron.

### Fetching credentials

```bash
cred-client fetch db_prod         # prints JSON to stdout
```

### Verifying retrieval

```bash
cred-client check --all                    # check all mapped credentials
cred-client check --all --verbose          # show error detail on failure
cred-client check --var DB_PROD_CRED_NAME  # check by env var name
cred-client check --name db_prod           # check by credential name
```

### Importing credentials

The `import` command uploads a JSON file as a new credential. The credential name can be supplied three ways:

**`--name` only** — creates the credential with the given name:

```bash
cred-client import --name db_prod --input-file db_prod.json
```

**`--env` only** — reads the credential name from the named mapping in `.cred.env`. Use this when the mapping already exists and you want to refresh the credential:

```bash
cred-client import --env DB_PROD_CRED_NAME --input-file db_prod.json
```

**`--name` and `--env` together** — writes the `ENV=name` mapping to `.cred.env` and creates the credential in one step. This is the recommended workflow when setting up a new credential that Tier 2 clients will consume via `get_cred()`:

```bash
cred-client import --name db_prod --env DB_PROD_CRED_NAME --input-file db_prod.json
```

If `DB_PROD_CRED_NAME` is already present in `.cred.env` with a different name, the command refuses with an error — edit `.cred.env` manually if you intend to remap it.

**Updating an existing credential:**

```bash
cred-client import --name db_prod --input-file db_prod.json --overwrite
```

`--overwrite` updates the credential in place. Requires `can_update` on the client-credential link.

---

## Managing credentials in admin

Credentials and client access are managed through the Django admin:

- **Credentials** — create and edit credentials, view which clients have access
- **Client** detail page — manage which credentials a client can access via the Credentials inline

When you link a client to a credential, the `enabled` checkbox on the link controls whether access is active. The client must also be enabled, and the credential must be enabled, for retrieval to succeed. Disabled links are shown in the admin list in italic muted text.

---

## Tier 2 usage

Tier 2 clients (scripts and services that consume credentials) import directly from the client library. They do not communicate with the server directly.

```python
from ophix_cred_client import get_cred

# Fetch the credential whose name is stored in the DB_PROD_CRED_NAME env var
secret = get_cred("DB_PROD_CRED_NAME")

# secret is the secret_json dict — use it in memory, never persist it
connection = connect(
    host=secret["HOST"],
    user=secret["USER"],
    password=secret["PASS"],
)
```

`get_cred(env_var_name)` reads the credential name from the named environment variable, fetches it from the server, and returns the `secret_json` dict. If the env var is not set or the fetch fails, it exits with an error.

The env var pattern separates configuration (which credential to use) from secrets (the credential content itself). The `.cred.env` file maps env var names to credential names; the server holds the secrets.

---

## API reference

All requests require `Authorization: Token <api_token>` and must originate from the registered host IP.

### Fetch a credential

```http
GET /api/credentials/<name>/
```

Response — 200 OK:

```json
{
  "name": "db_prod",
  "description": "Production database credentials",
  "secret_json": {
    "HOST": "db.internal",
    "USER": "appuser",
    "PASS": "secret"
  },
  "updated_at": "2026-03-01T12:00:00Z"
}
```

### Create a credential

```http
POST /api/credentials/<name>/
Content-Type: application/json

{
  "secret_json": { "KEY": "value" },
  "description": "Optional description"
}
```

Returns 201 Created. The creating client is automatically granted `can_update` and `can_delete`.

### Update a credential

```http
PUT /api/credentials/<name>/
Content-Type: application/json

{
  "secret_json": { "KEY": "new_value" }
}
```

Requires `can_update` on the client-credential link.

### Delete a credential

```http
DELETE /api/credentials/<name>/
```

Requires `can_delete` on the link **and** `ENABLE_ARTIFACT_DELETE=true` in the server `.env`.

---

## Server settings

Run `ophix-manage generate_deploy_config --env` to generate a sample `.env` with all variables and their descriptions.

| Variable | Default | Description |
| --- | --- | --- |
| `CRED_ENCRYPTION_KEY` | _(required)_ | Fernet encryption key for `secret_json` at-rest encryption. Generate with `ophix-manage generate_cred_key`. Must be set before running `migrate`. |
| `ENABLE_ARTIFACT_DELETE` | `False` | Allow clients to delete credentials they own. Disabled by default — enable only if client-driven deletion is required. |
| `AUTH_LEAK_INFO` | `False` | Include error detail in API responses. Set to `True` during development only; `False` in production prevents auth failure fingerprinting. |
| `MINIMUM_TOKEN_ROTATE_TIME` | `3600` | Minimum seconds between token rotations. Prevents rotation abuse. Default is 1 hour. |

---

## Access control

Every request is validated through four layers:

1. `Host.enabled` — the host machine is registered and active
2. `Client.enabled` — the specific client process is active
3. `Credential.enabled` — the credential itself is active
4. `ClientCredential.enabled` — this client has been granted access to this credential

If any layer fails, the request returns **403 Forbidden**. In production (`AUTH_LEAK_INFO=false`) the response does not distinguish between failure reasons.
