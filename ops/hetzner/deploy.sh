#!/usr/bin/env bash
set -euo pipefail

APP_USER="dragonlens"
APP_DIR="/opt/dragonlens"
DEPLOY_GIT_REF="main"
HEALTH_URL="http://127.0.0.1:8000/health"
POETRY_BIN="/home/${APP_USER}/.local/bin/poetry"

if [ "${EUID}" -ne 0 ]; then
    echo "Run deploy.sh as root."
    exit 1
fi

run_as_app() {
    runuser -u "$APP_USER" -- bash -lc "$1"
}

run_as_app "
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    cd \"$APP_DIR\"
    git tag \"pre-deploy-\$(date +%Y%m%d-%H%M%S)\"
    git fetch origin \"$DEPLOY_GIT_REF\"
    git checkout \"$DEPLOY_GIT_REF\"
    git pull --ff-only origin \"$DEPLOY_GIT_REF\"
    POETRY_VIRTUALENVS_IN_PROJECT=true \"$POETRY_BIN\" install --no-root --only main
"

"${APP_DIR}/ops/hetzner/migrate.sh"

systemctl restart dragonlens-api dragonlens-streamlit

sleep 3
if curl -sf "$HEALTH_URL" > /dev/null; then
    echo "Deploy successful — health check passed."
else
    echo "DEPLOY FAILED — health check failed. Consider rolling back."
    exit 1
fi
