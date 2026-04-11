---
title: Credentials
slug: credentials
order: 10
section: Credentials
---

The credentials domain stores named JSON secrets and distributes them to authorised clients over HTTPS. Secrets are fetched on demand and used in memory only — they are never written to disk on the client side.

Each credential is a named object containing arbitrary JSON (`secret_json`). Access is controlled per-client: a client can only retrieve credentials it has been explicitly linked to by an administrator.

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

```bash
cred-client import --name db_prod --input-file db_prod.json
cred-client import --name db_prod --input-file db_prod.json --overwrite
echo '{"HOST":"db.internal","PASS":"secret"}' | cred-client import --name db_prod --input-file -
```

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
from ophyx_cred_client import get_cred

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

The credentials plugin has no plugin-specific settings. The following base settings from `ophix-server-base` are most relevant to a credential server deployment. Run `ophix-manage generate_deploy_config --env` to generate a sample `.env` with all variables and their descriptions.

| Variable | Default | Description |
| --- | --- | --- |
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
