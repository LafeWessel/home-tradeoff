"""Seed the database with US states, counties, and major places.

Usage:
    python -m app.seed                # full seed
    python -m app.seed --states-only  # skip API-dependent counties/places
    python -m app.seed --places-min-population 10000

States are hardcoded (51 rows including DC). Counties and places are fetched
from the Census API at seed time using your CENSUS_API_KEY. Place seeding is
filtered by population so we don't carry every CDP — default threshold is 5000.

The seed is idempotent: re-running updates names/populations and inserts new
rows but never deletes existing locations.
"""

from __future__ import annotations

import argparse
import logging
import sys

import httpx
from sqlalchemy import select

from .db import SessionLocal, init_db
from .models.location import GeoLevel, Location
from .seed_data.states import STATES
from .settings import settings

log = logging.getLogger("seed")
ACS_YEAR = 2023


def _upsert_location(db, *, geoid: str, **fields) -> Location:
    existing = db.execute(select(Location).where(Location.geoid == geoid)).scalar_one_or_none()
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        return existing
    loc = Location(geoid=geoid, **fields)
    db.add(loc)
    return loc


def seed_states(db) -> int:
    for s in STATES:
        _upsert_location(
            db,
            geoid=s["fips"],
            level=GeoLevel.state,
            name=s["name"],
            state_fips=s["fips"],
            state_abbr=s["abbr"],
            county_fips=None,
            place_fips=None,
            parent_geoid=None,
            lat=s["lat"],
            lon=s["lon"],
        )
    db.commit()
    return len(STATES)


def _abbr(fips: str) -> str | None:
    return next((s["abbr"] for s in STATES if s["fips"] == fips), None)


def seed_counties(db) -> int:
    if not settings.census_api_key:
        log.warning("No CENSUS_API_KEY — skipping counties seed.")
        return 0
    url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
    params = {
        "get": "NAME,B01003_001E",
        "for": "county:*",
        "in": "state:*",
        "key": settings.census_api_key,
    }
    log.info("Fetching counties from Census ACS …")
    with httpx.Client(timeout=60.0) as c:
        resp = c.get(url, params=params)
        resp.raise_for_status()
        rows = resp.json()
    headers = rows[0]
    name_i = headers.index("NAME")
    pop_i = headers.index("B01003_001E")
    state_i = headers.index("state")
    county_i = headers.index("county")

    inserted = 0
    for r in rows[1:]:
        state_fips = r[state_i].zfill(2)
        county_fips = r[county_i].zfill(3)
        geoid = state_fips + county_fips
        abbr = _abbr(state_fips)
        if abbr is None:
            continue  # territories
        try:
            pop = int(r[pop_i]) if r[pop_i] not in (None, "", "null") else None
        except ValueError:
            pop = None
        # name is "County Name, State"; we want just the county name
        county_name = (r[name_i] or "").split(",")[0].strip()
        _upsert_location(
            db,
            geoid=geoid,
            level=GeoLevel.county,
            name=county_name,
            state_fips=state_fips,
            state_abbr=abbr,
            county_fips=county_fips,
            place_fips=None,
            parent_geoid=state_fips,
            population=pop,
        )
        inserted += 1
    db.commit()
    return inserted


def seed_places(db, min_population: int = 5000) -> int:
    if not settings.census_api_key:
        log.warning("No CENSUS_API_KEY — skipping places seed.")
        return 0
    url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"

    inserted = 0
    for s in STATES:
        params = {
            "get": "NAME,B01003_001E",
            "for": "place:*",
            "in": f"state:{s['fips']}",
            "key": settings.census_api_key,
        }
        try:
            with httpx.Client(timeout=60.0) as c:
                resp = c.get(url, params=params)
                resp.raise_for_status()
                rows = resp.json()
        except Exception as e:  # noqa: BLE001
            log.warning("places fetch failed for %s: %s", s["abbr"], e)
            continue
        if not rows or len(rows) < 2:
            continue
        headers = rows[0]
        name_i = headers.index("NAME")
        pop_i = headers.index("B01003_001E")
        state_i = headers.index("state")
        place_i = headers.index("place")

        for r in rows[1:]:
            try:
                pop = int(r[pop_i]) if r[pop_i] not in (None, "", "null") else 0
            except ValueError:
                pop = 0
            if pop < min_population:
                continue
            state_fips = r[state_i].zfill(2)
            place_fips = r[place_i].zfill(5)
            geoid = state_fips + place_fips
            # The Census name is e.g. "Phoenix city, Arizona"; strip the suffix.
            full = r[name_i] or ""
            base = full.split(",")[0].strip()
            for suffix in (" city", " town", " village", " borough", " CDP", " municipality"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)].strip()
                    break
            _upsert_location(
                db,
                geoid=geoid,
                level=GeoLevel.place,
                name=base,
                state_fips=state_fips,
                state_abbr=s["abbr"],
                county_fips=None,
                place_fips=place_fips,
                parent_geoid=state_fips,  # places nest under state in Census schema
                population=pop,
            )
            inserted += 1
        db.commit()
        log.info("seeded places for %s", s["abbr"])
    return inserted


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

    p = argparse.ArgumentParser()
    p.add_argument("--states-only", action="store_true")
    p.add_argument("--places-min-population", type=int, default=5000)
    args = p.parse_args()

    init_db()
    with SessionLocal() as db:
        n_states = seed_states(db)
        log.info("✔ %d states", n_states)

        if args.states_only:
            return 0

        n_counties = seed_counties(db)
        log.info("✔ %d counties", n_counties)

        n_places = seed_places(db, min_population=args.places_min_population)
        log.info("✔ %d places (pop ≥ %d)", n_places, args.places_min_population)
    return 0


if __name__ == "__main__":
    sys.exit(main())
