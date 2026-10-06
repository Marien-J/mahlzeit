# Running and deploying Mahlzeit

Everything runs from `compose.yaml` and is configured in `.env`. The same files serve a laptop,
a rented server and an on-prem machine; only `.env` differs.

| Service | What it does |
| --- | --- |
| caddy | Serves the PWA, proxies `/api` (including the live event stream) and `/mcp` to the app, gets TLS certificates |
| app | FastAPI; runs migrations on start (safe with several replicas); streams live updates |
| worker | Background jobs from the Postgres queue (email, push, cleanup) |
| db | PostgreSQL 16 |
| backup | On demand only (`ops` profile): encrypted backups and restores |

## Run locally

Needs Docker with Compose v2. Ports 80 (and 443) must be free, or set `HTTP_PORT`/`HTTPS_PORT`.

```bash
scripts/init-env.sh                      # builds the app image, writes .env with fresh secrets
docker compose up -d --build --wait
MAHLZEIT_PASSWORD='choose a long password' \
  docker compose exec -T -e MAHLZEIT_PASSWORD app \
  mahlzeit create-admin --email you@example.org --name Jonas --household Zuhause
```

Open http://localhost, sign in, go to **Household** and create an invitation for your partner.
`http://localhost` counts as a secure origin, so the service worker, installation and push work in
a desktop browser on the same machine. Phones need the HTTPS deployment below.

Then set your targets under **Settings → Targets and day types**. The first admin starts with
about 30 staple foods as favourites; everything else is found by search or barcode.

Further households (other couples): `docker compose exec app mahlzeit invite-household`
prints a link and a code that start a new household.

## Deploy to a server (one step once DNS points at it)

Requirements: any machine with Docker, a public DNS name pointing at it, ports 80 and 443 open,
outbound HTTPS. 2 vCPU / 4 GB RAM is comfortable.

```bash
git clone <repo> mahlzeit && cd mahlzeit
scripts/init-env.sh mahlzeit.example.org   # sets SITE_ADDRESS and BASE_URL=https://...
# optional in .env: SMTP_*, VAPID_SUBJECT, BACKUP_AGE_RECIPIENT (see Backups)
docker compose up -d --build --wait
```

Caddy obtains and renews the certificate itself. Then create the admin as above and open
`https://mahlzeit.example.org` on both phones in Chrome: menu, **Install app**.

Update to a new version:

```bash
git pull && docker compose up -d --build --wait
```

### Settings that matter

- `SITE_ADDRESS`: `http://localhost, http://127.0.0.1` (plain HTTP, local) or a bare domain
  (automatic HTTPS).
- `VAPID_SUBJECT`: optional contact for push services; defaults to `BASE_URL` when it is https.
- `BASE_URL`: the public URL; used in invite and reset links, cookies (`Secure` when https),
  push and the connector link.
- `OFF_CONTACT`: optional contact (e.g. `mailto:you@example.org`) that Open Food Facts sees in
  the User-Agent of barcode lookups; defaults to `BASE_URL`. `OFF_ENABLED=false` turns lookups
  off; unknown barcodes then go straight to the label form.
- `ENCRYPTION_KEY`: encrypts push subscriptions and, later, API keys. Losing it makes those
  unreadable; keep a copy with your backup key. The app refuses to start without a valid one.
- `SMTP_*`: optional. Without it, password resets use
  `docker compose exec -T -e MAHLZEIT_PASSWORD app mahlzeit reset-password --email ...`.
  Check it with `docker compose exec app mahlzeit send-test-email --to you@example.org`.

## Claude connector

Each person can let Claude read and log food for them. It needs the HTTPS deployment, because
Claude connects to the server from the internet.

1. In Mahlzeit: **Settings → Claude connector → Create link**. Copy the link; it is shown once.
2. In Claude (web or app): **Settings → Connectors → Add custom connector**. Paste the link as
   the server URL and name it, for example Mahlzeit. No other authentication is needed: the
   link itself is the secret.
3. In a chat, enable the connector and ask, for example, "Log 200 g skyr for breakfast" or
   "What do I have left today?".

**Create new link** replaces the old link (the old one stops working at once); **Turn off**
removes it. Anyone with the link can act as that person, so treat it like a password.
Locally (`http://localhost`) any MCP client can use the link, e.g. for testing.

## Backups

Create an age key pair **on your own computer** (not on the server) and keep the private part
safe, e.g. in your password manager:

```bash
age-keygen -o mahlzeit-backup-key.txt      # prints "Public key: age1..."
```

Put the public key into `.env` as `BACKUP_AGE_RECIPIENT`. Then:

```bash
scripts/backup.sh          # writes ./backups/mahlzeit-<UTC time>.tar.age, keeps the newest 14
```

Schedule it with cron on the host and copy `./backups` off the machine (they are encrypted, so any
storage will do):

```cron
17 3 * * * cd /opt/mahlzeit && scripts/backup.sh >> backups/backup.log 2>&1
```

A backup holds the database dump, the files volume and a short `meta.txt`. The file belongs to
the user who ran `scripts/backup.sh` (mode 600), so a non-root operator can copy it away.

### Restore

```bash
cp mahlzeit-20261006T031700Z.tar.age backups/
scripts/restore.sh backups/mahlzeit-20261006T031700Z.tar.age ~/mahlzeit-backup-key.txt
```

This stops app and worker, replaces the database and files, and starts everything again.

### Restore drill

`scripts/restore-drill.sh` proves the whole cycle without touching the running stack: it starts a
separate Compose project on port 8088, creates a user and a file, takes an encrypted backup with
a throwaway key, wipes all volumes, restores, and checks the login and the file. CI runs it on
every push.

## Move to another machine (e.g. on-prem)

1. On the old server: `scripts/backup.sh`.
2. On the new machine: clone the repository, copy `.env` (same `ENCRYPTION_KEY`!) and the backup.
3. `docker compose up -d --build --wait`, then `scripts/restore.sh backups/<file> <key>`.
4. Point DNS at the new machine. Caddy fetches a new certificate on the first request.

## Building behind a TLS-intercepting proxy

All Dockerfiles accept an optional build secret with an extra CA certificate:

```bash
docker build --secret id=build_ca,src=/path/to/proxy-ca.crt ...
```

Normal builds do not need it.
