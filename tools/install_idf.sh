#!/usr/bin/env bash
# Instaluje ESP-IDF ve verzi z firmware/.idf-version do ~/esp/<verze>/esp-idf.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(tr -d '[:space:]' < "$ROOT/firmware/.idf-version")"
DEST="$HOME/esp/$VER/esp-idf"

if [[ "$(uname)" == "Darwin" ]]; then
  brew install cmake ninja dfu-util ccache
else
  sudo apt-get install -y git wget flex bison gperf python3 python3-pip python3-venv \
    cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
fi

if [[ ! -d "$DEST" ]]; then
  mkdir -p "$(dirname "$DEST")"
  git clone -b "$VER" --recursive --depth 1 --shallow-submodules \
    https://github.com/espressif/esp-idf.git "$DEST"
fi
"$DEST/install.sh" esp32s3
echo "ESP-IDF $VER nainstalováno v $DEST"
