"""Fetch county-level named summit count.

Primary source: USGS Geographic Names Information System (GNIS) National File
  https://geonames.usgs.gov/docs/stategaz/NationalFile.zip
  Pipe-delimited; filter FEATURE_CLASS == 'Summit'; group by county FIPS.

Fallback (when GNIS is unavailable): OpenStreetMap via Overpass API
  Queries natural=peak nodes per US state bounding box, then assigns each
  peak to a county using Census county polygons (Plotly/Census GeoJSON, ~3MB)
  with a pure-Python ray-casting point-in-polygon test.

Output:
    app/sources/static/county_summits.json
    Keys: 5-digit county FIPS
    Values: count of named summit features in the county
    (Counties absent from this data have 0 named summits.)
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_summits.json"

GNIS_ZIP_URL = "https://geonames.usgs.gov/docs/stategaz/NationalFile.zip"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
COUNTY_GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"

# US state bounding boxes: (min_lat, min_lon, max_lat, max_lon)
STATE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "AL": (30.1, -88.5, 35.0, -84.9), "AK": (51.2, -179.9, 71.4, -129.0),
    "AZ": (31.3, -114.8, 37.0, -109.0), "AR": (33.0, -94.6, 36.5, -89.6),
    "CA": (32.5, -124.5, 42.0, -114.1), "CO": (36.9, -109.1, 41.0, -102.0),
    "CT": (40.9, -73.7, 42.1, -71.8), "DE": (38.4, -75.8, 39.8, -75.0),
    "FL": (24.4, -87.6, 31.0, -80.0), "GA": (30.4, -85.6, 35.0, -80.8),
    "HI": (18.9, -160.2, 22.2, -154.8), "ID": (42.0, -117.2, 49.0, -111.0),
    "IL": (36.9, -91.5, 42.5, -87.5), "IN": (37.8, -88.1, 41.8, -84.8),
    "IA": (40.4, -96.6, 43.5, -90.1), "KS": (37.0, -102.1, 40.0, -94.6),
    "KY": (36.5, -89.6, 39.1, -81.9), "LA": (28.9, -94.0, 33.0, -88.8),
    "ME": (43.1, -71.1, 47.5, -66.9), "MD": (37.9, -79.5, 39.7, -75.0),
    "MA": (41.2, -73.5, 42.9, -69.9), "MI": (41.7, -90.4, 48.3, -82.4),
    "MN": (43.5, -97.2, 49.4, -89.5), "MS": (30.2, -91.7, 35.0, -88.1),
    "MO": (35.9, -95.8, 40.6, -89.1), "MT": (44.4, -116.0, 49.0, -104.0),
    "NE": (40.0, -104.1, 43.0, -95.3), "NV": (35.0, -120.0, 42.0, -114.0),
    "NH": (42.7, -72.6, 45.3, -70.6), "NJ": (38.9, -75.6, 41.4, -73.9),
    "NM": (31.3, -109.1, 37.0, -103.0), "NY": (40.5, -79.8, 45.0, -71.9),
    "NC": (33.8, -84.3, 36.6, -75.5), "ND": (45.9, -104.1, 49.0, -96.6),
    "OH": (38.4, -84.8, 42.3, -80.5), "OK": (33.6, -103.0, 37.0, -94.4),
    "OR": (41.9, -124.6, 46.2, -116.5), "PA": (39.7, -80.5, 42.3, -74.7),
    "RI": (41.1, -71.9, 42.0, -71.1), "SC": (32.0, -83.4, 35.2, -78.5),
    "SD": (42.5, -104.1, 45.9, -96.4), "TN": (34.9, -90.3, 36.7, -81.6),
    "TX": (25.8, -106.7, 36.5, -93.5), "UT": (37.0, -114.1, 42.0, -109.0),
    "VT": (42.7, -73.4, 45.0, -71.5), "VA": (36.5, -83.7, 39.5, -75.2),
    "WA": (45.5, -124.8, 49.0, -116.9), "WV": (37.2, -82.7, 40.6, -77.7),
    "WI": (42.5, -92.9, 47.1, -86.2), "WY": (41.0, -111.1, 45.0, -104.0),
}


# ── GNIS approach ─────────────────────────────────────────────────────────────

def _try_gnis() -> dict[str, int] | None:
    """Returns {fips: summit_count} from GNIS, or None if unavailable."""
    try:
        r = requests.get(GNIS_ZIP_URL, timeout=300, stream=True)
        if r.status_code != 200:
            print(f"  GNIS unavailable (HTTP {r.status_code}), using Overpass fallback", file=sys.stderr)
            return None
        raw = b"".join(r.iter_content(chunk_size=1 << 20))
    except Exception as e:
        print(f"  GNIS error: {e}, using Overpass fallback", file=sys.stderr)
        return None

    print(f"  downloaded {len(raw) // 1024} KB", file=sys.stderr)
    counts: dict[str, int] = defaultdict(int)
    total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not txt_names:
            print("  No .txt in GNIS zip; using fallback", file=sys.stderr)
            return None
        with zf.open(txt_names[0]) as fh:
            reader = csv.DictReader(io.StringIO(fh.read().decode("utf-8-sig")), delimiter="|")
            for row in reader:
                if row.get("FEATURE_CLASS", "").strip() != "Summit":
                    continue
                st = (row.get("STATE_NUMERIC") or "").strip().zfill(2)
                co = (row.get("COUNTY_NUMERIC") or "").strip().zfill(3)
                if not st or not co or st == "00":
                    continue
                counts[st + co] += 1
                total += 1
    print(f"  {total} summits across {len(counts)} counties (GNIS)", file=sys.stderr)
    return dict(counts)


# ── Overpass fallback ──────────────────────────────────────────────────────────

def _fetch_county_polygons() -> list[dict]:
    """Returns list of {fips, bbox, rings} for point-in-polygon tests."""
    print("  Downloading county GeoJSON (~3MB)…", file=sys.stderr)
    req = urllib.request.Request(COUNTY_GEOJSON_URL, headers={"User-Agent": "home-tradeoff/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        fc = json.loads(r.read())

    counties = []
    for feat in fc["features"]:
        fips = feat.get("id") or feat.get("properties", {}).get("FIPS") or feat.get("properties", {}).get("fips")
        if not fips:
            continue
        fips = str(fips).zfill(5)
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            polys = [geom["coordinates"]]
        else:  # MultiPolygon
            polys = geom["coordinates"]

        # Compute overall bounding box
        all_x = [c[0] for poly in polys for ring in poly for c in ring]
        all_y = [c[1] for poly in polys for ring in poly for c in ring]
        bbox = (min(all_x), min(all_y), max(all_x), max(all_y))
        counties.append({"fips": fips, "bbox": bbox, "polys": polys})
    print(f"  {len(counties)} county polygons loaded", file=sys.stderr)
    return counties


def _point_in_ring(x: float, y: float, ring: list) -> bool:
    """Ray-casting point-in-polygon for a single ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _assign_county(lat: float, lon: float, counties: list[dict]) -> str | None:
    """Return 5-digit FIPS for the county containing (lat, lon)."""
    candidates = [
        c for c in counties
        if c["bbox"][0] <= lon <= c["bbox"][2] and c["bbox"][1] <= lat <= c["bbox"][3]
    ]
    for county in candidates:
        for poly in county["polys"]:
            # poly[0] = outer ring, poly[1:] = holes
            if _point_in_ring(lon, lat, poly[0]):
                # Check not in a hole
                in_hole = any(_point_in_ring(lon, lat, h) for h in poly[1:])
                if not in_hole:
                    return county["fips"]
    return None


def _fetch_overpass_peaks(state: str, bbox: tuple) -> list[tuple[float, float]]:
    """Fetch (lat, lon) of all natural=peak nodes in state bounding box."""
    min_lat, min_lon, max_lat, max_lon = bbox
    query = f'[out:json][timeout:60];node["natural"="peak"]({min_lat},{min_lon},{max_lat},{max_lon});out body;'
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": "home-tradeoff/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                d = json.loads(r.read())
            if "remark" in d and "timed out" in d["remark"]:
                raise RuntimeError("timed out")
            return [(e["lat"], e["lon"]) for e in d.get("elements", []) if "lat" in e]
        except Exception as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                print(f"    {state}: Overpass failed after 3 attempts: {e}", file=sys.stderr)
                return []
    return []


def _try_overpass() -> dict[str, int]:
    counties = _fetch_county_polygons()

    all_peaks: list[tuple[float, float]] = []
    print(f"  Fetching peaks from Overpass for {len(STATE_BBOXES)} states…", file=sys.stderr)

    def _fetch(state_bbox):
        state, bbox = state_bbox
        peaks = _fetch_overpass_peaks(state, bbox)
        return state, peaks

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch, item): item[0] for item in STATE_BBOXES.items()}
        for fut in as_completed(futures):
            state, peaks = fut.result()
            all_peaks.extend(peaks)
            if peaks:
                print(f"    {state}: {len(peaks)} peaks", file=sys.stderr)

    print(f"  {len(all_peaks)} total peaks; assigning to counties…", file=sys.stderr)

    counts: dict[str, int] = defaultdict(int)
    unassigned = 0
    for i, (lat, lon) in enumerate(all_peaks):
        fips = _assign_county(lat, lon, counties)
        if fips:
            counts[fips] += 1
        else:
            unassigned += 1
        if (i + 1) % 5000 == 0:
            print(f"    {i+1}/{len(all_peaks)} assigned…", file=sys.stderr)

    print(f"  {len(counts)} counties, {unassigned} peaks unassigned", file=sys.stderr)
    return dict(counts)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Fetching county summit counts…", file=sys.stderr)

    print("Trying GNIS National File…", file=sys.stderr)
    counts = _try_gnis()
    source = "USGS GNIS National File"
    source_url = GNIS_ZIP_URL

    if counts is None:
        print("Falling back to OpenStreetMap Overpass API…", file=sys.stderr)
        counts = _try_overpass()
        source = "OpenStreetMap via Overpass API (natural=peak)"
        source_url = OVERPASS_URL

    out = {
        "_meta": {
            "source": source,
            "source_url": source_url,
            "source_year": 2025,
            "notes": (
                "Count of named summit features per county. "
                "GNIS source counts officially named peaks/mountains/hills per USGS records. "
                "Overpass fallback counts OSM natural=peak nodes. "
                "Counties absent from this data have 0 named summits."
            ),
        },
        "data": dict(sorted(counts.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(counts)} counties → {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
