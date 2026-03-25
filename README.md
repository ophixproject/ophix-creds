# ophix-creds

Credentials domain plugin for **Ophix Project Servers**.

Stores named JSON secrets and distributes them to authorised clients
over HTTPS with token + IP authentication.

This is the `ophix-server-base` replacement for the standalone
`cred-server` application.

---

## Installation

```bash
pip install ophix-server-base ophix-creds
```

With documentation and theme tools:

```bash
pip install ophix-server-base ophix-creds ophix-docs ophix-theme-tools
```

---

## What this plugin provides

- `Credential` model — named JSON secret with `enabled` flag
- `ClientCredential` join model — per-client permissions
  (`enabled`, `can_update`, `can_delete`, `can_share`)
- `GET/POST/PUT/DELETE /api/credentials/<n>/` API endpoints
- Django admin with inline `ClientCredential` management
- Built-in documentation (loaded by `ophix_docs_update` if ophix-docs
  is installed)

---

## Migrating from cred-server

The API surface is identical. The client (`ophix-cred-client`) requires
no changes. The only difference is the server-side deployment:

1. Replace the standalone `cred-server` virtualenv with one containing
   `ophix-server-base` and `ophix-creds`.
2. Set `DJANGO_SETTINGS_MODULE=ophix.settings`.
3. Run `ophix-manage migrate`.
4. Run `ophix-manage collectstatic`.

Database schema differences:

- `ClientCredential` gains `can_update`, `can_delete`, `can_share` columns.
  Existing rows default to `can_update=False`, `can_delete=False`.
  Review and update permissions as needed after migration.
