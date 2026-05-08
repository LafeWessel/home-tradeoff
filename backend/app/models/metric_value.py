from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class MetricValue(Base):
    """A single metric reading for a single location.

    Provenance fields (`source`, `source_year`, `fetched_at`) are stored alongside
    every value so the UI can render "as of" stamps and refresh reasoning.
    """

    __tablename__ = "metric_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    metric_key: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    text_value: Mapped[str | None] = mapped_column(String(256))
    source: Mapped[str | None] = mapped_column(String(64))
    source_year: Mapped[int | None] = mapped_column()
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    location = relationship("Location", back_populates="metric_values")

    __table_args__ = (
        UniqueConstraint("location_id", "metric_key", name="uq_metric_value_location_key"),
        Index("ix_metric_values_metric_key_location", "metric_key", "location_id"),
    )
