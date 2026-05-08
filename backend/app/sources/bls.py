"""BLS LAUS (Local Area Unemployment Statistics) fetcher.

Series ID format:
    State:  LAUST{state_fips}0000000000003   (annual avg unemployment rate)
    County: LAUCN{state_fips}{county_fips}0000000003

We fetch the most recent annual average. The BLS v2 API supports up to 50
series per POST request and 500 requests/day with a registered key.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models.location import GeoLevel, Location
from ..settings import settings
from .http_cache import cached_post_json

log = logging.getLogger(__name__)

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def _series_id(loc: Location) -> str | None:
    if loc.level == GeoLevel.state and loc.state_fips:
        return f"LAUST{loc.state_fips}0000000000003"
    if loc.level == GeoLevel.county and loc.state_fips and loc.county_fips:
        return f"LAUCN{loc.state_fips}{loc.county_fips}0000000003"
    return None


def fetch_for_locations(
    db: Session, locations: list[Location], year: int = 2024
) -> list[tuple[int, str, float | None, str, int]]:
    by_series: dict[str, Location] = {}
    for loc in locations:
        sid = _series_id(loc)
        if sid:
            by_series[sid] = loc

    if not by_series:
        return []

    out: list[tuple[int, str, float | None, str, int]] = []
    series_ids = list(by_series.keys())

    # BLS allows up to 50 series per request; chunk.
    for i in range(0, len(series_ids), 50):
        chunk = series_ids[i : i + 50]
        body: dict[str, Any] = {
            "seriesid": chunk,
            "startyear": str(year - 1),
            "endyear": str(year),
            "annualaverage": True,
        }
        if settings.bls_api_key:
            body["registrationkey"] = settings.bls_api_key

        try:
            payload = cached_post_json(db, BLS_URL, json_body=body)
        except Exception as e:  # noqa: BLE001
            log.error("BLS fetch failed: %s", e)
            continue

        results = (payload.get("Results") or {}).get("series") or []
        for s in results:
            sid = s.get("seriesID")
            loc = by_series.get(sid)
            if loc is None:
                continue
            data = s.get("data") or []
            # Prefer M13 (annual average); fall back to most recent monthly.
            annual = next((d for d in data if d.get("period") == "M13"), None)
            chosen = annual or (data[0] if data else None)
            if not chosen:
                continue
            try:
                value = float(chosen["value"])
            except (KeyError, ValueError, TypeError):
                continue
            yr = int(chosen.get("year", year))
            out.append((loc.id, "employment.unemployment_rate", value, "BLS LAUS", yr))

    return out
