# Hetzner Setup Handoff — dragon-lens

## What was done

### 1. Firewall created: `dragonlens-fw`
- Inbound rules: TCP 22 (SSH), TCP 80 (HTTP), TCP 443 (HTTPS), ICMP
- All other inbound traffic is dropped
- No outbound restrictions
- Located in project "DragonLens" on Hetzner Console

### 2. SSH key uploaded: `dragonlens-hetzner`
- Type: ed25519
- Public key: `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILdkm1H+yNApEnWiY+nZ99j+N75uys3bNeG0RFFkmfRJ dragonlens-hetzner`
- Private key location on host: `~/.ssh/dragonlens_hetzner`

### 3. VM created: `dragonlens-demo`
- Type: CX23 (2 vCPU, 4 GB RAM, 40 GB SSD)
- OS: Ubuntu 24.04
- Location: Nuremberg, Germany (eu-central) — Falkenstein was unavailable
- Public IPv4: **157.90.175.0**
- Networking: IPv4 + IPv6
- Firewall: `dragonlens-fw` attached
- SSH key: `dragonlens-hetzner` attached
- Backups: disabled (relying on pg_dump via ops/hetzner/backup.sh)
- Cost: €5.34/mo (€4.75 server + €0.60 IPv4)

### 4. Secrets generated
Stored locally in the ignored file:

`/Users/denniskoehn/Documents/Git/src/dragon-lens-aws/ops/dragonlens-hetzner-env`

Use `ops/dragonlens-hetzner-env.example` as the tracked template.

Before pushing or merging, confirm the real env file stays ignored:

```bash
git status --short
git check-ignore -v ops/dragonlens-hetzner-env
```

---

## What still needs to happen

### A. DNS (manual — must be done before bootstrap)
Create an A record:
```
demo.dragon-lens.ai  →  157.90.175.0
```
Caddy auto-provisions HTTPS via Let's Encrypt and will fail if DNS doesn't resolve.

### B. Bootstrap the server
```bash
source ops/dragonlens-hetzner-env
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 \
  "curl -fsSL https://raw.githubusercontent.com/koehnden/dragon-lens/main/ops/hetzner/bootstrap.sh | bash -s -- https://github.com/koehnden/dragon-lens.git \"$DB_PASSWORD\" main"
```

Once on the server, the bootstrap script at `ops/hetzner/bootstrap.sh` will:
- Install Python 3.11, PostgreSQL 16, Caddy, git
- Create system user `dragonlens`
- Create PostgreSQL database and user from the passed password
- Clone the repo to `/opt/dragonlens`
- Install Poetry and create the in-project `.venv`
- Install systemd services: `dragonlens-api`, `dragonlens-streamlit`, `dragonlens-backup.timer`
- Copy Caddyfile to `/etc/caddy/Caddyfile`
- Enable Caddy and the backup timer without starting the app before `.env` exists

### C. Deploy the .env file
```bash
scp -i ~/.ssh/dragonlens_hetzner ops/dragonlens-hetzner-env root@157.90.175.0:/opt/dragonlens/.env
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "chown dragonlens:dragonlens /opt/dragonlens/.env && chmod 600 /opt/dragonlens/.env"
```

### D. Restart services
```bash
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "/opt/dragonlens/ops/hetzner/migrate.sh && systemctl start dragonlens-api dragonlens-streamlit caddy"
```

### E. Verify
- Health check: `curl https://demo.dragon-lens.ai/health`
- UI: open `https://demo.dragon-lens.ai` in browser
- API: `curl https://demo.dragon-lens.ai/api/...`

---

## Architecture reference

```
Internet → Caddy (ports 80/443, HTTPS termination)
             ├── /api/*    → FastAPI on localhost:8000
             ├── /health   → FastAPI on localhost:8000
             └── /*        → Streamlit on localhost:8501
                               └── PostgreSQL on localhost:5432
```

All services bind to localhost only. Caddy is the sole public-facing component.

Daily pg_dump backups run at 03:00 UTC with 7-day retention (via systemd timer).

---

## Deployment files reference
All deployment scripts are in `ops/hetzner/`:
- `bootstrap.sh` — initial server provisioning
- `migrate.sh` — explicit DB migrations/init after `.env` is in place
- `deploy.sh` — pull latest code, reinstall deps, restart, health check
- `rollback.sh` — revert to a git tag
- `backup.sh` — pg_dump with rotation
- `Caddyfile` — reverse proxy config
- `dragonlens-api.service` — FastAPI systemd unit
- `dragonlens-streamlit.service` — Streamlit systemd unit
- `dragonlens-backup.service` / `.timer` — scheduled backup
