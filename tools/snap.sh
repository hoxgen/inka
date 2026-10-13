#!/usr/bin/env bash
# Pořídí snímek rámečku. Kamera: INKA_CAM (index avfoundation na macOS, /dev/videoN na Linuxu).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:-snap}"
OUT="$ROOT/debug/captures/$(date +%Y%m%d-%H%M%S)-$NAME.jpg"
mkdir -p "$(dirname "$OUT")"
if [[ "$(uname)" == "Darwin" ]]; then
  # 1 s náběh, aby se ustálila automatická expozice
  ffmpeg -hide_banner -loglevel error -f avfoundation -framerate 30 \
    -i "${INKA_CAM:-0}:none" -ss 1 -frames:v 1 -q:v 2 "$OUT"
else
  ffmpeg -hide_banner -loglevel error -f v4l2 -i "${INKA_CAM:-/dev/video0}" \
    -ss 1 -frames:v 1 -q:v 2 "$OUT"
fi
echo "$OUT"
