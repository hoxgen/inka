#!/usr/bin/env bash
# Deploys server/ to a Linux host as a systemd user service (no sudo). Usage: INKA_HOST=user@host tools/deploy.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${INKA_HOST:?Set INKA_HOST, e.g. INKA_HOST=user@host tools/deploy.sh}"
cd "$ROOT/server"
uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/inka-requirements.txt >/dev/null
rsync -az --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache \
  "$ROOT/server/" "$HOST:apps/inka/server/"
scp -q /tmp/inka-requirements.txt "$HOST:apps/inka/server/requirements.txt"
scp -q "$ROOT/deploy/inka.service" "$HOST:.config/systemd/user/inka.service"
ssh "$HOST" 'set -e
  cd ~/apps/inka/server
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  .venv/bin/pip install -q --no-deps .
  test -f ~/.config/inka/env || { echo "missing ~/.config/inka/env"; exit 1; }
  systemctl --user daemon-reload
  systemctl --user enable -q inka
  systemctl --user restart inka
  systemctl --user is-active inka
  for i in $(seq 1 20); do curl -s -o /dev/null http://127.0.0.1:8100/ && break; sleep 1; done  # startup takes ~3 s
  curl -s -o /dev/null -w "local: %{http_code}\n" http://127.0.0.1:8100/'
