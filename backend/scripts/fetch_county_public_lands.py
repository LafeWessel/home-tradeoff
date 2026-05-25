"""Fetch county-level public land percentage from PAD-US 3.0 + Census TIGER.

Sources:
  - PAD-US 3.0 Vector Analysis & Summary Statistics (USGS ScienceBase)
    https://www.sciencebase.gov/catalog/item/6196b9ffd34eb622f691aca7
    File: PADUS3_0_SummaryStatistics_TabularData_CSV.zip
  - Census TIGERweb for county AREALAND (sq meters)

Method:
  1. Download PAD-US county CSV.
  2. Sum GIS_AcrsDb for each county where MngTp_Desc in the "public" set
     (Federal, State, Joint, Tribal, Regional Agency Special District).
  3. Fetch county land areas (sq m) from TIGERweb; convert to acres.
  4. Compute public_pct = public_acres / total_acres * 100, clamped to [0, 100].

Output:
    app/sources/static/county_public_lands.json
    Keys: 5-digit county FIPS
    Values: % of county land area that is publicly managed (Federal + State + allied)
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

import requests

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_public_lands.json"

PADUS_ZIP_URL = (
    "https://www.sciencebase.gov/catalog/file/get/6196b9ffd34eb622f691aca7"
    "?f=__disk__68%2F05%2F4d%2F68054dda18ccf4e1cfea0b43e5d9fcf06e40ed69"
)
PADUS_CSV_NAME = "PADUS3_0VectorAnalysis_Counties_Clip_CENSUS2020.csv"

TIGERWEB_COUNTIES = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "State_County/MapServer/1/query"
)

# Management types counted as "public land"
PUBLIC_TYPES = {"Federal", "State", "Joint", "Tribal", "Regional Agency Special District"}

SOURCE_YEAR = 2020


def _fetch_padus_acres() -> dict[str, float]:
    """Returns {5-digit-fips: public_acres}."""
    print("Downloading PAD-US 3.0 county statistics CSV…", file=sys.stderr)
    r = requests.get(PADUS_ZIP_URL, timeout=300, stream=True)
    r.raise_for_status()
    raw = b"".join(r.iter_content(chunk_size=1 << 20))
    print(f"  downloaded {len(raw) // 1024} KB", file=sys.stderr)

    public: dict[str, float] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        with zf.open(PADUS_CSV_NAME) as fh:
            text = fh.read().decode("utf-8-sig")  # strip BOM
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                mng = row.get("MngTp_Desc", "").strip()
                if mng not in PUBLIC_TYPES:
                    continue
                fips = (row.get("BndryID") or "").strip().zfill(5)
                if len(fips) != 5:
                    continue
                try:
                    acres = float(row.get("GIS_AcrsDb") or 0)
                except (ValueError, TypeError):
                    continue
                public[fips] = public.get(fips, 0.0) + acres

    print(f"  {len(public)} counties have public land acres", file=sys.stderr)
    return public


def _fetch_county_land_area() -> dict[str, float]:
    """Returns {5-digit-fips: land_area_acres} from TIGERweb."""
    print("Fetching county land areas from TIGERweb…", file=sys.stderr)
    areas: dict[str, float] = {}
    offset = 0
    page_size = 2000
    sq_m_per_acre = 4046.8564224

    while True:
        params = {
            "where": "STATE IS NOT NULL",
            "outFields": "STATE,COUNTY,AREALAND",
            "f": "json",
            "returnGeometry": "false",
            "resultOffset": str(offset),
            "resultRecordCount": str(page_size),
        }
        r = requests.get(TIGERWEB_COUNTIES, params=params, timeout=120)
        r.raise_for_status()
        d = r.json()
        feats = d.get("features", [])
        for f in feats:
            a = f.get("attributes", {})
            state = (a.get("STATE") or "").zfill(2)
            county = (a.get("COUNTY") or "").zfill(3)
            aland = a.get("AREALAND")
            if state and county and aland:
                fips = state + county
                areas[fips] = float(aland) / sq_m_per_acre
        if not d.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
        print(f"  fetched {offset} counties…", file=sys.stderr)

    print(f"  {len(areas)} county land areas fetched", file=sys.stderr)
    return areas


def main() -> None:
    public_acres = _fetch_padus_acres()
    county_areas = _fetch_county_land_area()

    data: dict[str, float] = {}
    for fips, pub in public_acres.items():
        total = county_areas.get(fips)
        if not total or total <= 0:
            continue
        pct = min(round(pub / total * 100, 2), 100.0)
        data[fips] = pct

    # Counties with zero public land recorded get 0.0
    for fips in county_areas:
        if fips not in data:
            data[fips] = 0.0

    out = {
        "_meta": {
            "source": "PAD-US 3.0 (USGS) — Federal, State, Tribal, Joint, Regional Agency land",
            "source_url": "https://www.sciencebase.gov/catalog/item/6196b9ffd34eb622f691aca7",
            "source_year": SOURCE_YEAR,
            "notes": (
                "Public land = Federal + State + Joint + Tribal + Regional Agency Special District. "
                "Denominator = county AREALAND from Census TIGERweb (land only, no water). "
                "PAD-US 3.0 clipped to Census 2020 county boundaries."
            ),
        },
        "data": dict(sorted(data.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(data)} counties → {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
