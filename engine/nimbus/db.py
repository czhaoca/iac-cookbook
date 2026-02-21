"""Database engine, session factory, and base model."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.effective_database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False} if "sqlite" in settings.effective_database_url else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all Nimbus models."""
    pass


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (for development — use Alembic in production)."""
    Base.metadata.create_all(bind=engine)
