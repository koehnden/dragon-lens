# Hetzner Demo Deployment

Single-VM deployment for the read-only DragonLens demo at `demo.dragon-lens.ai`.

## Stack

| Component  | Role                          |
|------------|-------------------------------|
| Caddy      | Reverse proxy, auto-TLS       |
| FastAPI    | API server (port 8000)        |
| Streamlit  | UI (port 8501)                |
| PostgreSQL | Single database for both demo and knowledge data |

Not running on the VM: Redis, Celery, Ollama, sentiment microservice.

## Prerequisites

- Hetzner account with billing enabled
- DNS access for `demo.dragon-lens.ai`
- SSH public key
- Local secret file copied from `ops/dragonlens-hetzner-env.example`
- Deploy key or GitHub token if repo is private

## 1. Provision VM

Create a CX23 (2 vCPU, 4 GB RAM, x86) in Hetzner Cloud:
- Image: Ubuntu 24.04
- Region: nbg1 (or any EU region)
- Add your SSH key
- Firewall: allow inbound TCP 22, 80, 443 only

## 2. DNS

Create an A record pointing `demo.dragon-lens.ai` to the VM's public IP.

## 3. Bootstrap

Prepare the local secret file first:

```bash
cp ops/dragonlens-hetzner-env.example ops/dragonlens-hetzner-env
```

Fill in:
- `DB_PASSWORD`
- `DATABASE_URL`
- `KNOWLEDGE_DATABASE_URL`
- `ADMIN_API_TOKEN`
- `KNOWLEDGE_SYNC_TOKEN`
- `DEMO_PUBLISH_TOKEN`
- `ENCRYPTION_SECRET_KEY`

Before pushing anything, verify the real env file stays local:

```bash
git status --short
git check-ignore -v ops/dragonlens-hetzner-env
```

`ops/dragonlens-hetzner-env` must not appear in `git status`.

Then bootstrap the VM from your local machine:

```bash
source ops/dragonlens-hetzner-env
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 \
  "curl -fsSL https://raw.githubusercontent.com/koehnden/dragon-lens/main/ops/hetzner/bootstrap.sh | bash -s -- https://github.com/koehnden/dragon-lens.git \"$DB_PASSWORD\" main"
```

This installs the system Python 3 runtime for Ubuntu 24.04, PostgreSQL, Caddy, creates the `dragonlens` system user, creates the DB, installs the app, and enables the services without starting the app before the env file exists.

## 4. Config

Upload your local untracked env file:

```bash
scp -i ~/.ssh/dragonlens_hetzner ops/dragonlens-hetzner-env root@157.90.175.0:/opt/dragonlens/.env
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 \
  "chown dragonlens:dragonlens /opt/dragonlens/.env && chmod 600 /opt/dragonlens/.env"
```

Run migrations and start the app services:

```bash
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 \
  "/opt/dragonlens/ops/hetzner/migrate.sh && systemctl start dragonlens-api dragonlens-streamlit caddy"
```

## 5. Verify

```bash
curl -sf https://demo.dragon-lens.ai/health
```

Check that:
- Public pages load
- Mutation routes return 403 in demo mode
- Admin sync works with bearer token
- PostgreSQL listens only on localhost: `ss -tlnp | grep 5432`

## 6. Deploy updates

```bash
sudo /opt/dragonlens/ops/hetzner/deploy.sh
```

This tags the current state, pulls latest main, installs deps, restarts services, and runs a health check.

## 7. Rollback

```bash
sudo /opt/dragonlens/ops/hetzner/rollback.sh <git-tag>
```

List available tags with `git tag -l 'pre-deploy-*'`.

## 8. Backups

Automated daily at 03:00 via systemd timer. Dumps go to `/var/backups/dragonlens/`, 7-day retention.

Manual backup:

```bash
sudo /opt/dragonlens/ops/hetzner/backup.sh
```

Restore:

```bash
gunzip -c /var/backups/dragonlens/<dump>.sql.gz | sudo -u postgres psql dragonlens
```

## 9. Monitoring

Set up an external health ping (e.g. healthchecks.io free tier) hitting `https://demo.dragon-lens.ai/health` every 5 minutes with alerts on missed pings.

View service logs:

```bash
journalctl -u dragonlens-api -f
journalctl -u dragonlens-streamlit -f
```

## 10. Local admin workflow

From your local machine:

```bash
# Sync knowledge for a vertical
poetry run python scripts/sync_knowledge_vertical.py "Electric Cars" \
  --url https://demo.dragon-lens.ai/api/v1/admin/knowledge-sync \
  --token <KNOWLEDGE_SYNC_TOKEN>

# Publish a demo snapshot
poetry run python scripts/publish_demo_vertical.py --vertical-name "Electric Cars" \
  --url https://demo.dragon-lens.ai/api/v1/admin/demo-publish \
  --token <DEMO_PUBLISH_TOKEN>
```
