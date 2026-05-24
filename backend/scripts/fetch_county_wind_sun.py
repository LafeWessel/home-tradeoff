#!/usr/bin/env python3
"""
Fetch county-level annual average wind speed and sunny days from NCEI hourly
normals (1991-2020).

Variables:
  HLY-WIND-AVGSPD — hourly average wind speed (tenths of mph)
  HLY-CLOD-PCTCLR — percent of hours with clear sky conditions

Process:
1. Load GHCN station inventory (cached by fetch_county_snowfall.py)
2. Load Census county centroids (cached)
3. Download the 220MB NCEI hourly normals by-station tar.gz
4. Per station: average HLY-WIND-AVGSPD across all valid hours → annual mph
5. Per station: average HLY-CLOD-PCTCLR → multiply by 3.65 → annual sunny days
6. Map stations to nearest county centroid
7. Median-aggregate per county
8. Merge both fields into county_climate.json

Output: backend/app/sources/static/county_climate.json
  - Adds "avg_wind_speed_mph" (float, mph)
  - Adds "annual_sunny_days" (float, estimated days/yr with clear skies)
"""

import csv
import io
import json
import math
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
HOURLY_ARCHIVE_URL = (
    "https://www.ncei.noaa.gov/data/normals-hourly/1991-2020/archive/"
    "us-climate-normals_1991-2020_v1.0.0_hourly_multivariate_by-station_c20210423.tar.gz"
)

MISSING_SENTINEL = -9999.0
# HLY-WIND-AVGSPD values are already in mph (confirmed from station file inspection)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_or_download(url, label, cache_path):
    if cache_path.exists():
        print(f"  {label}: cached ({cache_path.stat().st_size // 1024} KB)")
        return cache_path.read_bytes()
    print(f"  Downloading {label}...", end=" ", flush=True)
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    print(f"{len(data) // 1024} KB")
    return data


def load_station_inventory(data_bytes):
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
    print(f"  Loaded {len(stations):,} US stations")
    return stations


def load_county_centroids(data_bytes):
    import io as _io
    counties = {}
    reader = csv.DictReader(_io.StringIO(data_bytes.decode("utf-8-sig")))
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


def nearest_county(lat, lon, county_list):
    best_fips = None
    best_d = float("inf")
    for clat, clon, fips in county_list:
        if abs(clat - lat) > 3 or abs(clon - lon) > 3:
            continue
        d = haversine_km(lat, lon, clat, clon)
        if d < best_d:
            best_d = d
            best_fips = fips
    return best_fips if best_d <= 200 else None


def parse_hourly_archive(archive_path, station_inventory):
    """Stream through the tar.gz, computing per-station averages."""
    wind_by_station = {}   # sid -> mph
    sun_by_station = {}    # sid -> pct_clear (0-100)
    checked_units = False

    print("  Parsing hourly normals archive (this may take a few minutes)...", flush=True)
    with tarfile.open(archive_path, mode="r:gz") as tar:
        members = [m for m in tar.getmembers() if "USW" in m.name]  # first-order only
        print(f"    {len(members):,} station files in archive")
        for i, member in enumerate(members):
            if i % 3000 == 0:
                print(f"    {i:,}/{len(members):,} processed...", flush=True)
            if not member.name.endswith(".csv"):
                continue
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
            wind_vals = []
            clr_vals = []
            few_vals = []
            for row in reader:
                w_str = row.get("HLY-WIND-AVGSPD", "").strip()
                clr_str = row.get("HLY-CLOD-PCTCLR", "").strip()
                few_str = row.get("HLY-CLOD-PCTFEW", "").strip()
                if w_str:
                    try:
                        w = float(w_str)
                        if w > MISSING_SENTINEL + 1:
                            wind_vals.append(w)
                    except ValueError:
                        pass
                if clr_str and few_str:
                    try:
                        c = float(clr_str)
                        fw = float(few_str)
                        if c > MISSING_SENTINEL + 1 and fw > MISSING_SENTINEL + 1:
                            clr_vals.append(c)
                            few_vals.append(fw)
                    except ValueError:
                        pass

            if not checked_units and wind_vals:
                clr_avg = sum(clr_vals) / len(clr_vals) if clr_vals else 0
                few_avg = sum(few_vals) / len(few_vals) if few_vals else 0
                print(f"    Sample [{sid}]: wind={sum(wind_vals)/len(wind_vals):.1f} mph, "
                      f"CLR={clr_avg:.1f}%, FEW={few_avg:.1f}%, coverage={len(clr_vals)}/{len(wind_vals)}")
                checked_units = True

            if wind_vals:
                wind_by_station[sid] = sum(wind_vals) / len(wind_vals)

            # Require ≥30% hourly coverage (2628 of 8760 hours) for cloud data
            if clr_vals and len(clr_vals) / 8760 >= 0.30:
                avg_clr_few = (sum(clr_vals) / len(clr_vals)) + (sum(few_vals) / len(few_vals))
                sun_by_station[sid] = avg_clr_few  # percent of hours that are clear or few-clouds

    print(f"  Wind data: {len(wind_by_station):,} stations")
    print(f"  Sun data:  {len(sun_by_station):,} stations")
    return wind_by_station, sun_by_station


def county_median(values_by_county):
    result = {}
    for fips, vals in values_by_county.items():
        vals.sort()
        result[fips] = vals[len(vals) // 2]
    return result


def main():
    cache_dir = Path("/tmp/ncei_normals_cache")
    cache_dir.mkdir(exist_ok=True)

    print("Step 1: Station inventory")
    inv_bytes = load_or_download(
        STATION_INVENTORY_URL, "GHCN station inventory", cache_dir / "ghcnd-stations.txt"
    )
    station_inventory = load_station_inventory(inv_bytes)

    print("Step 2: County centroids")
    cent_bytes = load_or_download(
        COUNTY_CENTROIDS_URL, "Census county centroids", cache_dir / "CenPop2020_Mean_CO.txt"
    )
    counties = load_county_centroids(cent_bytes)
    county_list = [(lat, lon, fips) for fips, (lat, lon) in counties.items()]

    print("Step 3: Hourly normals archive (220 MB)")
    archive_path = cache_dir / "hourly_normals.tar.gz"
    if not archive_path.exists():
        print("  Downloading (this will take a while)...", end=" ", flush=True)
        with urllib.request.urlopen(HOURLY_ARCHIVE_URL, timeout=600) as r:
            data = r.read()
        archive_path.write_bytes(data)
        print(f"{len(data) // (1024*1024)} MB")
    else:
        print(f"  Cached ({archive_path.stat().st_size // (1024*1024)} MB)")

    print("Step 4: Parse wind speed and sunny days")
    wind_by_station, sun_by_station = parse_hourly_archive(archive_path, station_inventory)

    print("Step 5: Map stations to counties")
    county_wind = {}
    county_sun = {}
    no_county = 0
    all_station_ids = set(wind_by_station) | set(sun_by_station)
    for sid in all_station_ids:
        if sid not in station_inventory:
            continue
        lat, lon = station_inventory[sid]
        fips = nearest_county(lat, lon, county_list)
        if fips is None:
            no_county += 1
            continue
        if sid in wind_by_station:
            county_wind.setdefault(fips, []).append(wind_by_station[sid])
        if sid in sun_by_station:
            county_sun.setdefault(fips, []).append(sun_by_station[sid])
    print(f"  Wind: {len(county_wind):,} counties; Sun: {len(county_sun):,} counties; {no_county} no-county")

    print("Step 6: Aggregate (median)")
    wind_medians = county_median(county_wind)
    sun_medians = county_median(county_sun)

    print("Step 7: Merge into county_climate.json")
    if OUT_FILE.exists():
        blob = json.loads(OUT_FILE.read_text())
    else:
        blob = {"_meta": {}, "data": {}}

    data = blob.get("data", {})
    # Clear stale values from any previous partial run before re-writing
    for v in data.values():
        v.pop("avg_wind_speed_mph", None)
        v.pop("annual_sunny_days", None)

    for fips, mph in wind_medians.items():
        data.setdefault(fips, {})["avg_wind_speed_mph"] = round(mph, 1)
    for fips, pct in sun_medians.items():
        sunny_days = round(pct / 100.0 * 365, 0)
        data.setdefault(fips, {})["annual_sunny_days"] = sunny_days

    blob["_meta"]["avg_wind_speed_mph"] = {
        "source": "NOAA NCEI Hourly Normals 1991-2020",
        "source_year": 2020,
        "note": "HLY-WIND-AVGSPD (tenths m/s) averaged over all valid hours, converted to mph",
    }
    blob["_meta"]["annual_sunny_days"] = {
        "source": "NOAA NCEI Hourly Normals 1991-2020",
        "source_year": 2020,
        "note": "(HLY-CLOD-PCTCLR + HLY-CLOD-PCTFEW) / 100 × 365 — stations with ≥30% hourly coverage only",
    }
    blob["data"] = data
    OUT_FILE.write_text(json.dumps(blob, separators=(",", ":")))

    wind_covered = sum(1 for v in data.values() if "avg_wind_speed_mph" in v)
    sun_covered = sum(1 for v in data.values() if "annual_sunny_days" in v)
    print(f"\nDone. Wind: {wind_covered:,} counties. Sun: {sun_covered:,} counties.")

    samples = [
        ("48113", "Dallas Co TX"),
        ("06037", "LA County CA"),
        ("08031", "Denver CO"),
        ("36061", "Manhattan NY"),
        ("35001", "Bernalillo Co NM (Albuquerque)"),
        ("53033", "King Co WA (Seattle)"),
        ("17031", "Cook Co IL (Chicago)"),
    ]
    print("\nSpot checks:")
    for fips, name in samples:
        w = data.get(fips, {}).get("avg_wind_speed_mph")
        s = data.get(fips, {}).get("annual_sunny_days")
        print(f"  {name} ({fips}): wind={w} mph, sunny_days={s}")


if __name__ == "__main__":
    main()
