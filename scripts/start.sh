#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

echo "===== STARTUP ====="

# Install Tailscale if needed
if ! command -v tailscale >/dev/null 2>&1; then
    echo "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if [ -n "${TAILSCALE_AUTH_KEY:-}" ]; then

    TAILSCALED_BIN="$(command -v tailscaled || true)"

    if [ -z "$TAILSCALED_BIN" ] && [ -x /usr/sbin/tailscaled ]; then
        TAILSCALED_BIN="/usr/sbin/tailscaled"
    fi

    if [ -z "$TAILSCALED_BIN" ]; then
        echo "ERROR: tailscaled binary not found!"
        exit 1
    fi

    echo "Using tailscaled: $TAILSCALED_BIN"
    echo "Auth key prefix: ${TAILSCALE_AUTH_KEY:0:20}..."

    echo "Starting tailscaled..."

    "$TAILSCALED_BIN" \
        --tun=userspace-networking \
        --state=/tmp/tailscaled.state \
        --socket=/tmp/tailscaled.sock \
        >/tmp/tailscaled.log 2>&1 &

    sleep 5

    echo "Running tailscale up..."

    set +e

    tailscale \
        --socket=/tmp/tailscaled.sock \
        up \
        --authkey="${TAILSCALE_AUTH_KEY}" \
        --hostname="parl-apex-render" \
        --accept-routes=false

    TS_EXIT=$?

    echo
    echo "===== tailscale up exit code: $TS_EXIT ====="
    echo

    echo "===== tailscale status ====="
    tailscale --socket=/tmp/tailscaled.sock status || true

    echo
    echo "===== tailscale ip ====="
    tailscale --socket=/tmp/tailscaled.sock ip || true

    echo
    echo "===== tailscaled log ====="
    cat /tmp/tailscaled.log || true

    echo "==========================="

    set -e

else
    echo "WARNING: TAILSCALE_AUTH_KEY is not set."
fi

echo
echo "===== STARTING FASTAPI ====="

exec uv run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}"