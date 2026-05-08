from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ApiCache(Base):
    """HTTP response cache.

    Keyed by SHA-256 of (method, url, sorted query params, body). TTL stored
    per-row so different sources can have different freshness windows.
    """

    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    method: Mapped[str] = mapped_column(String(8))
    url: Mapped[str] = mapped_column(String(1024))
    status: Mapped[int] = mapped_column(Integer)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str | None] = mapped_column(String(128))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=60 * 60 * 24 * 30)
