"""Database engine + session management (SQLite via SQLAlchemy)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import BASE_DIR, settings

# Resolve a relative sqlite path against the project root so the app can be
# launched from anywhere.
_url = settings.DATABASE_URL
if _url.startswith("sqlite:///") and not _url.startswith("sqlite:////"):
    rel = _url.replace("sqlite:///", "", 1)
    abs_path = (BASE_DIR / rel).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    _url = f"sqlite:///{abs_path}"

engine = create_engine(
    _url,
    connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def _lightweight_migrate() -> None:
    """Add newly-introduced columns to existing tables.

    ``create_all`` only creates missing tables — it never alters an existing
    one — so a persisted database (e.g. the live deploy's SQLite file) would be
    missing columns added after it was first created. We add them in place so a
    deploy never has to drop data. Only additive, nullable/defaulted columns are
    handled here; anything more involved would warrant a real migration tool.
    """
    # column name -> DDL type + default used when back-filling existing rows
    expected: dict[str, dict[str, str]] = {
        "ideas": {"format": "VARCHAR(40) DEFAULT 'puppy_focus'"},
    }
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, columns in expected.items():
            if table not in existing_tables:
                continue  # create_all will build it fresh with every column
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in columns.items():
                if col not in have:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}'))


def init_db() -> None:
    """Create tables if they do not exist and seed defaults."""
    from . import models  # noqa: F401  (register mappers)

    Path(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _lightweight_migrate()

    from .seed import seed_defaults

    with SessionLocal() as db:
        seed_defaults(db)
        db.commit()


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
