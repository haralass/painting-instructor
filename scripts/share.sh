#!/bin/bash
# Start everything needed to share Painting Instructor with friends:
# Redis check, API, Celery worker, frontend, and the Cloudflare tunnel.
#
#   ./scripts/share.sh                 # read config from deploy/cloudflared/.env
#   PUBLIC_DOMAIN=paint.example.com ./scripts/share.sh
#
# Stop everything with Ctrl+C. First-time setup (Cloudflare account, tunnel,
# Access policy) is in docs/SHARING.md — this script assumes it is done.

set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv/bin"
ENV_FILE="deploy/cloudflared/.env"

# ── Configuration ────────────────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi

if [ -z "${PUBLIC_DOMAIN:-}" ]; then
  cat >&2 <<'MSG'
PUBLIC_DOMAIN is not set.

Create deploy/cloudflared/.env with your hostname:

    PUBLIC_DOMAIN=paint.example.com
    TUNNEL_NAME=painting-instructor

Full walkthrough: docs/SHARING.md
MSG
  exit 1
fi

TUNNEL_NAME="${TUNNEL_NAME:-painting-instructor}"
API_DOMAIN="api.${PUBLIC_DOMAIN}"

# ── Preflight ────────────────────────────────────────────────────────────────
if [ ! -x "$VENV/python" ]; then
  echo "No .venv — run ./scripts/dev.sh once to create it." >&2; exit 1
fi
if ! redis-cli ping >/dev/null 2>&1; then
  echo "Redis is not running.  brew services start redis" >&2; exit 1
fi
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed.  brew install cloudflared" >&2; exit 1
fi
if ! cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
  echo "No tunnel named '$TUNNEL_NAME'. See docs/SHARING.md (step 3)." >&2; exit 1
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

# The browser talks to the API on its own hostname; the API must allow the
# frontend's origin. CORS_ORIGINS is additive, so localhost keeps working.
export CORS_ORIGINS="https://${PUBLIC_DOMAIN}"
export NEXT_PUBLIC_API_URL="https://${API_DOMAIN}"

echo "Sharing as https://${PUBLIC_DOMAIN}  (API: https://${API_DOMAIN})"

pids=()
cleanup() {
  echo ""
  echo "Stopping…"
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

$VENV/python -m uvicorn backend.api.main:app --port 8000 &
pids+=($!)

$VENV/python -m celery -A backend.workers.tasks worker --loglevel=warning --concurrency=1 &
pids+=($!)

# Production build: `next dev` is slower and rebuilds on every request, which
# is miserable over a tunnel.
(cd frontend && npm run build && npm run start -- --port 3000) &
pids+=($!)

# Give the origins a moment before the tunnel starts routing traffic at them.
sleep 12

cloudflared tunnel --config deploy/cloudflared/config.yml run "$TUNNEL_NAME" &
pids+=($!)

cat <<MSG

──────────────────────────────────────────────
  Painting Instructor is live:
    https://${PUBLIC_DOMAIN}

  Your friends need the Access password you set
  in the Cloudflare dashboard (docs/SHARING.md).

  This Mac must stay awake and online.
  Stop everything with Ctrl+C.
──────────────────────────────────────────────
MSG

wait
