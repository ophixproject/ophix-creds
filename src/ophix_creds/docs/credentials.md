---
title: Credentials
slug: credentials
order: 10
section: Credentials
---

# Credentials

The **Credentials** plugin stores named JSON secrets and distributes
them to authorised clients over HTTPS.

Each credential is a named object with arbitrary JSON content
(`secret_json`). Access is controlled by the `ClientCredential` join
table — a client may only retrieve credentials it has been explicitly
linked to by an administrator.

---

## API

### Fetch a credential

```
GET /api/credentials/<name>/
Authorization: Token <api_token>
```

**200 OK**
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

---

### Create a credential

```
POST /api/credentials/<name>/
Authorization: Token <api_token>
Content-Type: application/json

{
  "secret_json": { "KEY": "value" },
  "description": "Optional description"
}
```

The creating client is automatically granted `can_update` and
`can_delete` on the new credential.

---

### Update a credential

```
PUT /api/credentials/<name>/
Authorization: Token <api_token>
Content-Type: application/json

{
  "secret_json": { "KEY": "new_value" }
}
```

Requires `can_update` on the `ClientCredential` join record.

---

### Delete a credential

```
DELETE /api/credentials/<name>/
Authorization: Token <api_token>
```

Requires `can_delete` on the join record **and**
`ENABLE_ARTIFACT_DELETE=true` in the server `.env`.

---

## Access control

All requests are validated through the standard Ophix 4-layer check:

1. `Host.enabled`
2. `Client.enabled`
3. `Credential.enabled`
4. `ClientCredential.enabled` (can_read) + operation-specific flag

If any layer fails the request returns **403 Forbidden**.
