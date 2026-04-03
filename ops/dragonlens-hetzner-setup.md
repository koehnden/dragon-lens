# Dragon Lens — Hetzner Server Setup

## Server Details

| Field         | Value                              |
|---------------|------------------------------------|
| Name          | dragonlens-demo                    |
| Type          | CX23 (2 vCPU, 4 GB RAM, 40 GB SSD)|
| Location      | Nuremberg, Germany (eu-central)    |
| Public IPv4   | 157.90.175.0                       |
| OS            | Ubuntu 24.04                       |
| Firewall      | dragonlens-fw (SSH 22, HTTP 80, HTTPS 443, ICMP) |
| SSH Key       | dragonlens-hetzner                 |
| Backups       | Disabled (pg_dump only)            |
| Monthly Cost  | €5.34 (€4.75 server + €0.60 IPv4) |

---

## Step 1: DNS — Point demo.dragon-lens.ai to the server

Create an **A record** in your DNS provider for:

    demo.dragon-lens.ai  →  157.90.175.0

(If you also want IPv6, add an AAAA record with the server's IPv6 address from the Hetzner console.)

---

## Step 2: SSH into the server

```bash
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0
```

---

## Step 3: Run the bootstrap script

```bash
source ops/dragonlens-hetzner-env
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 \
  "curl -fsSL https://raw.githubusercontent.com/koehnden/dragon-lens/main/ops/hetzner/bootstrap.sh | bash -s -- https://github.com/koehnden/dragon-lens.git \"$DB_PASSWORD\" main"
```

---

## Step 4: Copy the .env file to the server

From your local machine:

```bash
scp -i ~/.ssh/dragonlens_hetzner ops/dragonlens-hetzner-env root@157.90.175.0:/opt/dragonlens/.env
```

Then on the server, set ownership:

```bash
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "chown dragonlens:dragonlens /opt/dragonlens/.env && chmod 600 /opt/dragonlens/.env"
```

---

## Step 5: Run migrations and start services

```bash
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 \
  "/opt/dragonlens/ops/hetzner/migrate.sh && systemctl start dragonlens-api dragonlens-streamlit caddy"
```

---

## Secrets

Keep the real values only in the ignored local file:

`ops/dragonlens-hetzner-env`

Use `ops/dragonlens-hetzner-env.example` as the tracked template.

---

## Useful commands

```bash
# Check service status
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "systemctl status dragonlens-api dragonlens-streamlit caddy"

# View API logs
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "journalctl -u dragonlens-api -f"

# View Streamlit logs
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "journalctl -u dragonlens-streamlit -f"

# Deploy updates
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "bash /opt/dragonlens/ops/hetzner/deploy.sh"

# Manual backup
ssh -i ~/.ssh/dragonlens_hetzner root@157.90.175.0 "bash /opt/dragonlens/ops/hetzner/backup.sh"
```
