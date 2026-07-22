#!/usr/bin/env bash
# The single gate a checkpoint must pass. Exits nonzero on any failure.
set -euo pipefail
cd "$(dirname "$0")/.."

# Prefer the project venv locally; fall back to system python (e.g. CI runners).
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY="python3"; fi
echo "using: $($PY --version) at $PY"

echo "== stdlib baseline (always runs, zero deps) =="
$PY tests/test_contracts.py

if $PY -m pytest --version >/dev/null 2>&1; then
  echo "== pytest suite =="
  $PY -m pytest -q tests/
else
  echo "== pytest not installed — skipping full suite (finish ticket 0.2) =="
fi

if $PY -m ruff --version >/dev/null 2>&1; then
  echo "== ruff lint =="
  $PY -m ruff check src tests
else
  echo "== ruff not installed — skipping lint (finish ticket 0.2) =="
fi

echo "OK"
