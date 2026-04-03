#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/dragonlens"

if [ ! -f "${APP_DIR}/.env" ]; then
    echo "Missing ${APP_DIR}/.env"
    exit 1
fi

cd "$APP_DIR"
set -a
. "${APP_DIR}/.env"
set +a

PYTHONPATH="${APP_DIR}/src" "${APP_DIR}/.venv/bin/python" - <<'PY'
from models.database import init_db
from models.knowledge_database import init_knowledge_db

init_db()
init_knowledge_db()
PY
