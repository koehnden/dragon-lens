#!/usr/bin/env bash
set -euo pipefail

APP_USER="dragonlens"
APP_DIR="/opt/dragonlens"
TAG="${1:?Usage: rollback.sh <git-tag>}"
HEALTH_URL="http://127.0.0.1:8000/health"
POETRY_BIN="/home/${APP_USER}/.local/bin/poetry"

if [ "${EUID}" -ne 0 ]; then
    echo "Run rollback.sh as root."
    exit 1
fi

run_as_app() {
    runuser -u "$APP_USER" -- bash -lc "$1"
}

run_as_app "
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    cd \"$APP_DIR\"
    git checkout \"$TAG\"
    POETRY_VIRTUALENVS_IN_PROJECT=true \"$POETRY_BIN\" install --no-root --only main
"

"${APP_DIR}/ops/hetzner/migrate.sh"
systemctl restart dragonlens-api dragonlens-streamlit

sleep 3
if curl -sf "$HEALTH_URL" > /dev/null; then
    echo "Rolled back to $TAG and health check passed."
else
    echo "Rollback completed, but health check failed."
    exit 1
fi
