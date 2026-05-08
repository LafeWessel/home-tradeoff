"""Distance to nearest FAA large-hub airport.

Computes great-circle distance (haversine, miles) from each location's
centroid to the nearest large-hub airport in ``static/airports_large_hubs.json``.
States have lat/lon set in seed_data; counties/places without coordinates are
silently skipped (the resolver will cascade up to the state value).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session  # noqa: F401  (parity with other sources)

from ..models.location import Location

_STATIC = Path(__file__).resolve().parent / "static"
EARTH_RADIUS_MI = 3958.7613


@lru_cache(maxsize=1)
def _hubs() -> tuple[list[tuple[str, float, float]], str, int]:
    blob = json.loads((_STATIC / "airports_large_hubs.json").read_text())
    rows = [(a["code"], float(a["lat"]), float(a["lon"])) for a in blob["airports"]]
    return rows, blob["_meta"]["source"], int(blob["_meta"]["source_year"])


def _haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def fetch_for_locations(
    _db: Session, locations: list[Location]
) -> list[tuple[int, str, float | None, str, int]]:
    hubs, src, yr = _hubs()
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.lat is None or loc.lon is None:
            continue
        best = min(_haversine_mi(loc.lat, loc.lon, hlat, hlon) for _, hlat, hlon in hubs)
        out.append((loc.id, "infra.airport_hub_distance_mi", round(best, 1), src, yr))
    return out
