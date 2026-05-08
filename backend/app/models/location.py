from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class GeoLevel(str, enum.Enum):
    state = "state"
    county = "county"
    place = "place"  # incorporated place / CDP / municipality


class Location(Base):
    """A US geography (state, county, or place).

    `geoid` is the canonical Census GEOID:
      - state  -> 2-digit state FIPS               (e.g. "06")
      - county -> 5-digit state+county FIPS        (e.g. "06037")
      - place  -> 7-digit state+place FIPS         (e.g. "0644000" Los Angeles, CA)
    """

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    geoid: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    level: Mapped[GeoLevel] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    state_fips: Mapped[str | None] = mapped_column(String(2), index=True)
    state_abbr: Mapped[str | None] = mapped_column(String(2), index=True)
    county_fips: Mapped[str | None] = mapped_column(String(3))
    place_fips: Mapped[str | None] = mapped_column(String(5))
    parent_geoid: Mapped[str | None] = mapped_column(String(16), index=True)
    population: Mapped[int | None] = mapped_column()
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    metric_values: Mapped[list["MetricValue"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="location",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_locations_level_name", "level", "name"),
        Index("ix_locations_state_level", "state_fips", "level"),
    )

    @property
    def display_name(self) -> str:
        if self.level == GeoLevel.state or self.state_abbr is None:
            return self.name
        return f"{self.name}, {self.state_abbr}"
