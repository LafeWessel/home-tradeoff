"""Fetch county centroid elevation (feet) from USGS 3DEP Elevation Point Query Service.

Source: USGS 3D Elevation Program (3DEP) — National Map EPQS
        https://epqs.nationalmap.gov/v1/json

County centroids: Census 2020 Population Center file
        https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt

This gives the elevation at the county population centroid — a useful proxy for
altitude/mountainousness. It does not capture terrain variability within a county
(e.g. a county spanning both mountains and plains).

Output:
    app/sources/static/county_elevation.json
    Keys: 5-digit county FIPS
    Values: elevation in feet at the population centroid
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_elevation.json"

CENPOP_URL = (
    "https://www2.census.gov/geo/docs/reference/cenpop2020/"
    "county/CenPop2020_Mean_CO.txt"
)
EPQS_URL = "https://epqs.nationalmap.gov/v1/json"

SOURCE_YEAR = 2020
MAX_WORKERS = 20
RETRY_LIMIT = 3


def _load_centroids() -> list[dict[str, str]]:
    r = requests.get(CENPOP_URL, timeout=60)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig")  # strips UTF-8 BOM before parsing
    reader = csv.DictReader(io.StringIO(text))
    counties = []
    for row in reader:
        st = (row.get("STATEFP") or "").strip().zfill(2)
        co = (row.get("COUNTYFP") or "").strip().zfill(3)
        lat = (row.get("LATITUDE") or "").strip().lstrip("+")
        lon = (row.get("LONGITUDE") or "").strip()
        if st and co and lat and lon:
            counties.append({"fips": st + co, "lat": lat, "lon": lon})
    return counties


def _query_elevation(fips: str, lat: str, lon: str) -> tuple[str, float | None]:
    for attempt in range(RETRY_LIMIT):
        try:
            r = requests.get(
                EPQS_URL,
                params={"x": lon, "y": lat, "units": "Feet"},
                timeout=15,
            )
            r.raise_for_status()
            val = r.json().get("value")
            if val is not None:
                return fips, round(float(val), 1)
        except Exception:  # noqa: BLE001
            if attempt < RETRY_LIMIT - 1:
                time.sleep(0.5 * (attempt + 1))
    return fips, None


def main() -> None:
    print("Loading county centroids…", file=sys.stderr)
    centroids = _load_centroids()
    print(f"  {len(centroids)} counties", file=sys.stderr)

    data: dict[str, float] = {}
    errors = 0
    done = 0

    print(f"Querying USGS EPQS with {MAX_WORKERS} workers…", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_query_elevation, c["fips"], c["lat"], c["lon"]): c["fips"]
            for c in centroids
        }
        for fut in as_completed(futures):
            fips, elev = fut.result()
            done += 1
            if elev is not None:
                data[fips] = elev
            else:
                errors += 1
            if done % 500 == 0:
                print(f"  {done}/{len(centroids)} done, {errors} errors…", file=sys.stderr)

    print(f"  complete: {len(data)} elevations, {errors} failed", file=sys.stderr)

    out = {
        "_meta": {
            "source": "USGS 3DEP Elevation Point Query Service — county population centroids",
            "source_url": "https://epqs.nationalmap.gov/v1/json",
            "centroid_source": "Census 2020 County Population Centers",
            "source_year": SOURCE_YEAR,
            "notes": (
                "Elevation at the 2020 Census population centroid of each county. "
                "This is a proxy for typical altitude; it does not capture elevation variability "
                "within the county."
            ),
        },
        "data": dict(sorted(data.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(data)} counties → {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
