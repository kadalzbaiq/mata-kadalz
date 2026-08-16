#!/usr/bin/env bash
# Install the mata-kadalz MCP server into a local venv.
# Installs ONLY this package. llama-server and the model are external
# dependencies — install them separately per docs/SETUP-*.md.
# Usage: ./scripts/install.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install it first (e.g. sudo apt install python3 python3-venv)."
  exit 1
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

mkdir -p runtime/vision/cache
echo "mata-kadalz installed."
echo "Check llama-server reachability:  .venv/bin/mata-kadalz --health"
echo "Run stdio:                        .venv/bin/mata-kadalz"
echo "Run http:                         .venv/bin/mata-kadalz --transport http --host 127.0.0.1 --port 9932"
echo "Self-check: echo '{\"image_path\":\"<img>\",\"task\":\"<task>\"}' | .venv/bin/mata-kadalz --once"