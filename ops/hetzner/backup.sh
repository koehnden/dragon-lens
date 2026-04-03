#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/dragonlens"
DB_NAME="dragonlens"
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

FILENAME="$BACKUP_DIR/${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql.gz"
sudo -u postgres pg_dump "$DB_NAME" | gzip > "$FILENAME"

find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup created: $FILENAME"
