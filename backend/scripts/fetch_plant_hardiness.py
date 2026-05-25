"""Derive county-level USDA Plant Hardiness Zone approximations from NOAA temperature normals.

The USDA Plant Hardiness Zone Map is based on the Average Annual Extreme Minimum
Temperature (AAEMT) — the 30-year average of each year's coldest recorded temperature.
No public machine-readable API exists for the 2023 USDA PHZM; this script derives
zone numbers from the county January average-low temperature (already in
county_climate.json) using a calibrated offset.

Methodology:
  AAEMT ≈ jan_avg_low_f − 26°F
  (Continental US calibration; see notes below for accuracy caveats)

Zone-to-AAEMT table (5°F per half-zone):
  Zone 1a: ≤ −60°F   Zone  7a: −5 to 0°F    Zone 10b: 30–35°F
  Zone 1b: −60–−55   Zone  7b:  0–5°F         Zone 11a: 35–40°F
  Zone 2a: −55–−50   Zone  8a:  5–10°F        Zone 11b: 40–45°F
  Zone 2b: −50–−45   Zone  8b: 10–15°F        Zone 12a: 45–50°F
  Zone 3a: −45–−40   Zone  9a: 15–20°F        Zone 12b: 50–55°F
  Zone 3b: −40–−35   Zone  9b: 20–25°F        Zone 13a: 55–60°F
  Zone 4a: −35–−30   Zone 10a: 25–30°F        Zone 13b: ≥60°F
  Zone 4b: −30–−25
  Zone 5a: −25–−20
  Zone 5b: −20–−15
  Zone 6a: −15–−10
  Zone 6b: −10–−5

Output stored as decimal: Zone 6b → 6.5, Zone 7a → 7.0, Zone 7b → 7.5, etc.

Accuracy: typically within ±1 half-zone (±5°F AAEMT) for most continental US counties.
Pacific coastal areas and the Gulf Coast tend to be underestimated (real zone higher);
high-elevation interior sites may be overestimated. Not a substitute for the official
USDA PHZ map at planthardiness.ars.usda.gov.

Output:
    app/sources/static/county_plant_hardiness.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_plant_hardiness.json"

# Calibrated offset: AAEMT ≈ jan_avg_low_f - OFFSET
# Calibration points (jan_low → official zone → derived AAEMT midpoint):
#   Denver CO 16°F → Zone 6b → AAEMT −7.5°F  → offset 23.5
#   Chicago IL 13°F → Zone 5b → AAEMT −17.5°F → offset 30.5
#   Minneapolis MN 4°F → Zone 4b → AAEMT −27.5°F → offset 31.5
#   Atlanta GA 33°F → Zone 8a → AAEMT 7.5°F → offset 25.5
#   Miami FL 62°F → Zone 10b → AAEMT 37.5°F → offset 24.5
#   Seattle WA 36°F → Zone 8b → AAEMT 12.5°F → offset 23.5
AAEMT_OFFSET_F = 26.0

SOURCE_YEAR = 2020  # matches NOAA 1991-2020 normals used in county_climate.json


def _aaemt_to_zone_decimal(aaemt: float) -> float:
    """Map AAEMT (°F) to decimal USDA zone (e.g. 6.5 = Zone 6b)."""
    # Each 5°F increment corresponds to one half-zone step
    # Zone 1a starts at ≤ −60°F; zone index 0.
    # Formula: idx = floor((aaemt + 65) / 5), clamped to [0, 25]
    idx = max(0, min(25, int((aaemt + 65.0) / 5.0)))
    zone_num = idx // 2 + 1
    half = idx % 2
    return float(zone_num) + half * 0.5


def main() -> None:
    county_path = STATIC_DIR / "county_climate.json"
    if not county_path.exists():
        sys.exit(f"Missing {county_path} — run fetch_county_climate.py first")

    county_climate: dict[str, dict] = json.loads(county_path.read_text()).get("data", {})
    data: dict[str, float] = {}
    used_county = 0

    for fips, cc in county_climate.items():
        jan_low = cc.get("jan_low_f")
        if jan_low is None:
            continue
        aaemt = float(jan_low) - AAEMT_OFFSET_F
        data[fips] = _aaemt_to_zone_decimal(aaemt)
        used_county += 1

    print(f"  {used_county} counties from county climate data", file=sys.stderr)

    # Validate a few known zones
    checks = {
        "08031": (6.0, 7.5, "Denver CO"),   # expected ~6b
        "17031": (5.0, 6.5, "Cook IL"),     # expected ~5b/6a
        "27053": (4.0, 5.5, "Hennepin MN"), # expected ~4b/5a
        "12086": (9.5, 11.5, "Miami-Dade"), # expected ~10a/10b
        "53033": (7.0, 9.5, "King WA"),     # expected ~8a/8b
    }
    print("\nSpot-checks:", file=sys.stderr)
    for fips, (lo, hi, name) in checks.items():
        z = data.get(fips, "MISSING")
        ok = lo <= z <= hi if z != "MISSING" else False
        print(f"  {name}: zone={z} {'✓' if ok else '?'} (expected {lo}–{hi})", file=sys.stderr)

    out = {
        "_meta": {
            "source": "Derived from NOAA NCEI 1991–2020 county climate normals (jan_low_f)",
            "methodology": f"AAEMT ≈ jan_avg_low_f − {AAEMT_OFFSET_F}°F; then mapped to USDA PHZ half-zone grid",
            "source_year": SOURCE_YEAR,
            "notes": (
                "Approximate USDA Plant Hardiness Zone (decimal: 6.5 = Zone 6b). "
                f"Offset {AAEMT_OFFSET_F}°F calibrated for the continental US; typically within ±1 "
                "half-zone. For official zones see planthardiness.ars.usda.gov."
            ),
        },
        "data": dict(sorted(data.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {len(data)} counties → {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
