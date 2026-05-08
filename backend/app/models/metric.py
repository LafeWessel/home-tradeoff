from __future__ import annotations

import enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class MetricDirection(str, enum.Enum):
    lower_better = "lower_better"
    higher_better = "higher_better"
    target = "target"


class Metric(Base):
    """A metric definition (registered at startup from `metrics_catalog.py`).

    The DB row exists primarily so MetricValue can FK to it cleanly and
    so we can show metric metadata without hardcoding it in the UI.
    """

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32), index=True)
    unit: Mapped[str] = mapped_column(String(32))
    direction: Mapped[MetricDirection] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(String(512))
    source_label: Mapped[str | None] = mapped_column(String(64))
    # Lowest geo level at which this metric is meaningfully resolvable.
    # When asked at a more-granular level we'll cascade up to the parent.
    finest_level: Mapped[str] = mapped_column(String(16), default="state")
