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

from .metrics_catalog import CATALOG, CATALOG_BY_KEY
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
    _upsert(db, static_loader.fetch_homeschool_voucher(db, working))
    _upsert(db, static_loader.fetch_health(db, working))
    _upsert(db, static_loader.fetch_growth(db, working))
    _upsert(db, static_loader.fetch_politics(db, working))
    _upsert(db, static_loader.fetch_crime(db, working))
    _upsert(db, static_loader.fetch_col_components(db, working))
    _upsert(db, static_loader.fetch_obesity(db, working))
    _upsert(db, static_loader.fetch_cancer(db, working))
    _upsert(db, static_loader.fetch_public_lands(db, working))
    _upsert(db, static_loader.fetch_elevation(db, working))
    _upsert(db, static_loader.fetch_summits(db, working))
    _upsert(db, static_loader.fetch_plant_hardiness(db, working))
    _upsert(db, static_loader.fetch_water_quality(db, working))
    _upsert(db, static_loader.fetch_firearms(db, working))
    _upsert(db, static_loader.fetch_outdoor_recreation(db, working))
    _upsert(db, static_loader.fetch_park_availability(db, working))
    _upsert(db, static_loader.fetch_marijuana(db, working))
    _upsert(db, static_loader.fetch_abortion(db, working))
    _upsert(db, static_loader.fetch_religion(db, working))
    _upsert(db, static_loader.fetch_religion_adherence(db, working))
    _upsert(db, static_loader.fetch_religion_family(db, working))
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
    loc_ids = {r[0] for r in rows}
    keys = {r[1] for r in rows}
    existing_mvs = db.execute(
        select(MetricValue).where(
            MetricValue.location_id.in_(loc_ids),
            MetricValue.metric_key.in_(keys),
        )
    ).scalars().all()
    existing_map: dict[tuple[int, str], MetricValue] = {
        (mv.location_id, mv.metric_key): mv for mv in existing_mvs
    }
    for location_id, metric_key, value, source, year in rows:
        existing = existing_map.get((location_id, metric_key))
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


def get_bulk_resolved_metrics(
    db: Session, locations: list[Location]
) -> dict[int, dict[str, dict]]:
    """Batch version of get_resolved_metrics for many state/county locations.

    Fetches all relevant metric values in a single DB query instead of one per
    location, making it suitable for bulk map scoring of 50 states or 3k+ counties.
    """
    if not locations:
        return {}

    loc_by_id: dict[int, Location] = {loc.id: loc for loc in locations}
    parent_geoids = {loc.parent_geoid for loc in locations if loc.parent_geoid}

    parent_locs: list[Location] = []
    if parent_geoids:
        parent_locs = (
            db.execute(select(Location).where(Location.geoid.in_(parent_geoids)))
            .scalars()
            .all()
        )
    parent_by_geoid: dict[str, Location] = {p.geoid: p for p in parent_locs}

    all_ids = set(loc_by_id.keys()) | {p.id for p in parent_locs}

    mvs = db.execute(
        select(MetricValue).where(MetricValue.location_id.in_(all_ids))
    ).scalars().all()
    by_loc_metric: dict[tuple[int, str], MetricValue] = {
        (mv.location_id, mv.metric_key): mv for mv in mvs
    }

    result: dict[int, dict[str, dict]] = {}
    for loc in locations:
        chain = [loc]
        if loc.parent_geoid and loc.parent_geoid in parent_by_geoid:
            chain.append(parent_by_geoid[loc.parent_geoid])

        out: dict[str, dict] = {}
        for m in CATALOG:
            for c in chain:
                mv = by_loc_metric.get((c.id, m.key))
                if mv is not None and mv.value is not None:
                    out[m.key] = {
                        "value": mv.value,
                        "source": mv.source,
                        "source_year": mv.source_year,
                        "fetched_at": mv.fetched_at.isoformat() if mv.fetched_at else None,
                        "level_resolved": (
                            c.level.value if isinstance(c.level, GeoLevel) else c.level
                        ),
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
        result[loc.id] = out
    return result


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
