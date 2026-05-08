"""Load curated static JSON datasets and emit metric-value tuples.

Each JSON in ``static/`` is wrapped by a small adapter here that:
  - reads the file once (mtime-cached at module level),
  - matches each location to the right key (state abbr or county FIPS),
  - emits (location_id, metric_key, value, source, year) tuples.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session  # noqa: F401  (kept for parity with API-source signatures)

from ..models.location import GeoLevel, Location

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@lru_cache(maxsize=8)
def _load(name: str) -> dict:
    path = STATIC_DIR / name
    with path.open() as f:
        return json.load(f)


def fetch_taxes(_db: Session, locations: list[Location]) -> list[tuple[int, str, float | None, str, int]]:
    blob = _load("state_taxes.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    data = blob["data"]
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        # Tax data inherits up to state — every location with state_abbr gets it.
        abbr = loc.state_abbr
        if not abbr or abbr not in data:
            continue
        d = data[abbr]
        out.append((loc.id, "tax.income.top_marginal", float(d["top_marginal"]), src, yr))
        out.append((loc.id, "tax.sales.combined_avg", float(d["sales_combined"]), src, yr))
        out.append((loc.id, "tax.estate.has_estate_tax", float(d["estate_or_inherit"]), src, yr))
        # Property tax effective rate from this file is state-level; county-level overrides
        # come from another source (Census ACS).
        if loc.level == GeoLevel.state:
            out.append((loc.id, "tax.property.effective_rate", float(d["property_eff"]), src, yr))
        # Structure stored as text via a separate companion metric (textual values
        # bypass scoring; preserved for display).
        # We store as a numeric proxy too: 0=none, 1=flat, 2=progressive, for sortability.
        struct_num = {"none": 0, "flat": 1, "progressive": 2}.get(d["structure"], None)
        if struct_num is not None:
            out.append((loc.id, "tax.income.flat_or_progressive", float(struct_num), src, yr))
    return out


def fetch_climate(_db: Session, locations: list[Location]) -> list[tuple[int, str, float | None, str, int]]:
    blob = _load("state_climate.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    data = blob["data"]
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        abbr = loc.state_abbr
        if not abbr or abbr not in data:
            continue
        d = data[abbr]
        out.append((loc.id, "climate.jan_low_f", float(d["jan_low_f"]), src, yr))
        out.append((loc.id, "climate.jul_high_f", float(d["jul_high_f"]), src, yr))
        out.append((loc.id, "climate.annual_precip_in", float(d["annual_precip_in"]), src, yr))
    return out


def fetch_rpp(_db: Session, locations: list[Location]) -> list[tuple[int, str, float | None, str, int]]:
    blob = _load("state_rpp.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    data = blob["data"]
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        abbr = loc.state_abbr
        if not abbr or abbr not in data:
            continue
        out.append((loc.id, "col.rpp", float(data[abbr]), src, yr))
    return out


def fetch_fema(_db: Session, locations: list[Location]) -> list[tuple[int, str, float | None, str, int]]:
    state_blob = _load("state_fema_nri.json")
    src, yr = state_blob["_meta"]["source"], int(state_blob["_meta"]["source_year"])
    state_data = state_blob["data"]

    # Optional county-level overlay
    county_data: dict[str, float] = {}
    county_path = STATIC_DIR / "county_fema_nri.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {k: float(v) for k, v in cb.get("data", {}).items()}
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_fema_nri.json: %s", e)

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            out.append((loc.id, "hazard.fema_nri", county_data[loc.geoid], src, yr))
            continue
        abbr = loc.state_abbr
        if abbr and abbr in state_data:
            out.append((loc.id, "hazard.fema_nri", float(state_data[abbr]), src, yr))
    return out
