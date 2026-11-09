from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    existing_columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    recommendation_columns = {
        "baseline_match_score": "INTEGER",
        "match_summary": "TEXT NOT NULL DEFAULT ''",
        "matched_skills": "JSON NOT NULL DEFAULT '[]'",
        "skill_gaps": "JSON NOT NULL DEFAULT '[]'",
        "resume_outreach_pitch": "TEXT NOT NULL DEFAULT ''",
        "notion_page_id": "VARCHAR(100) NOT NULL DEFAULT ''",
        "source_type": "VARCHAR(30) NOT NULL DEFAULT 'manual'",
        "posted_at": "DATE",
    }
    with engine.begin() as connection:
        for name, definition in recommendation_columns.items():
            if name not in existing_columns:
                connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {definition}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
