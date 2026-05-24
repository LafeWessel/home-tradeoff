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
    state_src, state_yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    state_data = blob["data"]

    # County-level normals (tmax July, tmin January, pcpn annual) from NClimDiv
    county_climate: dict[str, dict[str, float]] = {}
    county_src, county_yr = state_src, state_yr
    county_path = STATIC_DIR / "county_climate.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_climate = cb.get("data", {})
            county_src = cb["_meta"].get("source", state_src)
            county_yr = int(cb["_meta"].get("source_year", state_yr))
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_climate.json: %s", e)

    # Fields available at county level
    COUNTY_FIELDS: dict[str, str] = {
        "jan_low_f": "climate.jan_low_f",
        "jul_high_f": "climate.jul_high_f",
        "annual_precip_in": "climate.annual_precip_in",
        "annual_snowfall_in": "climate.annual_snowfall_in",
        "avg_wind_speed_mph": "climate.avg_wind_speed_mph",
        "annual_sunny_days": "climate.annual_sunny_days",
    }
    # Fields available at state level only (no county source exists)
    STATE_ONLY_FIELDS: dict[str, str] = {}

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        abbr = loc.state_abbr
        if not abbr or abbr not in state_data:
            continue
        sd = state_data[abbr]

        # County-enhanced metrics: 3-tier county→place-parent-county→state
        for field, metric_key in COUNTY_FIELDS.items():
            county_row: dict[str, float] | None = None
            if loc.level == GeoLevel.county and loc.geoid in county_climate:
                county_row = county_climate[loc.geoid]
            elif loc.level == GeoLevel.place and loc.state_fips and loc.county_fips:
                county_row = county_climate.get(loc.state_fips + loc.county_fips)

            if county_row is not None and field in county_row:
                out.append((loc.id, metric_key, float(county_row[field]), county_src, county_yr))
            else:
                out.append((loc.id, metric_key, float(sd[field]), state_src, state_yr))

        # State-only metrics
        for field, metric_key in STATE_ONLY_FIELDS.items():
            out.append((loc.id, metric_key, float(sd[field]), state_src, state_yr))

    return out


def fetch_rpp(_db: Session, locations: list[Location]) -> list[tuple[int, str, float | None, str, int]]:
    state_blob = _load("state_rpp.json")
    state_src, state_yr = state_blob["_meta"]["source"], int(state_blob["_meta"]["source_year"])
    state_data = state_blob["data"]

    county_data: dict[str, float] = {}
    county_src, county_yr = state_src, state_yr
    county_path = STATIC_DIR / "county_rpp.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {k: float(v) for k, v in cb.get("data", {}).items()}
            county_src = cb["_meta"].get("source", state_src)
            county_yr = int(cb["_meta"].get("source_year", state_yr))
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_rpp.json: %s", e)

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            out.append((loc.id, "col.rpp", county_data[loc.geoid], county_src, county_yr))
        elif loc.level == GeoLevel.place and loc.state_fips and loc.county_fips:
            county_geoid = loc.state_fips + loc.county_fips
            if county_geoid in county_data:
                out.append((loc.id, "col.rpp", county_data[county_geoid], county_src, county_yr))
            elif loc.state_abbr and loc.state_abbr in state_data:
                out.append((loc.id, "col.rpp", float(state_data[loc.state_abbr]), state_src, state_yr))
        elif loc.state_abbr and loc.state_abbr in state_data:
            out.append((loc.id, "col.rpp", float(state_data[loc.state_abbr]), state_src, state_yr))
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
    blob = _load("state_housing_appreciation.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    state_data = blob["data"]

    county_data: dict[str, float] = {}
    county_path = STATIC_DIR / "county_housing_appreciation.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {k: float(v) for k, v in cb.get("data", {}).items()}
            src = cb["_meta"].get("source", src)
            yr = int(cb["_meta"].get("source_year", yr))
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_housing_appreciation.json: %s", e)

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            out.append((loc.id, "housing.appreciation_10yr_cagr", county_data[loc.geoid], src, yr))
        elif loc.level == GeoLevel.place and loc.state_fips and loc.county_fips:
            county_geoid = loc.state_fips + loc.county_fips
            if county_geoid in county_data:
                out.append((loc.id, "housing.appreciation_10yr_cagr", county_data[county_geoid], src, yr))
            elif loc.state_abbr and loc.state_abbr in state_data:
                out.append((loc.id, "housing.appreciation_10yr_cagr", float(state_data[loc.state_abbr]), src, yr))
        elif loc.state_abbr and loc.state_abbr in state_data:
            out.append((loc.id, "housing.appreciation_10yr_cagr", float(state_data[loc.state_abbr]), src, yr))
    return out


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
    blob = _load("state_pm25.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    state_data = blob["data"]

    county_data: dict[str, float] = {}
    county_path = STATIC_DIR / "county_pm25.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {k: float(v) for k, v in cb.get("data", {}).items()}
            src = cb["_meta"].get("source", src)
            yr = int(cb["_meta"].get("source_year", yr))
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_pm25.json: %s", e)

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            out.append((loc.id, "env.pm25_annual", county_data[loc.geoid], src, yr))
        elif loc.level == GeoLevel.place and loc.state_fips and loc.county_fips:
            county_geoid = loc.state_fips + loc.county_fips
            if county_geoid in county_data:
                out.append((loc.id, "env.pm25_annual", county_data[county_geoid], src, yr))
            elif loc.state_abbr and loc.state_abbr in state_data:
                out.append((loc.id, "env.pm25_annual", float(state_data[loc.state_abbr]), src, yr))
        elif loc.state_abbr and loc.state_abbr in state_data:
            out.append((loc.id, "env.pm25_annual", float(state_data[loc.state_abbr]), src, yr))
    return out


def fetch_heat_index(_db: Session, locations: list[Location]):
    return _state_keyed_simple("state_heat_index.json", "climate.summer_heat_index_f", locations)


def _fetch_county_scalar(
    state_file: str,
    state_field: str,
    county_file: str,
    metric_key: str,
    locations: list[Location],
) -> list[tuple[int, str, float | None, str, int]]:
    """3-tier county→place-parent-county→state loader for a single scalar metric."""
    blob = _load(state_file)
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    state_data: dict[str, dict] = blob["data"]

    county_data: dict[str, float] = {}
    county_path = STATIC_DIR / county_file
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {k: float(v) for k, v in cb.get("data", {}).items()}
            src = cb["_meta"].get("source", src)
            yr = int(cb["_meta"].get("source_year", yr))
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load %s: %s", county_file, e)

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            out.append((loc.id, metric_key, county_data[loc.geoid], src, yr))
        elif loc.level == GeoLevel.place and loc.state_fips and loc.county_fips:
            county_geoid = loc.state_fips + loc.county_fips
            if county_geoid in county_data:
                out.append((loc.id, metric_key, county_data[county_geoid], src, yr))
            elif loc.state_abbr and loc.state_abbr in state_data:
                out.append((loc.id, metric_key, float(state_data[loc.state_abbr][state_field]), src, yr))
        elif loc.state_abbr and loc.state_abbr in state_data:
            out.append((loc.id, metric_key, float(state_data[loc.state_abbr][state_field]), src, yr))
    return out


def fetch_utilities(_db: Session, locations: list[Location]):
    electricity = _fetch_county_scalar(
        "state_utilities.json", "electricity_cents_kwh",
        "county_electricity.json", "utility.electricity_rate",
        locations,
    )
    broadband = _fetch_county_scalar(
        "state_utilities.json", "broadband_100_20_pct",
        "county_broadband.json", "infra.broadband_100_20_pct",
        locations,
    )
    return electricity + broadband


def fetch_education(_db: Session, locations: list[Location]):
    return _state_keyed_simple("state_education.json", "edu.k12_proficiency_pct", locations)


def fetch_homeschool_voucher(_db: Session, locations: list[Location]) -> list[tuple[int, str, float | None, str, int]]:
    blob = _load("state_homeschool_voucher.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    data = blob["data"]
    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        abbr = loc.state_abbr
        if not abbr or abbr not in data:
            continue
        d = data[abbr]
        out.append((loc.id, "edu.homeschool_regulation_level", float(d["homeschool_regulation"]), src, yr))
        out.append((loc.id, "edu.school_voucher_program", float(d["school_voucher_program"]), src, yr))
    return out


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
    blob = _load("state_growth.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    state_data = blob["data"]

    county_data: dict[str, dict[str, float]] = {}
    county_path = STATIC_DIR / "county_growth.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {k: v for k, v in cb.get("data", {}).items() if isinstance(v, dict)}
            src = cb["_meta"].get("source", src)
            yr = int(cb["_meta"].get("source_year", yr))
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_growth.json: %s", e)

    fields = {
        "pop_growth_5yr_pct": "pop.growth_5yr_pct",
        "job_growth_5yr_pct": "employment.job_growth_5yr_pct",
    }

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            d = county_data[loc.geoid]
            for field, metric_key in fields.items():
                v = d.get(field)
                if v is not None:
                    out.append((loc.id, metric_key, float(v), src, yr))
        elif loc.level == GeoLevel.place and loc.state_fips and loc.county_fips:
            county_geoid = loc.state_fips + loc.county_fips
            if county_geoid in county_data:
                d = county_data[county_geoid]
                for field, metric_key in fields.items():
                    v = d.get(field)
                    if v is not None:
                        out.append((loc.id, metric_key, float(v), src, yr))
            elif loc.state_abbr and loc.state_abbr in state_data:
                d = state_data[loc.state_abbr]
                for field, metric_key in fields.items():
                    v = d.get(field)
                    if v is not None:
                        out.append((loc.id, metric_key, float(v), src, yr))
        elif loc.state_abbr and loc.state_abbr in state_data:
            d = state_data[loc.state_abbr]
            for field, metric_key in fields.items():
                v = d.get(field)
                if v is not None:
                    out.append((loc.id, metric_key, float(v), src, yr))
    return out


def fetch_politics(_db: Session, locations: list[Location]):
    blob = _load("state_politics.json")
    src, yr = blob["_meta"]["source"], int(blob["_meta"]["source_year"])
    state_data = blob["data"]

    county_data: dict[str, float] = {}
    county_path = STATIC_DIR / "county_politics.json"
    if county_path.exists():
        try:
            cb = json.loads(county_path.read_text())
            county_data = {k: float(v) for k, v in cb.get("data", {}).items()}
            src = cb["_meta"].get("source", src)
            yr = int(cb["_meta"].get("source_year", yr))
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to load county_politics.json: %s", e)

    out: list[tuple[int, str, float | None, str, int]] = []
    for loc in locations:
        if loc.level == GeoLevel.county and loc.geoid in county_data:
            out.append((loc.id, "politics.partisan_lean_2024", county_data[loc.geoid], src, yr))
        elif loc.level == GeoLevel.place and loc.state_fips and loc.county_fips:
            county_geoid = loc.state_fips + loc.county_fips
            if county_geoid in county_data:
                out.append((loc.id, "politics.partisan_lean_2024", county_data[county_geoid], src, yr))
            elif loc.state_abbr and loc.state_abbr in state_data:
                out.append((loc.id, "politics.partisan_lean_2024", float(state_data[loc.state_abbr]), src, yr))
        elif loc.state_abbr and loc.state_abbr in state_data:
            out.append((loc.id, "politics.partisan_lean_2024", float(state_data[loc.state_abbr]), src, yr))
    return out


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
