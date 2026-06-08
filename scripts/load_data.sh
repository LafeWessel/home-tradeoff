#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "backend/.venv" ]]; then
  echo "backend/.venv missing — run: cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
  exit 1
fi

cd backend
source .venv/bin/activate
exec python -m scripts.load_all "$@"
