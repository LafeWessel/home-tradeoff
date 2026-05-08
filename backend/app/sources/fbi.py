"""FBI Crime Data Explorer (CDE) — state-level annual estimates.

Endpoint:
    https://api.usa.gov/crime/fbi/cde/estimate/state/{abbr}?from=YYYY&to=YYYY&API_KEY=...

Returns annual rows including violent_crime, property_crime, and population.
We compute per-100k rates and emit the most recent year.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models.location import GeoLevel, Location
from ..settings import settings
from .http_cache import cached_get_json

log = logging.getLogger(__name__)

CDE_URL = "https://api.usa.gov/crime/fbi/cde/estimate/state/{abbr}"


def fetch_for_locations(
    db: Session, locations: list[Location], year: int = 2023
) -> list[tuple[int, str, float | None, str, int]]:
    if not settings.fbi_api_key:
        log.warning("FBI_API_KEY missing — skipping FBI CDE fetch")
        return []

    out: list[tuple[int, str, float | None, str, int]] = []

    for loc in locations:
        if loc.level != GeoLevel.state or not loc.state_abbr:
            continue
        url = CDE_URL.format(abbr=loc.state_abbr)
        params: dict[str, Any] = {
            "from": str(year - 4),
            "to": str(year),
            "API_KEY": settings.fbi_api_key,
        }
        try:
            payload = cached_get_json(db, url, params=params)
        except Exception as e:  # noqa: BLE001
            log.error("FBI fetch failed for %s: %s", loc.state_abbr, e)
            continue

        rows = _coerce_rows(payload)
        if not rows:
            continue

        # Most recent year
        rows.sort(key=lambda r: r["year"], reverse=True)
        latest = rows[0]
        pop = latest.get("population") or 0
        if pop <= 0:
            continue

        violent = latest.get("violent_crime")
        prop = latest.get("property_crime")
        if violent is not None:
            out.append(
                (loc.id, "crime.violent_per_100k", 100000 * violent / pop, "FBI CDE", latest["year"])
            )
        if prop is not None:
            out.append(
                (loc.id, "crime.property_per_100k", 100000 * prop / pop, "FBI CDE", latest["year"])
            )

    return out


def _coerce_rows(payload: Any) -> list[dict[str, Any]]:
    """The FBI CDE response shape varies. Accept a few common formats."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        # Common keys: "results", "data", or direct year-keyed dicts
        if "results" in payload and isinstance(payload["results"], list):
            rows = payload["results"]
        elif "data" in payload and isinstance(payload["data"], list):
            rows = payload["data"]
        else:
            # Treat the dict itself as { "2023": {...}, "2022": {...} }
            rows = []
            for k, v in payload.items():
                if isinstance(v, dict) and k.isdigit():
                    rows.append({"year": int(k), **v})
    else:
        return []

    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            yr = int(r.get("year") or r.get("data_year") or 0)
        except (TypeError, ValueError):
            continue
        if yr <= 0:
            continue
        out.append(
            {
                "year": yr,
                "population": _to_float(r.get("population") or r.get("estimated_population")),
                "violent_crime": _to_float(r.get("violent_crime") or r.get("violentCrime")),
                "property_crime": _to_float(r.get("property_crime") or r.get("propertyCrime")),
            }
        )
    return out


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
