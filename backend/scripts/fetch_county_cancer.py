"""Fetch county-level cancer incidence and mortality from NCI State Cancer Profiles.

Source: NCI / CDC State Cancer Profiles
        https://statecancerprofiles.cancer.gov/
Data: All cancer sites, all races, both sexes, all ages — 2018–2022 incidence,
      2019–2023 mortality.  Age-adjusted rates per 100,000 population.

Output:
    app/sources/static/county_cancer.json
    Keys: 5-digit county FIPS
    Values: {incidence_per_100k: float, mortality_per_100k: float}

Notes:
    - Some rural counties are suppressed (< ~16 cases/year); these are omitted.
    - The national aggregate row (FIPS 00000) is excluded.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import requests

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_cancer.json"

INCIDENCE_URL = (
    "https://statecancerprofiles.cancer.gov/incidencerates/index.php"
    "?stateFIPS=00&areatype=county&cancer=001&race=00&sex=0&age=001&type=incd&output=1"
)
MORTALITY_URL = (
    "https://statecancerprofiles.cancer.gov/deathrates/index.php"
    "?stateFIPS=00&areatype=county&cancer=001&race=00&sex=0&age=001&type=death&output=1"
)

INCIDENCE_YEAR = 2022  # 2018–2022 5-year average
MORTALITY_YEAR = 2023  # 2019–2023 5-year average


def _parse_nci_csv(text: str, rate_col_hint: str) -> dict[str, float]:
    """Parse NCI CSV export.  Returns {fips: rate}."""
    lines = text.splitlines()
    # Skip preamble lines until we hit the actual CSV header row.
    # The header starts with "County," (the first field); preamble lines may
    # contain "County" elsewhere (e.g. "Report for United States by County").
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("County,") or ln.startswith('"County",')),
        None,
    )
    if header_idx is None:
        sys.exit(f"Could not find header row in NCI CSV for {rate_col_hint}")

    reader = csv.DictReader(lines[header_idx:])
    data: dict[str, float] = {}
    rate_key = next(
        (k for k in (reader.fieldnames or []) if "Rate" in k or "rate" in k),
        None,
    )
    if rate_key is None:
        sys.exit(f"Could not identify rate column; fields: {reader.fieldnames}")

    for row in reader:
        fips_raw = (row.get("FIPS") or "").strip().strip('"')
        try:
            fips = str(int(fips_raw)).zfill(5)
        except ValueError:
            continue
        if fips == "00000":
            continue
        val_raw = (row.get(rate_key) or "").strip().strip('"').split()[0]
        try:
            data[fips] = float(val_raw)
        except (ValueError, TypeError):
            pass  # suppressed / missing
    return data


def main() -> None:
    print("Fetching NCI incidence rates…", file=sys.stderr)
    r = requests.get(INCIDENCE_URL, timeout=120)
    r.raise_for_status()
    incidence = _parse_nci_csv(r.text, "incidence")
    print(f"  {len(incidence)} counties with incidence data", file=sys.stderr)

    print("Fetching NCI mortality rates…", file=sys.stderr)
    r = requests.get(MORTALITY_URL, timeout=120)
    r.raise_for_status()
    mortality = _parse_nci_csv(r.text, "mortality")
    print(f"  {len(mortality)} counties with mortality data", file=sys.stderr)

    all_fips = sorted(set(incidence) | set(mortality))
    combined: dict[str, dict[str, float]] = {}
    for fips in all_fips:
        rec: dict[str, float] = {}
        if fips in incidence:
            rec["incidence_per_100k"] = incidence[fips]
        if fips in mortality:
            rec["mortality_per_100k"] = mortality[fips]
        if rec:
            combined[fips] = rec

    out = {
        "_meta": {
            "source": "NCI / CDC State Cancer Profiles — All Cancer Sites, All Races, Both Sexes, All Ages",
            "source_url": "https://statecancerprofiles.cancer.gov/",
            "incidence_years": "2018–2022",
            "mortality_years": "2019–2023",
            "source_year": MORTALITY_YEAR,
            "notes": "Age-adjusted rates per 100,000 population. Counties with suppressed data (< ~16 cases/yr) are excluded.",
        },
        "data": combined,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(combined)} counties → {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
