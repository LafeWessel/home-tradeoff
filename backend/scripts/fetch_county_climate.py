#!/usr/bin/env python3
"""Generate county_climate.json from NOAA NClimDiv county normals.

Downloads three NClimDiv county-level normals files (tmax, tmin, pcpn) and
extracts the 1991-2020 30-year normals (period code 0010) to produce:

  climate.jan_low_f      — January minimum temperature (°F)
  climate.jul_high_f     — July maximum temperature (°F)
  climate.annual_precip_in — Annual precipitation (inches, sum of monthly normals)

NClimDiv file format (fixed-width):
  Chars 0-4:  5-digit county FIPS
  Chars 5-6:  2-digit climate division code (within file, ignored here)
  Chars 7-10: 4-digit period code (0010 = 1991-2020)
  Remainder:  12 monthly values separated by spaces

Note: snowfall, wind speed, and sunny days are NOT available in NClimDiv and
remain at state level.

Usage:
    cd backend && python -m scripts.fetch_county_climate

Output:
    app/sources/static/county_climate.json
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_climate.json"

NCLIMDIV_BASE = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/"
DATE_SUFFIX = "20260506"  # update when NOAA releases newer monthly versions

FILES = {
    "tmax": f"climdiv-norm-tmaxcy-v1.0.0-{DATE_SUFFIX}",
    "tmin": f"climdiv-norm-tmincy-v1.0.0-{DATE_SUFFIX}",
    "pcpn": f"climdiv-norm-pcpncy-v1.0.0-{DATE_SUFFIX}",
}

NORMAL_PERIOD = "0010"  # 1991-2020 (the current WMO 30-year standard)
MISSING_SENTINEL = -99.99  # NClimDiv uses -9.99 or -99.99 for missing values
MISSING_THRESHOLD = -9.0


def _download(url: str) -> str:
    try:
        import requests
    except ImportError:
        sys.exit("Install requests: pip install requests")
    log.info("Downloading %s ...", url)
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    log.info("  Downloaded %d kB", len(r.content) // 1024)
    return r.text


def _parse_normals(text: str, period: str) -> dict[str, list[float]]:
    """Return {county_fips: [jan, feb, ..., dec]} for the given period code."""
    out: dict[str, list[float]] = {}
    skipped = 0
    for line in text.splitlines():
        line = line.rstrip()
        if len(line) < 11:
            continue
        # Fixed-width key: county_fips (0:5), div (5:7), period (7:11)
        fips = line[0:5]
        record_period = line[7:11]
        if record_period != period:
            continue
        # Monthly values follow after the 11-char key
        parts = line[11:].split()
        if len(parts) < 12:
            skipped += 1
            continue
        try:
            vals = [float(p) for p in parts[:12]]
        except ValueError:
            skipped += 1
            continue
        # Filter missing
        if any(v < MISSING_THRESHOLD for v in vals):
            skipped += 1
            continue
        if not fips.isdigit() or fips == "00000":
            skipped += 1
            continue
        out[fips] = vals
    log.info("  Parsed %d county records for period %s (%d skipped)", len(out), period, skipped)
    return out


def main() -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        sys.exit("Install requests: pip install requests")

    log.info("Fetching 1991-2020 normals (period %s) for tmax, tmin, pcpn...", NORMAL_PERIOD)

    tmax_text = _download(NCLIMDIV_BASE + FILES["tmax"])
    tmax = _parse_normals(tmax_text, NORMAL_PERIOD)

    tmin_text = _download(NCLIMDIV_BASE + FILES["tmin"])
    tmin = _parse_normals(tmin_text, NORMAL_PERIOD)

    pcpn_text = _download(NCLIMDIV_BASE + FILES["pcpn"])
    pcpn = _parse_normals(pcpn_text, NORMAL_PERIOD)

    all_fips = sorted(set(tmax) | set(tmin) | set(pcpn))
    log.info("County union: %d FIPS codes", len(all_fips))

    data: dict[str, dict[str, float | None]] = {}
    for fips in all_fips:
        row: dict[str, float | None] = {}
        if fips in tmin:
            row["jan_low_f"] = round(tmin[fips][0], 1)   # January = index 0
        if fips in tmax:
            row["jul_high_f"] = round(tmax[fips][6], 1)   # July = index 6
        if fips in pcpn:
            row["annual_precip_in"] = round(sum(pcpn[fips]), 2)
        if row:
            data[fips] = row

    out = {
        "_meta": {
            "source": "NOAA NClimDiv county normals (1991-2020)",
            "source_year": 2020,
            "notes": (
                "30-year normals (1991-2020, WMO standard period, NClimDiv period code 0010). "
                "jan_low_f = January mean minimum temperature (°F); "
                "jul_high_f = July mean maximum temperature (°F); "
                "annual_precip_in = sum of monthly mean precipitation (inches). "
                "Counties not in NClimDiv (some small counties, territories) fall back to state value."
            ),
        },
        "data": data,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    log.info("Wrote %d counties → %s", len(data), OUT_FILE)


if __name__ == "__main__":
    main()
