"""US Census Bureau ACS 5-year fetcher.

Endpoint:
    https://api.census.gov/data/{year}/acs/acs5?get={vars}&for={geo}&in={parent}&key={key}

Returns a 2D array — first row is headers, rest are values. We map variables
into our metric keys and emit `(metric_key, value)` tuples.

We use ACS 5-year tables because they have full coverage at all geographies
including small places. The 1-year tables are only published for 65k+ areas.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models.location import GeoLevel, Location
from ..settings import settings
from .http_cache import cached_get_json

log = logging.getLogger(__name__)

ACS_YEAR = 2023  # 5-year ACS released Dec 2024 — covers 2019-2023

# (metric_key, list of ACS variable codes used to compute it, computer fn)
# computer fn takes the dict {var_code -> float | None} and returns float | None
def _ratio(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None or denom <= 0:
        return None
    return 100.0 * num / denom


def _bachelors_or_higher_pct(vals: dict[str, float | None]) -> float | None:
    total = vals.get("B15003_001E")
    parts = [
        vals.get("B15003_022E"),  # Bachelor's
        vals.get("B15003_023E"),  # Master's
        vals.get("B15003_024E"),  # Professional
        vals.get("B15003_025E"),  # Doctorate
    ]
    if total is None or any(p is None for p in parts):
        return None
    return _ratio(sum(parts), total)  # type: ignore[arg-type]


def _owner_occupied_pct(vals: dict[str, float | None]) -> float | None:
    return _ratio(vals.get("B25003_002E"), vals.get("B25003_001E"))


def _race_pct(*nums: str):
    """Build a function returning sum(num vars) / B03002_001E as a percentage."""

    def fn(vals: dict[str, float | None]) -> float | None:
        total = vals.get("B03002_001E")
        parts = [vals.get(v) for v in nums]
        if total is None or any(p is None for p in parts):
            return None
        return _ratio(sum(parts), total)  # type: ignore[arg-type]

    return fn


def _identity(var: str):
    def fn(vals: dict[str, float | None]) -> float | None:
        v = vals.get(var)
        # ACS sentinels for missing/suppressed values: -666666666, -999999999, etc.
        if v is None or v <= -666666666:
            return None
        return v

    return fn


METRIC_DEFS: list[tuple[str, list[str], Any]] = [
    ("pop.total", ["B01003_001E"], _identity("B01003_001E")),
    ("pop.median_age", ["B01002_001E"], _identity("B01002_001E")),
    ("econ.median_household_income", ["B19013_001E"], _identity("B19013_001E")),
    ("housing.median_value", ["B25077_001E"], _identity("B25077_001E")),
    ("housing.median_rent", ["B25064_001E"], _identity("B25064_001E")),
    ("housing.owner_occupied_pct", ["B25003_001E", "B25003_002E"], _owner_occupied_pct),
    ("tax.property.median_annual_bill", ["B25103_001E"], _identity("B25103_001E")),
    (
        "edu.bachelors_or_higher_pct",
        ["B15003_001E", "B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"],
        _bachelors_or_higher_pct,
    ),
    # ACS B03002: Hispanic/Latino origin by race. Categories are mutually exclusive
    # so percentages sum to ~100. Hispanic counts any-race; non-Hispanic categories
    # are the "alone" race breakdowns.
    ("demo.race.white_pct", ["B03002_001E", "B03002_003E"], _race_pct("B03002_003E")),
    ("demo.race.black_pct", ["B03002_001E", "B03002_004E"], _race_pct("B03002_004E")),
    ("demo.race.hispanic_pct", ["B03002_001E", "B03002_012E"], _race_pct("B03002_012E")),
    ("demo.race.asian_pct", ["B03002_001E", "B03002_006E"], _race_pct("B03002_006E")),
    (
        "demo.race.native_american_pct",
        ["B03002_001E", "B03002_005E"],
        _race_pct("B03002_005E"),
    ),
    (
        "demo.race.other_pct",
        ["B03002_001E", "B03002_007E", "B03002_008E", "B03002_009E"],
        _race_pct("B03002_007E", "B03002_008E", "B03002_009E"),
    ),
]


def _all_vars() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _, vars_, _ in METRIC_DEFS:
        for v in vars_:
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def _parse_acs(raw: list[list[str]]) -> list[dict[str, str | None]]:
    """Parse Census 2D array into list of dicts."""
    if not raw or len(raw) < 2:
        return []
    headers = raw[0]
    rows: list[dict[str, str | None]] = []
    for r in raw[1:]:
        rows.append({h: (v if v != "null" else None) for h, v in zip(headers, r)})
    return rows


def _coerce_floats(row: dict[str, str | None], keys: list[str]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for k in keys:
        v = row.get(k)
        if v is None or v == "":
            out[k] = None
        else:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = None
    return out


def fetch_for_locations(
    db: Session, locations: list[Location]
) -> list[tuple[int, str, float | None, str, int]]:
    """Fetch ACS metrics for the given locations.

    Returns rows of (location_id, metric_key, value, source, year) for the
    resolver to upsert.
    """
    if not settings.census_api_key:
        log.warning("CENSUS_API_KEY missing — skipping ACS fetch")
        return []

    # Bucket by level (we make one request per level per state).
    by_level_state: dict[tuple[GeoLevel, str | None], list[Location]] = {}
    for loc in locations:
        by_level_state.setdefault((loc.level, loc.state_fips), []).append(loc)

    vars_ = _all_vars()
    out: list[tuple[int, str, float | None, str, int]] = []

    for (level, state_fips), locs in by_level_state.items():
        params: dict[str, Any] = {
            "get": ",".join(["NAME", *vars_]),
            "key": settings.census_api_key,
        }
        if level == GeoLevel.state:
            params["for"] = "state:*"
        elif level == GeoLevel.county:
            params["for"] = "county:*"
            params["in"] = f"state:{state_fips}"
        elif level == GeoLevel.place:
            params["for"] = "place:*"
            params["in"] = f"state:{state_fips}"
        else:
            continue

        url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
        try:
            raw = cached_get_json(db, url, params=params)
        except Exception as e:  # noqa: BLE001
            log.warning("Census fetch failed for %s/%s (non-fatal): %s", level, state_fips, e)
            continue
        rows = _parse_acs(raw)

        # Index returned rows by GEOID we can match to our Location rows.
        index: dict[str, dict[str, str | None]] = {}
        for r in rows:
            if level == GeoLevel.state:
                gid = (r.get("state") or "").zfill(2)
            elif level == GeoLevel.county:
                gid = (r.get("state") or "").zfill(2) + (r.get("county") or "").zfill(3)
            else:  # place
                gid = (r.get("state") or "").zfill(2) + (r.get("place") or "").zfill(5)
            index[gid] = r

        for loc in locs:
            r = index.get(loc.geoid)
            if r is None:
                continue
            float_vals = _coerce_floats(r, vars_)
            for metric_key, _, fn in METRIC_DEFS:
                v = fn(float_vals)
                out.append((loc.id, metric_key, v, "Census ACS 5yr", ACS_YEAR))

    return out
