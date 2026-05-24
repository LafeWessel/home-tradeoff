#!/usr/bin/env python3
"""
Build county-level Regional Price Parity (RPP) from BEA data.

Strategy:
  - BEA publishes MSA-level RPP (MARPP) freely at apps.bea.gov/regional/zip/MARPP.zip
  - OMB publishes the county→CBSA delineation file at census.gov (list1_2023.xlsx)
  - For counties IN an MSA/µSA: use that area's RPP
  - For non-metro counties: fall back to state-level RPP from state_rpp.json
  - Uses the most recent year with full coverage (currently 2022)

Output: backend/app/sources/static/county_rpp.json
  Format: {"_meta": {...}, "data": {"FIPS5": 94.5, ...}}
  Value: RPP index (US = 100)
"""

import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import openpyxl

STATIC_DIR = Path(__file__).parent.parent / "app" / "sources" / "static"
STATE_RPP_FILE = STATIC_DIR / "state_rpp.json"
OUT_FILE = STATIC_DIR / "county_rpp.json"

BEA_MARPP_URL = "https://apps.bea.gov/regional/zip/MARPP.zip"
CBSA_DELINEATION_URL = (
    "https://www2.census.gov/programs-surveys/metro-micro/geographies/"
    "reference-files/2023/delineation-files/list1_2023.xlsx"
)

YEAR = "2022"  # Most recent year with full coverage in MARPP


def download(url, label):
    print(f"  Downloading {label}...", end=" ", flush=True)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    print(f"{len(data) // 1024} KB")
    return data


def load_msa_rpp(zip_bytes, year=YEAR) -> dict[str, float]:
    """Parse BEA MARPP.zip → {cbsa_code_5: rpp_value}"""
    msa_rpp = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_name = next(n for n in zf.namelist() if "MARPP_MSA" in n and n.endswith(".csv"))
        with zf.open(csv_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            for row in reader:
                # Filter to LineCode=1 (All items RPP)
                if str(row.get("LineCode", "") or "").strip() != "1":
                    continue
                # GeoFIPS looks like ' "10180"' — strip spaces and quotes
                raw_fips = row.get("GeoFIPS", "").strip().strip('"').strip()
                if len(raw_fips) != 5:
                    continue
                val_str = row.get(year, "").strip()
                if not val_str or val_str in ("(NA)", "(D)", ""):
                    continue
                try:
                    msa_rpp[raw_fips] = float(val_str.replace(",", ""))
                except ValueError:
                    continue
    print(f"  Loaded {len(msa_rpp):,} MSA RPP values for year {year}")
    return msa_rpp


def load_county_cbsa(xlsx_bytes) -> dict[str, str]:
    """Parse OMB CBSA delineation → {county_fips5: cbsa_code5}"""
    county_cbsa = {}
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb.active
    # Data starts at row 4 (rows 1-3 are headers/title)
    for row in ws.iter_rows(min_row=4, values_only=True):
        cbsa_code = row[0]  # col A: CBSA Code
        state_fips = row[9]  # col J: FIPS State Code
        county_fips = row[10]  # col K: FIPS County Code
        if not cbsa_code or not state_fips or not county_fips:
            continue
        cbsa_str = str(int(cbsa_code)).zfill(5)
        state_str = str(int(state_fips)).zfill(2)
        county_str = str(int(county_fips)).zfill(3)
        county_geoid = state_str + county_str
        county_cbsa[county_geoid] = cbsa_str
    print(f"  Loaded {len(county_cbsa):,} county→CBSA mappings")
    return county_cbsa


def load_state_rpp(file: Path) -> dict[str, float]:
    """Load existing state RPP: {state_abbr: rpp}"""
    blob = json.loads(file.read_text())
    return {k: float(v) for k, v in blob["data"].items()}


# State abbreviation → 2-digit FIPS mapping
STATE_ABBR_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "FL": "12", "GA": "13", "HI": "15", "ID": "16",
    "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22",
    "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40",
    "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47",
    "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54",
    "WI": "55", "WY": "56", "DC": "11", "PR": "72",
}
FIPS_TO_ABBR = {v: k for k, v in STATE_ABBR_TO_FIPS.items()}


def main():
    print("Step 1: BEA Metro RPP")
    marpp_bytes = download(BEA_MARPP_URL, "BEA MARPP.zip")
    msa_rpp = load_msa_rpp(marpp_bytes)

    print("Step 2: OMB CBSA delineation")
    delineation_bytes = download(CBSA_DELINEATION_URL, "OMB CBSA delineation xlsx")
    county_cbsa = load_county_cbsa(delineation_bytes)

    print("Step 3: State-level RPP fallback")
    state_rpp = load_state_rpp(STATE_RPP_FILE)
    print(f"  Loaded {len(state_rpp)} state RPP values")

    # Load all known county FIPS from Census county centroids (already cached by snowfall script)
    # We'll build from county_cbsa keys + any county in state_rpp by prefix
    print("Step 4: Build county RPP")
    county_rpp = {}
    msa_count = 0
    state_count = 0
    missing = 0

    # All counties from the delineation file
    for county_fips, cbsa_code in county_cbsa.items():
        state_fips = county_fips[:2]
        state_abbr = FIPS_TO_ABBR.get(state_fips)

        if cbsa_code in msa_rpp:
            county_rpp[county_fips] = round(msa_rpp[cbsa_code], 2)
            msa_count += 1
        elif state_abbr and state_abbr in state_rpp:
            county_rpp[county_fips] = round(state_rpp[state_abbr], 2)
            state_count += 1
        else:
            missing += 1

    # Also fill in counties not in ANY CBSA using state fallback
    # Load all county FIPS from our county_climate.json (all 3,200+ counties)
    climate_path = STATIC_DIR / "county_climate.json"
    if climate_path.exists():
        all_fips = set(json.loads(climate_path.read_text()).get("data", {}).keys())
        for fips in all_fips:
            if fips not in county_rpp:
                state_fips = fips[:2]
                state_abbr = FIPS_TO_ABBR.get(state_fips)
                if state_abbr and state_abbr in state_rpp:
                    county_rpp[fips] = round(state_rpp[state_abbr], 2)
                    state_count += 1
                else:
                    missing += 1

    print(f"  MSA-level: {msa_count:,} counties")
    print(f"  State fallback: {state_count:,} counties")
    print(f"  Missing: {missing}")

    print("Step 5: Write county_rpp.json")
    blob = {
        "_meta": {
            "source": "BEA MARPP (metro) + BEA SARPP (state fallback)",
            "source_year": int(YEAR),
            "note": (
                f"MSA-level RPP from BEA MARPP {YEAR} for counties within CBSAs. "
                "Non-metro counties use state-level RPP. US = 100."
            ),
        },
        "data": county_rpp,
    }
    OUT_FILE.write_text(json.dumps(blob, separators=(",", ":")))
    print(f"  Wrote {len(county_rpp):,} counties to {OUT_FILE}")

    # Spot checks
    samples = [
        ("36061", "Manhattan NY"),
        ("06037", "LA County CA"),
        ("48453", "Travis Co TX"),
        ("30063", "Missoula Co MT"),
        ("38017", "Cass Co ND (Fargo)"),
        ("01001", "Autauga Co AL"),
    ]
    print("\nSpot checks:")
    for fips, name in samples:
        val = county_rpp.get(fips)
        cbsa = county_cbsa.get(fips, "(non-metro)")
        print(f"  {name} ({fips}): RPP={val}  CBSA={cbsa}")


if __name__ == "__main__":
    main()
