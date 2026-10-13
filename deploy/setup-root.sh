#!/usr/bin/env bash
# One-time root setup on the server: linger, Cloudflare tunnel ingress, tailscale serve. Run: sudo INKA_FRAME_HOST=frame.example.com bash deploy/setup-root.sh
set -euo pipefail
HOST="${INKA_FRAME_HOST:?Set INKA_FRAME_HOST, e.g. sudo INKA_FRAME_HOST=frame.example.com bash deploy/setup-root.sh}"
CFG=/etc/cloudflared/config.yml

echo "== 1/3 linger for $SUDO_USER (service runs without a login session)"
loginctl enable-linger "$SUDO_USER"

echo "== 2/3 cloudflared: ingress $HOST → 127.0.0.1:8100 only for /api/v1/frame"
if grep -q "hostname: $HOST" "$CFG"; then
  echo "   ingress for $HOST already exists, skipping"
else
  cp -p "$CFG" "$CFG.bak-$(date +%Y%m%d-%H%M%S)"
  python3 - "$CFG" "$HOST" <<'PY'
import sys
path, host = sys.argv[1], sys.argv[2]
lines = open(path).read().splitlines(keepends=True)
idx = next(i for i, l in enumerate(lines) if l.strip() == "- service: http_status:404")
rule = (
    f"  - hostname: {host}\n"
    f"    path: ^/api/v1/frame$\n"
    f"    service: http://127.0.0.1:8100\n"
    f"  - hostname: {host}\n"
    f"    service: http_status:404\n"
)
lines.insert(idx, rule)
open(path, "w").write("".join(lines))
PY
fi
cloudflared tunnel ingress validate --config "$CFG"
TUNNEL=$(awk '/^tunnel:/{print $2}' "$CFG")
cloudflared tunnel route dns "$TUNNEL" "$HOST" || echo "   DNS record may already exist"
systemctl restart cloudflared
sleep 3
systemctl is-active cloudflared

echo "== 3/3 tailscale serve: https://<tailnet hostname>/ → 127.0.0.1:8100 (tailnet only)"
tailscale serve --bg --https=443 http://127.0.0.1:8100
tailscale serve status
echo "Done."
