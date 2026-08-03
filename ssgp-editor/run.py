#!/usr/bin/env python3
"""Start the SSGP Editor server (API + web UI).

    python run.py                # uses host/port from config.yaml
    python run.py --port 9000    # override

Then open http://localhost:8080  (or your chosen port).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from ssgp.config import ROOT, load_config
from ssgp.ffmpeg_utils import ffmpeg_available, install_hint


def _load_local_secrets() -> None:
    """Load the API key (and optional model) from persistent local files so the
    user sets it ONCE and never has to re-paste it each session. Checked in order,
    without overwriting anything already set in the environment:

      1. ~/.ssgp-key            (just the key on one line)
      2. <project>/.env         (KEY=VALUE lines, e.g. ANTHROPIC_API_KEY=sk-ant-...)

    Neither file is committed to git.
    """
    # 1) ~/.ssgp-key -> ANTHROPIC_API_KEY
    keyfile = Path.home() / ".ssgp-key"
    if not os.environ.get("ANTHROPIC_API_KEY") and keyfile.exists():
        val = keyfile.read_text(encoding="utf-8").strip()
        if val:
            os.environ["ANTHROPIC_API_KEY"] = val.splitlines()[0].strip()

    # 2) project .env -> any KEY=VALUE (ANTHROPIC_API_KEY, SSGP_MODEL, ...)
    envfile = ROOT / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and not os.environ.get(k):
                os.environ[k] = v


def main() -> None:
    _load_local_secrets()
    cfg = load_config()
    server = cfg.get("server", {})

    # Hosts like Render/Railway/Fly inject the port to bind via $PORT.
    default_port = int(os.environ.get("PORT") or server.get("port", 8080))

    ap = argparse.ArgumentParser(description="SSGP Editor server")
    ap.add_argument("--host", default=server.get("host", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=default_port)
    ap.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    args = ap.parse_args()

    if not ffmpeg_available():
        print("\n[!] " + install_hint() + "\n")

    if os.environ.get("ANTHROPIC_API_KEY"):
        print("AI editing: ON (Anthropic key loaded)")
    else:
        print("AI editing: OFF — save your key once with:  echo 'sk-ant-...' > ~/.ssgp-key")

    print(f"SSGP Editor -> http://{args.host}:{args.port}  (UI + API)")
    uvicorn.run("ssgp.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
