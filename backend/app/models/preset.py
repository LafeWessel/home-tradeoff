from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Preset(Base):
    """A named bundle of preferences. Users save and switch between these."""

    __tablename__ = "presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    preferences: Mapped[list["Preference"]] = relationship(
        back_populates="preset",
        cascade="all, delete-orphan",
    )


class Preference(Base):
    """One metric's preference inside a preset.

    Direction comes from the metric definition by default but can be
    overridden per-preset (e.g. someone wants COLDER summers).
    """

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    preset_id: Mapped[int] = mapped_column(ForeignKey("presets.id", ondelete="CASCADE"))
    metric_key: Mapped[str] = mapped_column(String(64))
    weight: Mapped[float] = mapped_column(Float, default=5.0)
    direction: Mapped[str | None] = mapped_column(String(16))
    # For lower_better: ideal = best ceiling; cap = "unacceptable" floor of credit
    # For higher_better: ideal = best floor;   cap = "unacceptable" ceiling of credit
    # For target:       ideal = target;        tolerance = ± window of full credit decay
    ideal: Mapped[float | None] = mapped_column(Float)
    cap: Mapped[float | None] = mapped_column(Float)
    tolerance: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(default=True)

    preset = relationship("Preset", back_populates="preferences")

    __table_args__ = (Index("ix_preferences_preset_metric", "preset_id", "metric_key", unique=True),)
