import argparse
import logging
import os
from collections.abc import Mapping
from pathlib import Path

from .app import Config, create_app

REQUIRED = ("PHOTOS_DIR", "DATA_DIR", "INKA_DEVICE_TOKEN")


def config_from_env(env: Mapping[str, str]) -> Config:
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")
    return Config(
        Path(env["PHOTOS_DIR"]), Path(env["DATA_DIR"]), env["INKA_DEVICE_TOKEN"], tz=env.get("INKA_TZ", "Europe/Prague")
    )


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    ap = argparse.ArgumentParser(prog="inka-server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(config_from_env(os.environ)), host=args.host, port=args.port)
