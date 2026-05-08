from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.location import GeoLevel, Location
from ..resolver import ensure_metric_values, get_resolved_metrics
from .schemas import LocationMetricsOut, LocationOut, MetricValueOut

router = APIRouter(prefix="/api/locations", tags=["locations"])


def _to_out(loc: Location) -> LocationOut:
    level = loc.level.value if isinstance(loc.level, GeoLevel) else loc.level
    return LocationOut(
        id=loc.id,
        geoid=loc.geoid,
        level=level,
        name=loc.name,
        display_name=loc.display_name,
        state_abbr=loc.state_abbr,
        state_fips=loc.state_fips,
        parent_geoid=loc.parent_geoid,
        population=loc.population,
        lat=loc.lat,
        lon=loc.lon,
    )


@router.get("/search", response_model=list[LocationOut])
def search(
    q: str = Query("", max_length=128),
    level: str | None = None,
    state: str | None = None,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[LocationOut]:
    """Fuzzy search by location name. Optionally filter by level or state abbr.

    `q` may be empty, in which case results are returned by population desc
    (subject to level/state filters). Useful for "give me every state" listings.
    """
    q = (q or "").strip()
    stmt = select(Location)
    if q:
        stmt = stmt.where(Location.name.ilike(f"%{q}%"))
    if level:
        stmt = stmt.where(Location.level == level)
    if state:
        stmt = stmt.where(Location.state_abbr == state.upper())
    candidates = db.execute(stmt.limit(1000)).scalars().all()

    if not q or len(candidates) <= limit:
        # Sort by population desc as a reasonable tie-breaker.
        candidates.sort(key=lambda l: (-(l.population or 0), l.name))
        return [_to_out(c) for c in candidates[:limit]]

    # Rerank by fuzzy ratio against display name.
    name_map = {c.id: c.display_name for c in candidates}
    ranked = process.extract(
        q, name_map, scorer=fuzz.WRatio, limit=limit, processor=lambda s: s.lower()
    )
    by_id = {c.id: c for c in candidates}
    return [_to_out(by_id[item[2]]) for item in ranked if item[2] in by_id]


@router.get("/{geoid}", response_model=LocationOut)
def get_location(geoid: str, db: Session = Depends(get_db)) -> LocationOut:
    loc = db.execute(select(Location).where(Location.geoid == geoid)).scalar_one_or_none()
    if loc is None:
        raise HTTPException(404, f"location {geoid} not found")
    return _to_out(loc)


@router.get("/{geoid}/metrics", response_model=LocationMetricsOut)
def get_location_metrics(geoid: str, db: Session = Depends(get_db)) -> LocationMetricsOut:
    loc = db.execute(select(Location).where(Location.geoid == geoid)).scalar_one_or_none()
    if loc is None:
        raise HTTPException(404, f"location {geoid} not found")
    ensure_metric_values(db, [loc])
    metrics = get_resolved_metrics(db, loc)
    return LocationMetricsOut(
        location=_to_out(loc),
        metrics={k: MetricValueOut(**v) for k, v in metrics.items()},
    )
