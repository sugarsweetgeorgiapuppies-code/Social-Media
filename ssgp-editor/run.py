#!/usr/bin/env python3
"""Start the SSGP Editor server (API + web UI).

    python run.py                # uses host/port from config.yaml
    python run.py --port 9000    # override

Then open http://localhost:8080  (or your chosen port).
"""

from __future__ import annotations

import argparse

import uvicorn

from ssgp.config import load_config
from ssgp.ffmpeg_utils import ffmpeg_available, install_hint


def main() -> None:
    cfg = load_config()
    server = cfg.get("server", {})

    ap = argparse.ArgumentParser(description="SSGP Editor server")
    ap.add_argument("--host", default=server.get("host", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(server.get("port", 8080)))
    ap.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    args = ap.parse_args()

    if not ffmpeg_available():
        print("\n[!] " + install_hint() + "\n")

    print(f"SSGP Editor -> http://{args.host}:{args.port}  (UI + API)")
    uvicorn.run("ssgp.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
