#!/usr/bin/env python3
"""Generate county_housing_appreciation.json from FHFA All-Transactions County HPI.

Downloads the public FHFA county-level HPI Excel file (no auth required), then
computes the 10-year compound annual growth rate (CAGR) for each county using
the index levels for the most recent year and 10 years prior.

Usage:
    cd backend && python -m scripts.fetch_county_appreciation [--years 10]

Output:
    app/sources/static/county_housing_appreciation.json
    Keys: 5-digit county FIPS (e.g. "06037" = Los Angeles County)
    Values: 10-year CAGR as a percentage (e.g. 5.2 = 5.2%/yr)
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_housing_appreciation.json"

FHFA_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx"


def _download(url: str) -> bytes:
    try:
        import requests
    except ImportError:
        sys.exit("Install requests: pip install requests")
    log.info("Downloading %s ...", url)
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    log.info("  Downloaded %d kB", len(r.content) // 1024)
    return r.content


def _parse_hpi(xlsx_bytes: bytes) -> dict[str, dict[int, float]]:
    """Return {5-digit-fips: {year: index_value}} from FHFA county HPI xlsx.

    FHFA hpi_at_county.xlsx column layout (A–H, 0-indexed):
      0: state (2-letter abbreviation)
      1: county name
      2: county FIPS code (5-digit)
      3: year
      4: annual change (%)
      5: index, base=100 at first record
      6: index, base=100 in 1990
      7: index, base=100 in 2000

    Rows 0–3 are metadata/description; data starts at row 4.
    Missing values are represented as "." or empty.
    """
    try:
        import openpyxl
    except ImportError:
        sys.exit("Install openpyxl: pip install openpyxl")

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    ws = wb.active

    # Skip metadata rows; find first row where col C is a 5-digit FIPS integer
    DATA_START_SCAN = 10  # scan first 10 rows to find data start
    all_rows = list(ws.iter_rows(values_only=True))

    data_start = 4  # default
    for i, row in enumerate(all_rows[:DATA_START_SCAN]):
        fips_cell = row[2] if len(row) > 2 else None
        try:
            fips_int = int(str(fips_cell).strip())
            if 1000 <= fips_int <= 99999:  # plausible 5-digit FIPS
                data_start = i
                log.info("Data starts at row %d (FIPS=%s)", i, fips_cell)
                break
        except (TypeError, ValueError):
            continue

    # Column indices (0-based): state=0, county_name=1, fips=2, year=3, change=4, idx=5
    FIPS_COL = 2
    YR_COL = 3
    IDX_COL = 7  # prefer base-2000 index (most complete); fallback to col 6 then 5

    # county FIPS → {year: index}
    data: dict[str, dict[int, float]] = {}
    skipped = 0
    for row in all_rows[data_start:]:
        if row is None or all(c is None for c in row):
            continue
        try:
            fips_raw = str(row[FIPS_COL]).strip()
            fips = fips_raw.zfill(5)
            if not fips.isdigit() or fips == "00000":
                skipped += 1
                continue
            yr = int(float(str(row[YR_COL]).strip()))
            # Try preferred index columns in order
            idx = None
            for col in (IDX_COL, 6, 5):
                v = row[col] if len(row) > col else None
                v_str = str(v).strip() if v is not None else ""
                if v_str and v_str != "." and v_str.lower() != "none":
                    idx = float(v_str)
                    break
            if idx is None or idx <= 0:
                skipped += 1
                continue
        except (TypeError, ValueError, IndexError):
            skipped += 1
            continue
        data.setdefault(fips, {})[yr] = idx

    log.info("Parsed %d county-year observations (%d skipped)", sum(len(v) for v in data.values()), skipped)
    return data


def _compute_cagr(
    county_years: dict[str, dict[int, float]],
    n_years: int,
) -> dict[str, float]:
    """Compute n-year CAGR for each county using HPI index levels."""
    most_recent = max(yr for years in county_years.values() for yr in years)
    base_year = most_recent - n_years
    log.info("Computing %d-yr CAGR: %d → %d", n_years, base_year, most_recent)

    out: dict[str, float] = {}
    missing_base = 0
    for fips, years in county_years.items():
        end_val = years.get(most_recent)
        start_val = years.get(base_year)
        if end_val is None or start_val is None or start_val <= 0:
            missing_base += 1
            continue
        cagr_pct = ((end_val / start_val) ** (1.0 / n_years) - 1.0) * 100.0
        out[fips] = round(cagr_pct, 2)

    log.info(
        "CAGR computed for %d counties (%d skipped — missing base or end year)",
        len(out), missing_base,
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=10, help="CAGR window in years (default 10)")
    args = parser.parse_args()

    xlsx_bytes = _download(FHFA_URL)
    county_years = _parse_hpi(xlsx_bytes)

    if not county_years:
        sys.exit("No county HPI data parsed from the FHFA file.")

    cagr = _compute_cagr(county_years, args.years)

    most_recent = max(yr for years in county_years.values() for yr in years)
    base_year = most_recent - args.years

    out = {
        "_meta": {
            "source": "FHFA All-Transactions House Price Index (county, developmental)",
            "source_year": most_recent,
            "notes": (
                f"{args.years}-year CAGR of FHFA all-transactions HPI "
                f"({base_year}→{most_recent}). "
                "Not seasonally adjusted. Counties with missing base or end year excluded; "
                "those fall back to state value."
            ),
        },
        "data": dict(sorted(cagr.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    log.info("Wrote %d counties → %s", len(cagr), OUT_FILE)


if __name__ == "__main__":
    main()
