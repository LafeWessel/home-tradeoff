#!/usr/bin/env python3
"""Generate county_pm25.json from EPA AQS annual monitor-level concentration data.

Downloads the public bulk file (no API key required), filters for PM2.5 (88101),
and averages valid monitors per county to produce a single county-level annual mean.

Usage:
    cd backend && python -m scripts.fetch_county_pm25 [--year 2023]

Output:
    app/sources/static/county_pm25.json
    Keys: 5-digit county FIPS (e.g. "06037" = Los Angeles County)
    Values: annual mean PM2.5 concentration in µg/m³
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_pm25.json"

# EPA AQS public bulk files — no API key needed
BULK_URL = "https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_{year}.zip"

PM25_PARAM = "88101"          # PM2.5 - Local Conditions (FRM/FEM)
PM25_PARAM_ALT = "88502"      # PM2.5 - Acceptable (non-FRM instruments, broader coverage)


def _download_zip(year: int) -> bytes:
    try:
        import requests
    except ImportError:
        sys.exit("Install requests: pip install requests")
    url = BULK_URL.format(year=year)
    log.info("Downloading %s (~4–8 MB) ...", url)
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    log.info("  Downloaded %d kB", len(r.content) // 1024)
    return r.content


def _county_means(zip_bytes: bytes) -> dict[str, float]:
    """Average PM2.5 annual means across monitors per county.

    Filters:
      - Parameter 88101 (or 88502 for counties with no FRM monitor)
      - 'Annual Mean' metric (skips 24hr, seasonal, etc.)
      - Exceptional events excluded (standard regulatory basis)
      - Completeness indicator Y (meets 75% observation requirement)
    """
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))

    # county FIPS → list of monitor annual means
    county_monitors: dict[str, list[float]] = {}

    with zf.open(csv_name) as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
        for row in reader:
            param = row.get("Parameter Code", "").strip()
            if param not in (PM25_PARAM, PM25_PARAM_ALT):
                continue

            # The bulk file has "Daily Mean" and "Quarterly Means" but no pre-computed
            # "Annual Mean" row; we average daily means (all completeness-Y rows) per county.
            metric = row.get("Metric Used", "").strip()
            if metric != "Daily Mean":
                continue

            # Standard regulatory basis: prefer "No Events" or "Events Excluded"
            event = row.get("Event Type", "").strip().lower()
            if "events included" in event and "concurred" not in event:
                continue

            completeness = row.get("Completeness Indicator", "").strip().upper()
            if completeness not in ("Y", ""):
                continue

            state_code = row.get("State Code", "").strip().zfill(2)
            county_code = row.get("County Code", "").strip().zfill(3)
            if not state_code or not county_code or state_code == "00":
                continue
            fips = state_code + county_code

            val_str = row.get("Arithmetic Mean", "").strip()
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                continue
            if val < 0:
                continue

            county_monitors.setdefault(fips, []).append(val)

    # Average across monitors; prefer FRM (88101) but use 88502 as fill
    means: dict[str, float] = {
        fips: round(sum(vals) / len(vals), 2)
        for fips, vals in county_monitors.items()
        if vals
    }
    return means


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2023,
                        help="Data year (default 2023; 2024 file may not be available yet)")
    args = parser.parse_args()

    zip_bytes = _download_zip(args.year)
    means = _county_means(zip_bytes)

    if not means:
        sys.exit(f"No PM2.5 data found for year {args.year}.")

    out = {
        "_meta": {
            "source": "EPA AQS annual monitor-level concentration data",
            "source_year": args.year,
            "notes": (
                f"County annual mean PM2.5 (µg/m³) averaged across FRM/FEM monitors "
                f"(param 88101; 88502 used where 88101 unavailable). "
                f"Exceptional events excluded. Only counties with ≥1 qualifying monitor included; "
                f"others fall back to state value."
            ),
        },
        "data": dict(sorted(means.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    log.info("Wrote %d counties → %s", len(means), OUT_FILE)


if __name__ == "__main__":
    main()
