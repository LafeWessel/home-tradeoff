"""Metric resolver — orchestrates fetching, caching, and cascading lookups.

The resolver is the bridge between the API layer (which asks "give me all
metrics for these locations") and the source layer (which knows how to talk
to one external API).

Behavior:
  1. Expand each requested location to its ancestor chain (place -> county
     -> state) so we can answer questions at coarser granularities even
     when the user picked a city.
  2. For each ancestor, fetch any metric values that aren't already cached
     and have not gone stale.
  3. Persist new values to ``metric_values`` with provenance.
  4. When asked for a metric value at level L for location X, return X's
     own value if present, else cascade up the ancestor chain.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .metrics_catalog import CATALOG, CATALOG_BY_KEY, MetricDef
from .models.location import GeoLevel, Location
from .models.metric_value import MetricValue
from .sources import airport, bls, census, fbi, static_loader

log = logging.getLogger(__name__)

# How long a cached metric value is considered fresh before we refetch.
DEFAULT_FRESHNESS = timedelta(days=30)


def get_ancestors(db: Session, location: Location) -> list[Location]:
    """Return [self, county_parent?, state_parent?] in order from finest to coarsest."""
    chain: list[Location] = [location]
    cur = location
    while cur.parent_geoid:
        parent = db.execute(
            select(Location).where(Location.geoid == cur.parent_geoid)
        ).scalar_one_or_none()
        if not parent or parent.id == cur.id:
            break
        chain.append(parent)
        cur = parent
    return chain


def _missing_or_stale_metric_keys(
    db: Session, location: Location, metric_keys: list[str], freshness: timedelta
) -> list[str]:
    """Return keys whose cached value for `location` is missing or older than `freshness`."""
    if not metric_keys:
        return []
    rows = db.execute(
        select(MetricValue.metric_key, MetricValue.fetched_at).where(
            MetricValue.location_id == location.id, MetricValue.metric_key.in_(metric_keys)
        )
    ).all()
    cutoff = datetime.now(timezone.utc) - freshness
    fresh: set[str] = set()
    for k, fetched_at in rows:
        if fetched_at is not None:
            ts = fetched_at if fetched_at.tzinfo else fetched_at.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                fresh.add(k)
    return [k for k in metric_keys if k not in fresh]


def _metrics_for_level(level: GeoLevel) -> list[MetricDef]:
    """Metrics that are *natively* defined at this level (not via cascade)."""
    rank = {GeoLevel.place: 3, GeoLevel.county: 2, GeoLevel.state: 1}
    out: list[MetricDef] = []
    for m in CATALOG:
        try:
            ml = GeoLevel(m.finest_level)
        except ValueError:
            continue
        if rank[level] >= rank[ml] and ml == level:
            out.append(m)
    return out


def _all_native_metrics(level: GeoLevel) -> list[MetricDef]:
    """Metrics defined natively *at or below* this level — used when fetching."""
    rank = {GeoLevel.place: 3, GeoLevel.county: 2, GeoLevel.state: 1}
    out: list[MetricDef] = []
    for m in CATALOG:
        try:
            ml = GeoLevel(m.finest_level)
        except ValueError:
            continue
        if rank[ml] == rank[level]:
            out.append(m)
    return out


def ensure_metric_values(
    db: Session, locations: list[Location], freshness: timedelta = DEFAULT_FRESHNESS
) -> None:
    """Make sure every applicable metric is fetched and cached for these locations.

    Expands locations to include all ancestors, then runs each source for the
    locations whose level it serves.
    """
    # Build the working set: requested locations + their ancestors
    seen_ids: set[int] = set()
    working: list[Location] = []
    for loc in locations:
        for anc in get_ancestors(db, loc):
            if anc.id not in seen_ids:
                seen_ids.add(anc.id)
                working.append(anc)

    # Bucket by level
    by_level: dict[GeoLevel, list[Location]] = {}
    for loc in working:
        by_level.setdefault(loc.level, []).append(loc)

    # ---- Census ACS (state, county, place) ----
    census_locs = working  # Census handles all 3 levels
    if census_locs:
        # Drive the cache check from census.METRIC_DEFS so newly-added metrics
        # (e.g. demo.race.*) automatically trigger a refetch instead of silently
        # being skipped because older keys are still fresh.
        keys = [k for k, _vars, _fn in census.METRIC_DEFS]
        needs = [
            loc for loc in census_locs if _missing_or_stale_metric_keys(db, loc, keys, freshness)
        ]
        if needs:
            tuples = census.fetch_for_locations(db, needs)
            _upsert(db, tuples)

    # ---- BLS LAUS (state, county) ----
    bls_locs = [
        loc for loc in working if loc.level in (GeoLevel.state, GeoLevel.county)
    ]
    if bls_locs:
        needs = [
            loc
            for loc in bls_locs
            if _missing_or_stale_metric_keys(db, loc, ["employment.unemployment_rate"], freshness)
        ]
        if needs:
            tuples = bls.fetch_for_locations(db, needs)
            _upsert(db, tuples)

    # ---- Static sources (taxes, climate, RPP, FEMA, crime, ...) ----
    # Static loaders are cheap — always run, the upsert is idempotent.
    _upsert(db, static_loader.fetch_taxes(db, working))
    _upsert(db, static_loader.fetch_climate(db, working))
    _upsert(db, static_loader.fetch_rpp(db, working))
    _upsert(db, static_loader.fetch_fema(db, working))
    _upsert(db, static_loader.fetch_insurance(db, working))
    _upsert(db, static_loader.fetch_taxes_extra(db, working))
    _upsert(db, static_loader.fetch_housing_appreciation(db, working))
    _upsert(db, static_loader.fetch_nri_components(db, working))
    _upsert(db, static_loader.fetch_pm25(db, working))
    _upsert(db, static_loader.fetch_heat_index(db, working))
    _upsert(db, static_loader.fetch_utilities(db, working))
    _upsert(db, static_loader.fetch_education(db, working))
    _upsert(db, static_loader.fetch_health(db, working))
    _upsert(db, static_loader.fetch_growth(db, working))
    _upsert(db, static_loader.fetch_politics(db, working))
    _upsert(db, static_loader.fetch_crime(db, working))
    _upsert(db, static_loader.fetch_col_components(db, working))
    _upsert(db, airport.fetch_for_locations(db, working))

    # ---- FBI CDE live overlay (state) ----
    # The live FBI Crime Data Explorer endpoints under api.usa.gov/crime/fbi/cde
    # started returning 404 in 2026-05; the static state_crime.json snapshot
    # above is the primary source. We still attempt the live fetch as a
    # best-effort overlay so values refresh automatically once the API comes
    # back; the circuit breaker quietly suppresses it when the API is down.
    # Runs LAST so a successful live fetch overwrites the static snapshot.
    fbi_locs = [loc for loc in working if loc.level == GeoLevel.state]
    if fbi_locs:
        tuples = fbi.fetch_for_locations(db, fbi_locs)
        if tuples:
            _upsert(db, tuples)


def _upsert(
    db: Session, rows: list[tuple[int, str, float | None, str, int]]
) -> None:
    if not rows:
        return
    now = datetime.now(timezone.utc)
    for location_id, metric_key, value, source, year in rows:
        existing = db.execute(
            select(MetricValue).where(
                MetricValue.location_id == location_id, MetricValue.metric_key == metric_key
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                MetricValue(
                    location_id=location_id,
                    metric_key=metric_key,
                    value=value,
                    source=source,
                    source_year=year,
                    fetched_at=now,
                )
            )
        else:
            existing.value = value
            existing.source = source
            existing.source_year = year
            existing.fetched_at = now
    db.commit()


def get_resolved_metrics(
    db: Session, location: Location
) -> dict[str, dict]:
    """Return {metric_key: {value, source, year, level_resolved}} for `location`.

    For metrics whose `finest_level` is coarser than the location, we cascade
    up the ancestor chain. The `level_resolved` field tells the UI which level
    the value actually came from so it can display "(state value)" hints.
    """
    chain = get_ancestors(db, location)
    chain_ids = [c.id for c in chain]

    rows = db.execute(
        select(MetricValue).where(MetricValue.location_id.in_(chain_ids))
    ).all()
    by_loc_metric: dict[tuple[int, str], MetricValue] = {}
    for (mv,) in rows:
        by_loc_metric[(mv.location_id, mv.metric_key)] = mv

    out: dict[str, dict] = {}
    for m in CATALOG:
        for c in chain:  # finest -> coarsest
            mv = by_loc_metric.get((c.id, m.key))
            if mv is not None and mv.value is not None:
                out[m.key] = {
                    "value": mv.value,
                    "source": mv.source,
                    "source_year": mv.source_year,
                    "fetched_at": mv.fetched_at.isoformat() if mv.fetched_at else None,
                    "level_resolved": c.level.value if isinstance(c.level, GeoLevel) else c.level,
                    "resolved_geoid": c.geoid,
                }
                break
        else:
            out[m.key] = {
                "value": None,
                "source": None,
                "source_year": None,
                "fetched_at": None,
                "level_resolved": None,
                "resolved_geoid": None,
            }
    return out
