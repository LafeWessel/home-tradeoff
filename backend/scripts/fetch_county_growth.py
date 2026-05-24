#!/usr/bin/env python3
"""Generate county_growth.json with 5-year population and job growth by county.

Data sources:
  pop_growth_5yr_pct  — Census ACS 5yr B01003_001E (2019 vs 2024 vintage)
  job_growth_5yr_pct  — BLS LAUS employed-count series (2019 vs 2024 annual avg)
                        Series ID: LAUCN{state_fips}{county_fips}0000000005

Note: BLS LAUS measures resident-based employment (where workers live), not
establishment-based jobs (where employers are). It is a valid local opportunity
signal and avoids downloading the large BLS QCEW bulk files.

Usage:
    cd backend && python -m scripts.fetch_county_growth

Requires CENSUS_API_KEY in backend/.env.
BLS_API_KEY is optional but raises rate limit from 25 to 500 req/day.
BLS API limit: 50 series per request; ~64 requests per year × 2 years = ~128 calls.

Output:
    app/sources/static/county_growth.json
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_growth.json"

ACS_YEAR_NOW = 2024
ACS_YEAR_PAST = 2019
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


# ---------------------------------------------------------------------------
# Census ACS — county population
# ---------------------------------------------------------------------------

def _acs_county_pop(year: int, api_key: str) -> dict[str, int]:
    """Return {5-digit-geoid: population} from ACS 5yr B01003_001E."""
    import requests

    STATE_FIPS = [
        f"{n:02d}" for n in range(1, 57)
        if n not in (3, 7, 11, 14, 43, 52)
    ]

    out: dict[str, int] = {}
    for sfips in STATE_FIPS:
        r = requests.get(
            f"https://api.census.gov/data/{year}/acs/acs5",
            params={
                "get": "NAME,B01003_001E",
                "for": "county:*",
                "in": f"state:{sfips}",
                "key": api_key,
            },
            timeout=30,
        )
        if not r.ok:
            log.warning("ACS %d county pop: state %s → HTTP %d", year, sfips, r.status_code)
            continue
        rows = r.json()
        headers = rows[0]
        pop_idx = headers.index("B01003_001E")
        state_idx = headers.index("state")
        county_idx = headers.index("county")
        for row in rows[1:]:
            geoid = row[state_idx].zfill(2) + row[county_idx].zfill(3)
            try:
                out[geoid] = int(row[pop_idx])
            except (TypeError, ValueError):
                pass
    log.info("ACS %d: got population for %d counties", year, len(out))
    return out


def fetch_pop_growth(api_key: str) -> dict[str, float]:
    pop_now = _acs_county_pop(ACS_YEAR_NOW, api_key)
    pop_past = _acs_county_pop(ACS_YEAR_PAST, api_key)
    growth: dict[str, float] = {}
    for geoid in pop_now:
        p_now = pop_now.get(geoid)
        p_past = pop_past.get(geoid)
        if p_now is None or p_past is None or p_past == 0:
            continue
        growth[geoid] = round((p_now - p_past) / p_past * 100, 2)
    log.info("Pop growth computed for %d counties", len(growth))
    return growth


# ---------------------------------------------------------------------------
# BLS LAUS — county employment levels
# ---------------------------------------------------------------------------

def _laus_series_id(state_fips: str, county_fips: str) -> str:
    # Employed count series: LAUCN{state}{county}0000000005
    return f"LAUCN{state_fips}{county_fips}0000000005"


def _bls_batch(series_ids: list[str], year: int, bls_key: str | None) -> dict[str, float]:
    """Return {series_id: annual_avg_employment} for up to 50 series."""
    import requests

    body: dict[str, Any] = {
        "seriesid": series_ids,
        "startyear": str(year),
        "endyear": str(year),
        "annualaverage": True,
    }
    if bls_key:
        body["registrationkey"] = bls_key

    r = requests.post(BLS_URL, json=body, timeout=60)
    r.raise_for_status()
    payload = r.json()

    if payload.get("status") != "REQUEST_SUCCEEDED":
        msgs = payload.get("message", [])
        log.warning("BLS API non-success: %s", msgs)

    out: dict[str, float] = {}
    for s in (payload.get("Results") or {}).get("series") or []:
        sid = s.get("seriesID", "")
        data = s.get("data") or []
        annual = next((d for d in data if d.get("period") == "M13"), None)
        chosen = annual or (data[0] if data else None)
        if not chosen:
            continue
        try:
            out[sid] = float(chosen["value"].replace(",", ""))
        except (KeyError, ValueError, TypeError):
            pass
    return out


def _bls_county_employment(
    county_fips_list: list[tuple[str, str]], year: int, bls_key: str | None
) -> dict[str, float]:
    """Return {5-digit-geoid: employed_count} for the given year."""
    series_map: dict[str, str] = {}
    for sfips, cfips in county_fips_list:
        sid = _laus_series_id(sfips, cfips)
        geoid = sfips + cfips
        series_map[sid] = geoid

    out: dict[str, float] = {}
    series_ids = list(series_map.keys())
    total = len(series_ids)
    for i in range(0, total, 50):
        chunk = series_ids[i: i + 50]
        log.info("BLS LAUS %d: batch %d/%d ...", year, i // 50 + 1, (total + 49) // 50)
        try:
            results = _bls_batch(chunk, year, bls_key)
        except Exception as e:  # noqa: BLE001
            log.warning("BLS batch failed: %s", e)
            results = {}
        for sid, emp in results.items():
            geoid = series_map.get(sid)
            if geoid:
                out[geoid] = emp
        # Be polite to the BLS API — no need to hammer it
        if i + 50 < total:
            time.sleep(0.5)
    log.info("BLS LAUS %d: got employment for %d counties", year, len(out))
    return out


def fetch_job_growth(
    county_fips_list: list[tuple[str, str]], bls_key: str | None
) -> dict[str, float]:
    emp_now = _bls_county_employment(county_fips_list, ACS_YEAR_NOW, bls_key)
    emp_past = _bls_county_employment(county_fips_list, ACS_YEAR_PAST, bls_key)
    growth: dict[str, float] = {}
    for geoid in emp_now:
        e_now = emp_now.get(geoid)
        e_past = emp_past.get(geoid)
        if e_now is None or e_past is None or e_past == 0:
            continue
        growth[geoid] = round((e_now - e_past) / e_past * 100, 2)
    log.info("Job growth computed for %d counties", len(growth))
    return growth


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("Install requests: pip install requests")

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.settings import settings  # noqa: PLC0415

    if not settings.census_api_key:
        sys.exit("CENSUS_API_KEY not set — add it to backend/.env")

    if not settings.bls_api_key:
        log.warning(
            "BLS_API_KEY not set — rate-limited to 25 req/day (may fail for large county sets). "
            "Add BLS_API_KEY to backend/.env for 500 req/day."
        )

    # Population growth from ACS
    pop_growth = fetch_pop_growth(settings.census_api_key)

    # Build county FIPS list from pop growth keys (covers all counties we fetched)
    county_fips_list = [(geoid[:2], geoid[2:]) for geoid in pop_growth]

    # Job growth from BLS LAUS
    job_growth = fetch_job_growth(county_fips_list, settings.bls_api_key)

    all_fips = sorted(set(pop_growth) | set(job_growth))
    data: dict[str, dict[str, float | None]] = {}
    for fips in all_fips:
        data[fips] = {
            "pop_growth_5yr_pct": pop_growth.get(fips),
            "job_growth_5yr_pct": job_growth.get(fips),
        }

    out = {
        "_meta": {
            "source": "Census ACS 5yr (pop) / BLS LAUS (jobs)",
            "source_year": ACS_YEAR_NOW,
            "notes": (
                f"5-year growth {ACS_YEAR_PAST}→{ACS_YEAR_NOW}. "
                "pop: ACS B01003_001E total population; "
                "jobs: BLS LAUS employed-count (resident-based, annual avg)."
            ),
        },
        "data": data,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    log.info("Wrote %d counties → %s", len(data), OUT_FILE)


if __name__ == "__main__":
    main()
