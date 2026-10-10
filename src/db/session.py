"""SQLAlchemy engine and request-scoped sessions."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import Settings, get_settings


@lru_cache(maxsize=8)
def get_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    current = settings or get_settings()
    return sessionmaker(
        bind=get_engine(current.database_url),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
