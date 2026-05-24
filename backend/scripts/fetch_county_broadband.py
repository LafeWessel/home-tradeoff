#!/usr/bin/env python3
"""Generate county_broadband.json from Census ACS internet subscription data.

Uses ACS 5-year estimates table B28002 to compute the share of households with
a broadband internet subscription at the county level.

Note: This measures broadband *subscriptions*, not FCC-style *availability* (which
requires FCC BDC data that needs authentication for bulk download). Subscription
rate is a reasonable county-level proxy: areas with poor broadband infrastructure
have demonstrably lower subscription rates.

Variables used:
  B28002_001E — Total households (universe)
  B28002_004E — With a broadband internet subscription (cable, fiber, DSL, satellite, etc.)

Usage:
    cd backend && python -m scripts.fetch_county_broadband [--year 2023]

Requires CENSUS_API_KEY in backend/.env.

Output:
    app/sources/static/county_broadband.json
    Keys: 5-digit county FIPS
    Values: % of households with broadband subscription (0–100)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_broadband.json"

ACS_BASE = "https://api.census.gov/data/{year}/acs/acs5"

STATE_FIPS = [f"{n:02d}" for n in range(1, 57) if n not in (3, 7, 11, 14, 43, 52)]

TOTAL_VAR = "B28002_001E"
BROADBAND_VAR = "B28002_004E"


def _fetch_county_broadband(year: int, api_key: str) -> dict[str, float]:
    try:
        import requests
    except ImportError:
        sys.exit("Install requests: pip install requests")

    out: dict[str, float] = {}
    for sfips in STATE_FIPS:
        r = requests.get(
            ACS_BASE.format(year=year),
            params={
                "get": f"NAME,{TOTAL_VAR},{BROADBAND_VAR}",
                "for": "county:*",
                "in": f"state:{sfips}",
                "key": api_key,
            },
            timeout=30,
        )
        if not r.ok:
            log.warning("ACS %d: state %s → HTTP %d", year, sfips, r.status_code)
            continue
        rows = r.json()
        headers = rows[0]
        total_idx = headers.index(TOTAL_VAR)
        bb_idx = headers.index(BROADBAND_VAR)
        state_idx = headers.index("state")
        county_idx = headers.index("county")
        for row in rows[1:]:
            try:
                total = int(row[total_idx])
                bb = int(row[bb_idx])
            except (TypeError, ValueError):
                continue
            if total <= 0 or bb < 0:
                continue
            geoid = row[state_idx].zfill(2) + row[county_idx].zfill(3)
            out[geoid] = round(bb / total * 100, 1)

    log.info("ACS %d: broadband subscription rate for %d counties", year, len(out))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2023, help="ACS 5-year vintage year (default 2023)")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.settings import settings  # noqa: PLC0415

    if not settings.census_api_key:
        sys.exit("CENSUS_API_KEY not set — add it to backend/.env")

    data = _fetch_county_broadband(args.year, settings.census_api_key)

    if not data:
        sys.exit(f"No broadband data returned for ACS year {args.year}.")

    out = {
        "_meta": {
            "source": "Census ACS 5-year B28002 (broadband internet subscriptions)",
            "source_year": args.year,
            "notes": (
                f"ACS {args.year} 5-year: share of households (%) with a broadband "
                "internet subscription (cable, fiber optic, DSL, satellite, or other). "
                "Measures subscriptions, not FCC availability; counties without broadband "
                "infrastructure have lower subscription rates. "
                "Counties not returned by ACS fall back to state value."
            ),
        },
        "data": dict(sorted(data.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    log.info("Wrote %d counties → %s", len(data), OUT_FILE)


if __name__ == "__main__":
    main()
