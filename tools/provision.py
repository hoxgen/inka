#!/usr/bin/env python3
"""Zapíše konfiguraci rámečku (Wi-Fi, server, token) do NVS oddílu. Hodnoty nevypisuje."""
import argparse
import csv
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NVS_OFFSET = "0x9000"
NVS_SIZE = "0x6000"
FIELDS = [
    ("wifi_ssid", "INKA_WIFI_SSID"),
    ("wifi_pass", "INKA_WIFI_PASS"),
    ("server_url", "INKA_SERVER_URL"),
    ("device_token", "INKA_DEVICE_TOKEN"),
]


def parse_env(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value
    return values


# Maximální délka v bajtech UTF-8 (velikost polí v firmware/components/config/include/config.h bez NUL).
MAX_BYTES = {"INKA_WIFI_SSID": 32, "INKA_WIFI_PASS": 64, "INKA_SERVER_URL": 127, "INKA_DEVICE_TOKEN": 64}


def normalize(values: dict[str, str]) -> dict[str, str]:
    # SSID a heslo zůstávají beze změny; mezery v nich mohou být platné.
    out = dict(values)
    if "INKA_SERVER_URL" in out:
        out["INKA_SERVER_URL"] = out["INKA_SERVER_URL"].strip().rstrip("/")
    if "INKA_DEVICE_TOKEN" in out:
        out["INKA_DEVICE_TOKEN"] = out["INKA_DEVICE_TOKEN"].strip()
    return out


def build_csv(values: dict[str, str]) -> str:
    values = normalize(values)
    missing = [env for _, env in FIELDS if not values.get(env)]
    if missing:
        raise ValueError(f"missing values: {', '.join(missing)}")
    too_long = [env for env, limit in MAX_BYTES.items() if len(values[env].encode("utf-8")) > limit]
    if too_long:
        raise ValueError(f"too long: {', '.join(f'{e} (max {MAX_BYTES[e]} B)' for e in too_long)}")
    if not values["INKA_SERVER_URL"].startswith(("http://", "https://")):
        raise ValueError("INKA_SERVER_URL must start with http:// or https://")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["key", "type", "encoding", "value"])
    w.writerow(["inka", "namespace", "", ""])
    for key, env in FIELDS:
        w.writerow([key, "data", "string", values[env]])
    return out.getvalue()


def main() -> int:
    from serial.tools import list_ports

    sys.path.insert(0, str(ROOT / "tools"))
    import serial_wait

    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(ROOT / "firmware" / "provision.local.env"))
    ap.add_argument("--port")
    args = ap.parse_args()

    try:
        csv_text = build_csv(parse_env(Path(args.env).read_text()))
    except (OSError, ValueError) as exc:
        print(f"provision: {exc}", file=sys.stderr)
        return 1

    port = args.port or serial_wait.find_port(list_ports.comports())
    if not port:
        print("provision: port ESP32 nenalezen", file=sys.stderr)
        return 1

    gen = Path(os.environ["IDF_PATH"]) / "components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py"
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "nvs.csv"
        bin_path = Path(tmp) / "nvs.bin"
        csv_path.write_text(csv_text)
        subprocess.run(
            [sys.executable, str(gen), "generate", str(csv_path), str(bin_path), NVS_SIZE],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "esptool", "--port", port, "write_flash", NVS_OFFSET, str(bin_path)],
            check=True,
        )
    print(f"provision: NVS zapsáno na {port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
