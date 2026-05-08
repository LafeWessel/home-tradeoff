#!/usr/bin/env bash
# Run backend + frontend in parallel for local development.
# Cleans up both processes on Ctrl+C.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "backend/.venv" ]]; then
  echo "backend/.venv missing — run: cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
  exit 1
fi
if [[ ! -d "frontend/node_modules" ]]; then
  echo "frontend/node_modules missing — run: cd frontend && npm install"
  exit 1
fi

cleanup() {
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd backend
  source .venv/bin/activate
  exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
) &
BACKEND_PID=$!

(
  cd frontend
  exec npm run dev
) &
FRONTEND_PID=$!

echo "▸ backend   pid $BACKEND_PID  http://127.0.0.1:8765/docs"
echo "▸ frontend  pid $FRONTEND_PID  http://127.0.0.1:5173"
echo "(Ctrl+C to stop both)"
wait
