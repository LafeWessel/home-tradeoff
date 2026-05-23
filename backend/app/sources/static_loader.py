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
        out.append((loc.id, "climate.annual_snowfall_in", float(d["annual_snowfall_in"]), src, yr))
        out.append((loc.id, "climate.annual_sunny_days", float(d["annual_sunny_days"]), src, yr))
        out.append((loc.id, "climate.avg_wind_speed_mph", float(d["avg_wind_speed_mph"]), src, yr))
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


# ──────────────────────────────────────────────────────────────────────────
# Generic helpers + the new curated metrics added in 2026-05.
# ──────────────────────────────────────────────────────────────────────────


def _state_keyed_simple(
    file: str, metric_key: str, locations: list[Location]
) -> list[tuple[int, str, float | None, str, int]]:
    """Emit one metric per location from a {state_abbr: scalar} JSON file."""
    blob = _load(file)
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    data = blob["data"]
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        abbr = loc.state_abbr
        if abbr and abbr in data:
            out.append((loc.id, metric_key, float(data[abbr]), src, yr))
    return out


def _state_keyed_multi(
    file: str, field_to_metric: dict[str, str], locations: list[Location]
) -> list[tuple[int, str, float | None, str, int]]:
    """Emit multiple metrics per location from a {state_abbr: {field: scalar, ...}} JSON file."""
    blob = _load(file)
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    data = blob["data"]
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        abbr = loc.state_abbr
        if not abbr or abbr not in data:
            continue
        d = data[abbr]
        for field, metric_key in field_to_metric.items():
            v = d.get(field)
            if v is not None:
                out.append((loc.id, metric_key, float(v), src, yr))
    return out


def fetch_insurance(_db: Session, locations: list[Location]):
    return _state_keyed_simple("state_insurance.json", "housing.insurance_avg_premium", locations)


def fetch_taxes_extra(_db: Session, locations: list[Location]):
    return _state_keyed_multi(
        "state_taxes_extra.json",
        {
            "retirement_burden": "tax.retirement.burden_score",
            "capital_gains_top": "tax.capital_gains.top_rate",
        },
        locations,
    )


def fetch_housing_appreciation(_db: Session, locations: list[Location]):
    return _state_keyed_simple(
        "state_housing_appreciation.json", "housing.appreciation_10yr_cagr", locations
    )


def fetch_nri_components(_db: Session, locations: list[Location]):
    """Hurricane / wildfire / tornado / flood. County overlay if available."""
    state_blob = _load("state_nri_components.json")
    src, yr = state_blob["_meta"]["source"], int(state_blob["_meta"]["source_year"])
    state_data = state_blob["data"]

    county_data: dict[str, dict[str, float]] = {}
    county_path = STATIC_DIR / "county_nri_components.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {
                k: {kk: float(vv) for kk, vv in v.items()}
                for k, v in cb.get("data", {}).items()
            }
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_nri_components.json: %s", e)

    fields = {
        "hurricane": "hazard.hurricane",
        "wildfire": "hazard.wildfire",
        "tornado": "hazard.tornado",
        "flood": "hazard.flood",
    }
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            d = county_data[loc.geoid]
            for f, mk in fields.items():
                if f in d:
                    out.append((loc.id, mk, float(d[f]), src, yr))
            continue
        abbr = loc.state_abbr
        if abbr and abbr in state_data:
            d = state_data[abbr]
            for f, mk in fields.items():
                if f in d:
                    out.append((loc.id, mk, float(d[f]), src, yr))
    return out


def fetch_pm25(_db: Session, locations: list[Location]):
    return _state_keyed_simple("state_pm25.json", "env.pm25_annual", locations)


def fetch_heat_index(_db: Session, locations: list[Location]):
    return _state_keyed_simple("state_heat_index.json", "climate.summer_heat_index_f", locations)


def fetch_utilities(_db: Session, locations: list[Location]):
    return _state_keyed_multi(
        "state_utilities.json",
        {
            "electricity_cents_kwh": "utility.electricity_rate",
            "broadband_100_20_pct": "infra.broadband_100_20_pct",
        },
        locations,
    )


def fetch_education(_db: Session, locations: list[Location]):
    return _state_keyed_simple("state_education.json", "edu.k12_proficiency_pct", locations)


def fetch_health(_db: Session, locations: list[Location]):
    return _state_keyed_multi(
        "state_health.json",
        {
            "primary_care_per_100k": "health.primary_care_per_100k",
            "life_expectancy": "health.life_expectancy_years",
        },
        locations,
    )


def fetch_growth(_db: Session, locations: list[Location]):
    return _state_keyed_multi(
        "state_growth.json",
        {
            "pop_growth_5yr_pct": "pop.growth_5yr_pct",
            "job_growth_5yr_pct": "employment.job_growth_5yr_pct",
        },
        locations,
    )


def fetch_politics(_db: Session, locations: list[Location]):
    return _state_keyed_simple("state_politics.json", "politics.partisan_lean_2024", locations)


def fetch_crime(_db: Session, locations: list[Location]):
    return _state_keyed_multi(
        "state_crime.json",
        {
            "violent_per_100k": "crime.violent_per_100k",
            "property_per_100k": "crime.property_per_100k",
        },
        locations,
    )


def fetch_col_components(_db: Session, locations: list[Location]) -> list[tuple[int, str, float | None, str, int]]:
    """Emit grocery index, childcare cost, and marketplace health premium from state_col_components.json."""
    blob = _load("state_col_components.json")
    out: list[tuple[int, str, float | None, str, int]] = []
    sections = [
        ("grocery_index", "col.grocery_index"),
        ("childcare_infant_annual", "col.childcare_infant_annual"),
        ("healthcare_marketplace_monthly", "col.healthcare_marketplace_monthly"),
    ]
    for field, metric_key in sections:
        section = blob[field]
        src = section["source"]
        yr = int(section["source_year"])
        data = section["data"]
        for loc in locations:
            abbr = loc.state_abbr
            if abbr and abbr in data:
                out.append((loc.id, metric_key, float(data[abbr]), src, yr))
    return out
