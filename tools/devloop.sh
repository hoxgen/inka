#!/usr/bin/env bash
# Build + flash + čekání na refresh + snímek kamerou.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:-devloop}"
source "$ROOT/tools/env.sh"
cd "$ROOT/firmware"
idf.py build
PORT="$(PYTHONPATH="$ROOT/tools" python3 -c 'from serial.tools import list_ports; import serial_wait; print(serial_wait.find_port(list_ports.comports()) or "")')"
if [[ -z "$PORT" ]]; then
  echo "Port ESP32 nenalezen. Je rámeček zapnutý a připojený?" >&2
  exit 1
fi
idf.py -p "$PORT" flash
python3 "$ROOT/tools/serial_wait.py" --timeout 200 \
  --fail "inka: display failed" --fail "inka: not provisioned" --fail "inka: fb alloc failed" \
  "${INKA_WAIT:-inka: refresh done}"
sleep 2
"$ROOT/tools/snap.sh" "$NAME"
