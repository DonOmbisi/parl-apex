#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

if [ -n "${TAILSCALE_AUTH_KEY:-}" ]; then
  if command -v tailscaled >/dev/null 2>&1; then
    tailscaled --state=/data/tailscaled.state --socket=/tmp/tailscaled.sock >/tmp/tailscaled.log 2>&1 &
    sleep 2
    tailscale --socket=/tmp/tailscaled.sock up --authkey "${TAILSCALE_AUTH_KEY}" --hostname parl-apex-render &
  else
    tailscale up --authkey "${TAILSCALE_AUTH_KEY}" --hostname parl-apex-render &
  fi
  sleep 5
else
  echo "TAILSCALE_AUTH_KEY is not set; starting without Tailscale."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
