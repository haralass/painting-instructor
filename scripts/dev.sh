#!/bin/bash
# Start the full Painting Instructor stack for local development.
# Usage: ./scripts/dev.sh          (from the repo root)
# Stop:  Ctrl+C (kills all three processes)

set -e
cd "$(dirname "$0")/.."

VENV=".venv/bin"
if [ ! -x "$VENV/python" ]; then
  echo "No .venv found — creating it and installing backend deps..."
  python3 -m venv .venv
  $VENV/pip install -r requirements.txt -r requirements-dev.txt
fi

if ! redis-cli ping >/dev/null 2>&1; then
  echo "⚠️  Redis is not running. Start it with:  brew services start redis"
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend deps..."
  (cd frontend && npm install)
fi

echo "Starting backend API (http://localhost:8000)..."
$VENV/python -m uvicorn backend.api.main:app --port 8000 --reload &
API_PID=$!

echo "Starting Celery worker..."
$VENV/python -m celery -A backend.workers.tasks worker --loglevel=info --concurrency=1 &
WORKER_PID=$!

echo "Starting frontend (http://localhost:3000)..."
(cd frontend && npm run dev) &
FRONT_PID=$!

trap "kill $API_PID $WORKER_PID $FRONT_PID 2>/dev/null" EXIT

echo ""
echo "──────────────────────────────────────────────"
echo "  Painting Instructor is running:"
echo "  →  http://localhost:3000"
echo "  Stop everything with Ctrl+C"
echo "──────────────────────────────────────────────"
wait
