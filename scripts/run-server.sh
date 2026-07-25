#!/usr/bin/env bash
# Run the EDOS API server: bring up Postgres, ensure the schema, launch uvicorn.
# Usage:  ./scripts/run-server.sh            (foreground)
#         run inside tmux on a headless box so it survives your SSH session.
set -euo pipefail
cd "$(dirname "$0")/.."

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://edos:edos@localhost:5432/edos}"
PY="${PY:-.venv/bin/python}"

echo "== Postgres (pgvector) =="
docker compose up -d postgres
until [ "$(docker inspect -f '{{.State.Health.Status}}' edos-postgres 2>/dev/null)" = "healthy" ]; do
  sleep 1
done
echo "postgres healthy"

echo "== schema =="
"$PY" scripts/db/bootstrap.py    # idempotent: safe to re-run

echo "== server on :8000  (UI: /app · docs: /docs) =="
exec "$PY" -m uvicorn edos.api.app:app --app-dir src --host 0.0.0.0 --port 8000
