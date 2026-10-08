# Installing ophix-creds (Credserver)

This walks through a production-style install of a credserver: a Linux host, running as an
unprivileged service user, fronted by nginx and managed by systemd. If you just want a quick
local/dev instance with no TLS, no nginx, and no systemd, see the "Development setup" section of
[Server Installation](https://github.com/ophixproject/ophix-server-base) instead - this guide
covers the real deployment path.

---

## Before you start / Prerequisites

Not sure what's already on your server? A few one-liners to check:

```bash
python3 --version   # need 3.10 or later
openssl version     # only relevant if self-issuing a certificate (see below)
nginx -v
mysql --version     # only relevant if you're using MariaDB/MySQL (ophix-dbengine-mariadb)
```

You will need:

- A Linux server with:
  - Python 3.10 or later
  - nginx
  - systemd
  - `openssl` (needed if you self-issue a certificate - see below)

  We test on Ubuntu (20/22/24/26 LTS). Other distros should work - `configure_install` (Step 3
  below) asks where nginx config should go, defaulting to the Debian/Ubuntu layout
  (`/etc/nginx/sites-available/`, symlinked into `sites-enabled/`). If your distro loads `*.conf`
  files directly from one directory instead - RHEL/Fedora-family `conf.d` in particular - point
  the config directory there and leave the enabled directory blank; no separate symlink step is
  created in that case. The systemd unit path (`/etc/systemd/system/`) is standard across all
  systemd distros, so nothing to configure there. `adduser` below is the Debian/Ubuntu frontend to
  `useradd`; on other distros use the equivalent for yours.

- If you're using the recommended default engine, `ophix-dbengine-mariadb` (Step 2 below) brings in
  `mysqlclient` (MariaDB/MySQL client bindings), which is a C extension. If pip has to build it
  from source on your platform (no prebuilt wheel available), you'll also need build tools
  installed first:

  ```bash
  sudo apt install -y build-essential default-libmysqlclient-dev pkg-config python3-dev
  ```

  Using a different engine instead? Skip this - it's only needed for MariaDB/MySQL.

- An SSL/TLS certificate for the hostname you'll run the server on. It can be from a public CA, or
  self-issued for internal use - [`ophix-ca-tools`](https://github.com/ophixproject/ophix-ca-tools)
  is a small standalone shell/OpenSSL CA built for exactly this. You'll need three files: the
  certificate, its private key (PEM format), and - if self-issued - the CA bundle used to sign it
  (not needed for a certificate from a public CA).

  With `ophix-ca-tools`, a cert's key and crt are already stored together under
  `ssl/<domain>/<host>/` after `issue_cert.sh create`, and the CA bundle lands in your current
  directory after you run `generate_ca_bundle.sh` (normally the `ophix-ca-tools` checkout itself,
  unless you `cd` elsewhere first). We recommend copying all three into a single folder under the
  service user's own home directory, e.g. `/home/ophix/ssl/creds.internal.yourdomain.com/` - the
  `ophix` user (created below) needs read access to wherever you point `configure_install` at, and
  consolidating them there sidesteps any cross-user permission fiddling.

- A database (MariaDB/MySQL/PostgreSQL/CockroachDB/SQL Server), with the following ready:
  - host and port
  - database name
  - username and password

  Every engine - MariaDB included - needs its matching `ophix-dbengine-*` driver plugin installed
  alongside `ophix-creds`; none is bundled by default (see Step 2 below).

Once all of the above is sorted, you're ready to install. These instructions install the server in
user space - the service runs as an unprivileged user throughout, and `sudo`/root is only needed
for the one step that wires up nginx and systemd.

---

## Step 0 (optional) - Create a user to run your server

As a user with `sudo` access:

```bash
sudo adduser --disabled-password --gecos "" ophix
```

This creates the `ophix` user with a home directory and no usable login password - you'll operate
as it via `sudo`, not by logging in directly. Everything from here on (Steps 1–4) runs as this
user, not root:

```bash
sudo -iu ophix
```

## Step 1 - Create the install directory and a virtual environment

```bash
cd ~
mkdir credserver && cd credserver

python3 -m venv .cred-env
source .cred-env/bin/activate
```

(Or use [uv](https://docs.astral.sh/uv/) instead of `venv` - `uv venv .cred-env`. uv doesn't seed
`pip` by default, so either use `uv pip install` in Step 2 or create the venv with `--seed`.)

## Step 2 - Install the credserver and recommended add-ons

```bash
pip install ophix-creds ophix-dbengine-mariadb ophix-docs ophix-client-management venv-cmds
```

- `ophix-server-base` and `ophix-codemirror` are both pulled in automatically as dependencies of
  `ophix-creds` - no need to install either separately. `ophix-codemirror` is what gives the
  `secret_json` field a syntax-aware JSON editor in the admin UI.
- `ophix-dbengine-mariadb` installs the MariaDB/MySQL driver. Every database engine needs its
  matching `ophix-dbengine-*` plugin installed explicitly - none is bundled by default, MariaDB
  included. Swap it for a different one if you're using another engine:

  ```bash
  pip install ophix-dbengine-postgres     # PostgreSQL
  pip install ophix-dbengine-mssql        # SQL Server (also requires ODBC Driver 17/18 at the OS level)
  pip install ophix-dbengine-cockroachdb  # CockroachDB
  ```

- `ophix-docs` - inline markdown documentation in the admin UI (recommended, optional).
- `ophix-client-management` - fleet client status dashboard: token rotation health, client
  package versions, last-seen tracking (recommended, optional).
- `venv-cmds` - lists the console commands available in this venv and checks installed packages
  for updates (recommended, optional).

## Step 3 - Configure the server

```bash
ophix-manage configure_install ophixcredserver
```

In this command "ophixcredserver" is the slug, this example is chosen deliberately - it doesn't have to match the install directory name (`credserver` above), and giving it the `ophix` prefix here means the resulting systemd service (`ophixcredserver`) reads unambiguously in `systemctl status` alongside any other, non-Ophix services on the box. Use whatever slug you like; it becomes the name of every generated file and the service itself.

The wizard is interactive and asks for:

- Install directory (where runtime data - logs, SSL certs, the socket - will live)
- Server hostname (used in the nginx config and to validate your TLS certificate)
- Service user and group (defaults to `ophix`/`ophix`, matching Step 0)
- nginx config directory and enabled directory - defaults to the Debian/Ubuntu layout; see the
  Prerequisites note above if you're on a distro that lays nginx config out differently
- TLS certificate and private key paths - point these at the files from the Prerequisites step;
  the wizard validates the certificate actually covers the hostname you gave, and warns if not
- Database engine and connection details, with a live connection test before anything is saved.
  If you only installed one engine in Step 2 (eg. `ophix-dbengine-mariadb`), it will be auto-selected and you'll just be asked for host/port/credentials.  If you installed more than one for some reason, you'll be asked to pick which one you want to use.
- **`CRED_ENCRYPTION_KEY`** - the one setting specific to `ophix-creds`. This is the Fernet key
  used to encrypt every stored credential at rest. The wizard offers two choices:
  - **Generate** (the default, and what you want for a fresh install) - a new key is created and
    written into `.env` automatically. Nothing further to do, but back up the resulting `.env`
    somewhere safe once the install is done - losing this key means losing access to every
    credential ever stored on this server, permanently. There is no recovery path.
  - **Supply an existing key** - only relevant if you're rebuilding a venv against a database that
    already has encrypted credentials in it (e.g. redeploying onto a new host, or recovering after
    wiping a venv). You'll be prompted to paste the original key; if you don't have it, the
    existing credentials are unrecoverable regardless of anything else in this guide.
- Superuser username, email, and password (your first admin login)
- Theme to activate and admin title, the "Ophix" theme is included by default.

The wizard writes `.ophixcredserver.conf` (used by the next step) and `.env` (Django's runtime
settings, with everything above already patched in) - both `chmod 600`. It's safe to re-run at any
time to change a setting; existing values are offered as defaults.

## Step 4 - Install the configured server

```bash
ophix-manage run_install ophixcredserver
```

Reads `.ophixcredserver.conf` and, in one pass:

1. Creates the install directory's subdirectory structure (`logs/`, `ssl/`, `run/`, etc.)
2. Copies your TLS certificate and key into `ssl/certs/` and `ssl/private/`
3. Generates `ophixcredserver.nginx.conf`
4. Generates `ophixcredserver.service` (the systemd unit)
5. Generates `ophixcredserver-sudo-install.sh` - the root script for Step 5
6. Generates `ophixcredserver-sudo-uninstall.sh` - can be run as root for a clean uninstall
7. Runs database migrations - creates the database structure in your empty database
8. Collects static files
9. Creates the superuser account
10. Activates the selected theme and sets the admin title
11. Loads inline documentation, since `ophix-docs` is installed
12. Generates static error pages (400, 403, 404, 500, 503) using the active theme
13. Creates the backup directory and generates `ophixcredserver-backup.sh`, since Step 3
    configured a backup directory
14. Generates `ophixcredserver-update.sh`, a convenience script for future upgrades
15. Runs `check_updates` quietly, to populate the Plugin Versions admin page for the
    first time - nothing else does this on a fresh install; `ophixcredserver-update.sh`
    keeps it current on every upgrade after this

All generated filenames use the slug (`ophixcredserver`), not `ophix-creds`'s own default
server name (`credserver`) - this is what keeps filenames unique if you ever run more than
one credserver instance on the same box.

Available flags if you need to skip a step: `--skip-migrate`, `--skip-collectstatic`,
`--skip-superuser`.

## Step 5 - System integration (as root)

Back with `sudo` access (exit the `ophix` shell, or open a new one):

```bash
sudo bash ophixcredserver-sudo-install.sh
```

This is the only step that touches anything outside the install directory. It:

- Sets ownership and permissions on the install directory
- Installs the nginx config and enables it
- Installs the systemd unit, enables it, and starts the service

---

That's it - you're done. The admin UI should now be live at `https://<your-hostname>/admin/`.

## Next steps

- Make sure `<your-hostname>` actually resolves to this host's IP - a DNS record update (or,
  for local testing, a `/etc/hosts` entry) is often the last piece still outstanding at this
  point, and the admin UI won't be reachable until it's in place.
- Login with your superuser account
- Go to **Admin → Hosts** and create a Host entry for each machine that will run a client - clients
  register themselves against a Host's IP on first run.
- See the **Client Quickstart** doc (in the admin's Documentation panel, if `ophix-docs` is
  installed) for how to bootstrap a client against this server.
- For `ophix-creds` specific instructions go to **Documentation → Search** and search for
  `cred-client`. You will need to install
  [ophix-cred-client](https://github.com/ophixproject/ophix-cred-client) in each virtual
  environment that needs to fetch credentials. A single user account can have multiple clients,
  as long as each one has its own venv.
