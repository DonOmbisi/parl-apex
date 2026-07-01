#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

if [ -n "${TAILSCALE_AUTH_KEY:-}" ]; then
  TAILSCALED_BIN="$(command -v tailscaled || true)"
  if [ -z "${TAILSCALED_BIN}" ] && [ -x /usr/sbin/tailscaled ]; then
    TAILSCALED_BIN="/usr/sbin/tailscaled"
  fi

  if [ -n "${TAILSCALED_BIN}" ]; then
    "${TAILSCALED_BIN}" --state=/data/tailscaled.state --socket=/tmp/tailscaled.sock >/tmp/tailscaled.log 2>&1 &
    sleep 2
    tailscale --socket=/tmp/tailscaled.sock up --authkey "${TAILSCALE_AUTH_KEY}" --hostname parl-apex-render --accept-routes=false &
  else
    echo "tailscaled binary not found after installation; starting without Tailscale."
  fi
  sleep 5
else
  echo "TAILSCALE_AUTH_KEY is not set; starting without Tailscale."
fi

exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
