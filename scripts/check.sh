#!/usr/bin/env bash
# The single gate a checkpoint must pass. Exits nonzero on any failure.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== stdlib baseline (always runs, zero deps) =="
python3 tests/test_contracts.py

if python3 -m pytest --version >/dev/null 2>&1; then
  echo "== pytest suite =="
  python3 -m pytest -q tests/
else
  echo "== pytest not installed — skipping full suite (finish ticket 0.2) =="
fi

if python3 -m ruff --version >/dev/null 2>&1; then
  echo "== ruff lint =="
  python3 -m ruff check src tests
else
  echo "== ruff not installed — skipping lint (finish ticket 0.2) =="
fi

echo "OK"
