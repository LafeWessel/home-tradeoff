"""Fetch county-level adult obesity prevalence from CDC PLACES 2025 release.

Source: CDC PLACES Local Data for Better Health, County Data 2025
        https://data.cdc.gov/resource/swc5-untb.json (Socrata)
Measure: OBESITY — % of adults (age-adjusted) with BMI ≥ 30

Output:
    app/sources/static/county_obesity.json
    Keys: 5-digit county FIPS
    Values: adult obesity prevalence (%)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_obesity.json"

PLACES_URL = "https://data.cdc.gov/resource/swc5-untb.json"
MEASURE_ID = "OBESITY"
PAGE_SIZE = 10_000
SOURCE_YEAR = 2025


def _fetch() -> dict[str, float]:
    try:
        import requests
    except ImportError:
        sys.exit("Install requests: pip install requests")

    print("Fetching CDC PLACES county obesity data…", file=sys.stderr)
    data: dict[str, float] = {}
    offset = 0
    while True:
        params = {
            "$where": f"measureid='{MEASURE_ID}'",
            "$select": "locationid,data_value",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }
        r = requests.get(PLACES_URL, params=params, timeout=60)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        for row in rows:
            fips = (row.get("locationid") or "").strip()
            val = row.get("data_value")
            if len(fips) == 5 and val is not None:
                try:
                    data[fips] = float(val)
                except (ValueError, TypeError):
                    pass
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        print(f"  fetched {offset} rows…", file=sys.stderr)

    return data


def main() -> None:
    data = _fetch()
    if not data:
        sys.exit("No data returned — check the CDC PLACES endpoint or measure ID.")

    out = {
        "_meta": {
            "source": "CDC PLACES: Local Data for Better Health, County Data 2025",
            "source_url": "https://data.cdc.gov/resource/swc5-untb.json",
            "measure": "OBESITY — adults with BMI ≥ 30, age-adjusted %",
            "source_year": SOURCE_YEAR,
        },
        "data": dict(sorted(data.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(data)} counties → {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
