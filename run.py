#!/usr/bin/env python3
"""Entrypoint: launch the AI Social Media Employee web app.

Usage:
    python run.py              # start the web server + scheduler
    python run.py --research   # run one research/briefing cycle and exit
"""
from __future__ import annotations

import argparse

from app.config import settings


def run_once() -> None:
    """Run a single end-to-end research + briefing cycle (for cron/testing)."""
    from app.database import SessionLocal, init_db
    from app.services import briefing as briefing_svc

    init_db()
    with SessionLocal() as db:
        brief = briefing_svc.run_daily_workflow(db, run_type="manual")
        db.commit()
        print(f"Briefing generated for {brief.date}: {brief.headline}")
        print(brief.summary)


def serve() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sugar Sweet Georgia Puppies AI employee")
    parser.add_argument(
        "--research",
        action="store_true",
        help="Run one research + briefing cycle and exit (no web server).",
    )
    args = parser.parse_args()
    if args.research:
        run_once()
    else:
        serve()
