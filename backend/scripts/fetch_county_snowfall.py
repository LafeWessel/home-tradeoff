#!/usr/bin/env python3
"""
Fetch county-level annual snowfall normals (1991-2020) from NCEI bulk archive.

Process:
1. Download GHCN station inventory (lat/lon for all stations)
2. Download Census county population centroids (lat/lon per county FIPS)
3. Download the 54MB annual/seasonal normals tar.gz from NCEI
4. Parse each station CSV for ANN-SNOW-NORMAL
5. Map each station to nearest county centroid
6. Median-aggregate per county
7. Merge into existing county_climate.json

Output: backend/app/sources/static/county_climate.json
  - Adds "annual_snowfall_in" field per county FIPS
"""

import csv
import io
import json
import math
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

STATIC_DIR = Path(__file__).parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_climate.json"

STATION_INVENTORY_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"
COUNTY_CENTROIDS_URL = (
    "https://www2.census.gov/geo/docs/reference/cenpop2020/county/"
    "CenPop2020_Mean_CO.txt"
)
NORMALS_ARCHIVE_URL = (
    "https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/archive/"
    "us-climate-normals_1991-2020_v1.0.1_annualseasonal_multivariate_by-station_c20230404.tar.gz"
)

MISSING_SENTINEL = -9999.0


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def download(url, label, dest=None):
    print(f"  Downloading {label}...", end=" ", flush=True)
    if dest and dest.exists():
        print("(cached)")
        return dest.read_bytes()
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    print(f"{len(data) // 1024} KB")
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return data


def load_station_inventory(data_bytes):
    """Parse ghcnd-stations.txt fixed-width: ID(0:11), lat(12:20), lon(21:30), elev(31:37), name(41:71)"""
    stations = {}
    for line in data_bytes.decode("latin-1").splitlines():
        if len(line) < 30:
            continue
        sid = line[0:11].strip()
        if not sid.startswith("US"):
            continue
        try:
            lat = float(line[12:20])
            lon = float(line[21:30])
        except ValueError:
            continue
        stations[sid] = (lat, lon)
    print(f"  Loaded {len(stations):,} US stations from inventory")
    return stations


def load_county_centroids(data_bytes):
    """Parse CenPop2020_Mean_CO.txt CSV: STATEFP, COUNTYFP, COUNAME, STNAME, POPULATION, LATITUDE, LONGITUDE"""
    counties = {}
    reader = csv.DictReader(io.StringIO(data_bytes.decode("utf-8-sig")))
    for row in reader:
        fips = row["STATEFP"].zfill(2) + row["COUNTYFP"].zfill(3)
        try:
            lat = float(row["LATITUDE"])
            lon = float(row["LONGITUDE"])
        except (KeyError, ValueError):
            continue
        counties[fips] = (lat, lon)
    print(f"  Loaded {len(counties):,} county centroids")
    return counties


def build_county_index(counties):
    """Build sorted lat/lon list for nearest-county lookup."""
    # Returns list of (lat, lon, fips)
    return [(lat, lon, fips) for fips, (lat, lon) in counties.items()]


def nearest_county(lat, lon, county_list):
    """Find nearest county centroid by haversine distance."""
    best_fips = None
    best_d = float("inf")
    for clat, clon, fips in county_list:
        # Cheap bounding box pre-filter (1 degree ≈ 111 km)
        if abs(clat - lat) > 3 or abs(clon - lon) > 3:
            continue
        d = haversine_km(lat, lon, clat, clon)
        if d < best_d:
            best_d = d
            best_fips = fips
    if best_d > 200:
        return None  # Too far (offshore/territorial station)
    return best_fips


def parse_normals_archive(archive_bytes, station_inventory):
    """Extract ANN-SNOW-NORMAL from each station CSV in the tar.gz archive."""
    snow_by_station = {}
    print("  Parsing station normals archive...", flush=True)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
        members = tar.getmembers()
        print(f"    {len(members):,} files in archive")
        for i, member in enumerate(members):
            if i % 2000 == 0:
                print(f"    {i:,}/{len(members):,} processed...", flush=True)
            if not member.name.endswith(".csv"):
                continue
            # Station ID is the filename without .csv
            fname = member.name.split("/")[-1]
            sid = fname[:-4]
            if sid not in station_inventory:
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            try:
                content = f.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                val_str = row.get("ANN-SNOW-NORMAL", "").strip()
                if not val_str:
                    continue
                try:
                    val = float(val_str)
                except ValueError:
                    continue
                if val < MISSING_SENTINEL + 1:
                    continue
                # Convert tenths of inches to inches if flagged
                # NClimDiv values are already in inches
                snow_by_station[sid] = val
                break  # Only one annual row per station
    print(f"  Found ANN-SNOW-NORMAL for {len(snow_by_station):,} stations")
    return snow_by_station


def main():
    cache_dir = Path("/tmp/ncei_normals_cache")
    cache_dir.mkdir(exist_ok=True)

    print("Step 1: Station inventory")
    inv_bytes = download(
        STATION_INVENTORY_URL, "GHCN station inventory", cache_dir / "ghcnd-stations.txt"
    )
    station_inventory = load_station_inventory(inv_bytes)

    print("Step 2: County centroids")
    cent_bytes = download(
        COUNTY_CENTROIDS_URL, "Census county centroids", cache_dir / "CenPop2020_Mean_CO.txt"
    )
    counties = load_county_centroids(cent_bytes)
    county_list = build_county_index(counties)

    print("Step 3: Annual normals archive")
    archive_path = cache_dir / "annualseasonal_normals.tar.gz"
    archive_bytes = download(NORMALS_ARCHIVE_URL, "NCEI annual normals (54MB)", archive_path)

    print("Step 4: Parse snowfall normals")
    snow_by_station = parse_normals_archive(archive_bytes, station_inventory)

    print("Step 5: Map stations to counties")
    county_snow = {}  # fips -> list of values
    no_county = 0
    for sid, snow_in in snow_by_station.items():
        if sid not in station_inventory:
            continue
        lat, lon = station_inventory[sid]
        fips = nearest_county(lat, lon, county_list)
        if fips is None:
            no_county += 1
            continue
        county_snow.setdefault(fips, []).append(snow_in)
    print(f"  Mapped {len(county_snow):,} counties; {no_county} stations had no county")

    print("Step 6: Aggregate per county (median)")
    county_median = {}
    for fips, vals in county_snow.items():
        vals.sort()
        mid = len(vals) // 2
        county_median[fips] = round(vals[mid], 1)

    print("Step 7: Merge into county_climate.json")
    if OUT_FILE.exists():
        blob = json.loads(OUT_FILE.read_text())
    else:
        blob = {"_meta": {}, "data": {}}

    # Merge: add annual_snowfall_in to each county's dict
    data = blob.get("data", {})
    updated = 0
    for fips, snow in county_median.items():
        if fips not in data:
            data[fips] = {}
        data[fips]["annual_snowfall_in"] = snow
        updated += 1

    # Update meta
    blob["_meta"]["annual_snowfall_in"] = {
        "source": "NOAA NCEI 1991-2020 Normals",
        "source_year": 2020,
        "note": "ANN-SNOW-NORMAL per GHCN station, nearest-county assignment",
    }
    blob["data"] = data
    OUT_FILE.write_text(json.dumps(blob, separators=(",", ":")))

    covered = sum(1 for v in data.values() if "annual_snowfall_in" in v)
    print(f"\nDone. {covered:,} counties have annual_snowfall_in.")
    print(f"Output: {OUT_FILE}")

    # Spot check
    samples = [("06037", "LA County CA"), ("48453", "Travis Co TX"), ("36061", "Manhattan NY"), ("08031", "Denver CO")]
    print("\nSpot checks:")
    for fips, name in samples:
        val = data.get(fips, {}).get("annual_snowfall_in")
        print(f"  {name} ({fips}): {val} in")


if __name__ == "__main__":
    main()
