#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${MYSQL_URL:-}" && ( -z "${MYSQL_HOST:-}" || -z "${MYSQL_DATABASE:-}" || -z "${MYSQL_USER:-}" ) ]]; then
  eval "$(
    python3 - <<'PY'
import os
import shlex
from urllib.parse import unquote, urlparse

url = urlparse(os.environ["MYSQL_URL"])
values = {
    "MYSQL_HOST": url.hostname or "127.0.0.1",
    "MYSQL_PORT": str(url.port or 3306),
    "MYSQL_DATABASE": url.path.lstrip("/"),
    "MYSQL_USER": unquote(url.username or ""),
    "MYSQL_PASSWORD": unquote(url.password or ""),
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
  )"
fi

if [[ -z "${MYSQL_HOST:-}" || -z "${MYSQL_DATABASE:-}" || -z "${MYSQL_USER:-}" ]]; then
  echo "MYSQL_HOST, MYSQL_DATABASE and MYSQL_USER are required" >&2
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/finvue-$STAMP.sql.gz"

MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_PWD="${MYSQL_PASSWORD:-}" mysqldump \
  --host="$MYSQL_HOST" \
  --port="$MYSQL_PORT" \
  --user="$MYSQL_USER" \
  --single-transaction \
  --routines \
  --triggers \
  --default-character-set=utf8mb4 \
  "$MYSQL_DATABASE" | gzip > "$OUT"

echo "$OUT"
