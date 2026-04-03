#!/usr/bin/env bash
set -euo pipefail

APP_USER="dragonlens"
APP_DIR="/opt/dragonlens"
PG_DB="dragonlens"
PG_USER="dragonlens"
REPO_URL="${1:?Usage: bootstrap.sh <repo-url> <pg-password> [git-ref] }"
PG_PASS="${2:?Usage: bootstrap.sh <repo-url> <pg-password> [git-ref] }"
REPO_REF="${3:-main}"
POETRY_BIN="/home/${APP_USER}/.local/bin/poetry"
PG_CONF_DIR="/etc/postgresql/16/main/conf.d"

apt-get update
apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    postgresql postgresql-contrib \
    caddy \
    git curl

useradd --system --create-home --shell /bin/bash "$APP_USER" || true

runuser -u postgres -- psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER'" \
    | grep -q 1 \
    || runuser -u postgres -- psql -c "CREATE USER $PG_USER WITH PASSWORD '$PG_PASS';"
runuser -u postgres -- psql -tc "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" \
    | grep -q 1 \
    || runuser -u postgres -- createdb -O "$PG_USER" "$PG_DB"

mkdir -p "$PG_CONF_DIR"
cat > "${PG_CONF_DIR}/dragonlens.conf" <<'PGCONF'
listen_addresses = 'localhost'
shared_buffers = 256MB
PGCONF
systemctl restart postgresql

install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
if [ -d "${APP_DIR}/.git" ]; then
    runuser -u "$APP_USER" -- git -C "$APP_DIR" fetch origin "$REPO_REF"
    runuser -u "$APP_USER" -- git -C "$APP_DIR" checkout "$REPO_REF"
    runuser -u "$APP_USER" -- git -C "$APP_DIR" pull --ff-only origin "$REPO_REF"
else
    runuser -u "$APP_USER" -- git clone --branch "$REPO_REF" --single-branch "$REPO_URL" "$APP_DIR"
fi

runuser -u "$APP_USER" -- bash -lc "
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    python3.11 -m pip install --user --upgrade pip poetry
    cd \"$APP_DIR\"
    POETRY_VIRTUALENVS_IN_PROJECT=true \"$POETRY_BIN\" env use python3.11
    POETRY_VIRTUALENVS_IN_PROJECT=true \"$POETRY_BIN\" install --no-root --only main
"

cp "$APP_DIR/ops/hetzner/Caddyfile" /etc/caddy/Caddyfile
cp "$APP_DIR/ops/hetzner/dragonlens-api.service" /etc/systemd/system/
cp "$APP_DIR/ops/hetzner/dragonlens-streamlit.service" /etc/systemd/system/
cp "$APP_DIR/ops/hetzner/dragonlens-backup.service" /etc/systemd/system/
cp "$APP_DIR/ops/hetzner/dragonlens-backup.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable caddy
systemctl enable dragonlens-api
systemctl enable dragonlens-streamlit
systemctl enable dragonlens-backup.timer
systemctl start caddy
systemctl start dragonlens-backup.timer

echo "Bootstrap complete."
echo "Next steps:"
echo "  1. Copy /opt/dragonlens/.env"
echo "  2. Run /opt/dragonlens/ops/hetzner/migrate.sh"
echo "  3. Start dragonlens-api and dragonlens-streamlit"
