"""End-to-end smoke test of the real workflow.

Runs without an API key (offline/inferred path) so CI and a first-time owner
can verify the full pipeline: research -> save trends -> generate ideas ->
select -> filming package -> approve -> performance -> analysis.

Run with:  python -m pytest -q   (or)  python tests/test_e2e.py
"""
from __future__ import annotations

import os
import tempfile

# Use an isolated temp database before importing the app modules.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DAILY_RUN_ENABLED"] = "false"
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # force offline path

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Briefing, Idea, Performance, Trend  # noqa: E402
from app.services import analytics, ideas as ideas_svc  # noqa: E402
from app.services import briefing as briefing_svc  # noqa: E402


def run() -> None:
    init_db()
    with SessionLocal() as db:
        # 1-5: full daily workflow
        brief = briefing_svc.run_daily_workflow(db, run_type="manual")
        db.commit()

        assert isinstance(brief, Briefing)
        trends = db.query(Trend).all()
        ideas = db.query(Idea).all()
        assert trends, "expected trends to be researched"
        assert ideas, "expected ideas to be generated"
        assert brief.headline, "expected a briefing headline"
        assert brief.source in {"inferred", "live_research"}
        print(f"✓ workflow: {len(trends)} trends, {len(ideas)} ideas, briefing '{brief.headline}'")

        # primary idea should have a filming package
        primary = db.get(Idea, brief.primary_idea_id)
        assert primary is not None
        assert primary.script, "primary idea should have a script"
        assert primary.hashtags, "primary idea should have hashtags"
        assert primary.caption, "primary idea should have a caption"
        assert primary.no_speak_version, "primary idea should have a no-talking version"
        assert isinstance(primary.compliance, dict) and "passed" in primary.compliance
        print("✓ filming package + compliance present on the recommended video")

        # 6: dedup — a second run should not duplicate identical ideas
        before = len(ideas)
        briefing_svc.run_daily_workflow(db, run_type="manual")
        db.commit()
        after = db.query(Idea).count()
        # Offline heuristic reuses the same evergreen concepts; dedup should keep
        # growth modest (no exact-duplicate fingerprints).
        fps = [i.fingerprint for i in db.query(Idea).all()]
        assert len(fps) == len(set(fps)), "duplicate fingerprints leaked past dedup"
        print(f"✓ dedup: {before} -> {after} ideas, no duplicate fingerprints")

        # 7: approve + build package on a non-primary idea
        other = db.query(Idea).filter(Idea.id != primary.id).first()
        ideas_svc.build_filming_package(db, other)
        other.status = "Approved"
        db.commit()
        assert other.script
        print("✓ approve + build package on a second idea")

        # 8: record performance and 9: analysis improves recommendations
        perf = Performance(
            idea_id=primary.id, platform=primary.platform, category=primary.category,
            hook=primary.hook, views=5000, reach=6000, likes=300, comments=45,
            shares=80, saves=120, completion_rate=62.0, calls=3, messages=5,
            appointments=1, video_length_seconds=22,
        )
        db.add(perf)
        primary.status = "Published"
        db.commit()

        result, source = analytics.run_analysis(db)
        assert "headline" in result
        summary = analytics.summarise_for_strategist(db)
        assert "1 posts" in summary or "posts logged" in summary
        print(f"✓ performance logged + analysis produced ({source})")

    print("\nALL END-TO-END CHECKS PASSED ✅")


def test_end_to_end():
    run()


if __name__ == "__main__":
    run()
