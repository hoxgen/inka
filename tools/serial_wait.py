#!/usr/bin/env python3
"""Čeká na řádek v sériovém logu rámečku."""
import argparse
import sys
import time

ESPRESSIF_VID = 0x303A


def find_port(ports):
    for p in ports:
        if getattr(p, "vid", None) == ESPRESSIF_VID:
            return p.device
    return None


def wait_for(lines, pattern, out, fail_patterns=()):
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        print(line, file=out, flush=True)
        if pattern in line:
            return True
        if any(f in line for f in fail_patterns):
            return False
    return None


def serial_lines(port, deadline):
    import serial

    while time.monotonic() < deadline:
        try:
            with serial.Serial(port, 115200, timeout=1) as s:
                while time.monotonic() < deadline:
                    raw = s.readline()
                    if raw:
                        yield raw
        except serial.SerialException:
            time.sleep(0.5)  # port po resetu chvíli chybí


def main():
    from serial.tools import list_ports

    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("--port")
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--fail", action="append", default=[])
    args = ap.parse_args()

    deadline = time.monotonic() + args.timeout
    port = args.port
    while port is None and time.monotonic() < deadline:
        port = find_port(list_ports.comports())
        if port is None:
            time.sleep(0.5)
    if port is None:
        print("serial_wait: port ESP32 nenalezen", file=sys.stderr)
        return 1
    found = wait_for(serial_lines(port, deadline), args.pattern, sys.stdout, args.fail)
    if found is False:
        print("serial_wait: firmware hlásí chybu", file=sys.stderr)
        return 2
    if found is None:
        print(f"serial_wait: '{args.pattern}' nenalezeno do {args.timeout:.0f} s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
