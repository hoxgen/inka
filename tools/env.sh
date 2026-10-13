# Použití: source tools/env.sh
_INKA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
_INKA_VER="$(tr -d '[:space:]' < "$_INKA_ROOT/firmware/.idf-version")"
export IDF_PATH="$HOME/esp/$_INKA_VER/esp-idf"
# Hlavičky hostitelského SDK z profilu shellu rozbíjí křížový překlad pro ESP32.
unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH OBJC_INCLUDE_PATH SDKROOT
if [[ ! -f "$IDF_PATH/export.sh" ]]; then
  echo "ESP-IDF $_INKA_VER chybí. Spusť tools/install_idf.sh" >&2
  return 1 2>/dev/null || exit 1
fi
. "$IDF_PATH/export.sh" >/dev/null
_INKA_HAVE="$(idf.py --version | grep -oE 'v[0-9]+\.[0-9]+(\.[0-9]+)?')"
if [[ "$_INKA_HAVE" != "$_INKA_VER" ]]; then
  echo "Chyba: ESP-IDF $_INKA_HAVE, požadováno $_INKA_VER" >&2
  return 1 2>/dev/null || exit 1
fi
export INKA_ROOT="$_INKA_ROOT"
