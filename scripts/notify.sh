#!/usr/bin/env bash
# EDOS build notifier. Prefers Telegram if creds are present, else falls back to ntfy.
# Never fatal — a failed notification must never block the build.
#   usage: scripts/notify.sh "message text" [title]
set -u
MSG="${1:-EDOS build update}"
TITLE="${2:-EDOS}"

# Load .env if present (for TELEGRAM_* / NTFY_TOPIC) without clobbering existing env.
if [ -f "$(dirname "$0")/../.env" ]; then
  set -a; . "$(dirname "$0")/../.env" 2>/dev/null || true; set +a
fi

NTFY_TOPIC="${NTFY_TOPIC:-edos-dws-build-notify}"

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=[${TITLE}] ${MSG}" >/dev/null 2>&1 || true
else
  curl -s -H "Title: ${TITLE}" -d "${MSG}" "https://ntfy.sh/${NTFY_TOPIC}" >/dev/null 2>&1 || true
fi
