"""Shared pytest fixtures."""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def tmp_db(monkeypatch):
    """Swap in a fresh SQLite file for the duration of the test.

    We can't simply reload app.db because the model classes were imported
    against the original Base — reloading db rebinds Base but leaves the
    model registrations stuck on the old metadata. Instead we replace the
    engine and SessionLocal in-place.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    import app.db as db_mod
    from app.db import Base  # noqa: F401 — touch import
    import app.models  # noqa: F401 — registers ORM classes with Base

    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False}, future=True
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal", SessionLocal)

    yield db_mod

    engine.dispose()
    os.unlink(path)
