#!/usr/bin/env python3
"""Bulk-load all metric values for every state and county.

Run once to warm the database from scratch; safe to re-run — all writes are
upserts, and locations with recent data are skipped for live API sources.

Usage:
    cd backend && python -m scripts.load_all            # skip locations fresh within 180 days
    cd backend && python -m scripts.load_all --force    # re-fetch everything

API keys required (set in backend/.env):
    CENSUS_API_KEY  — ACS 5yr data (population, income, housing, etc.)
    BLS_API_KEY     — unemployment rate (optional; raises rate limit)
    FBI_API_KEY     — state-level crime rates (optional)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models.location import GeoLevel, Location
from app.resolver import ensure_metric_values

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Re-fetch even if data is already fresh")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    freshness = timedelta(0) if args.force else timedelta(days=180)

    init_db()

    with SessionLocal() as db:
        states = db.execute(
            select(Location).where(Location.level == GeoLevel.state).order_by(Location.geoid)
        ).scalars().all()
        counties = db.execute(
            select(Location).where(Location.level == GeoLevel.county).order_by(Location.geoid)
        ).scalars().all()

        if not states:
            print("No locations found. Run the seed script first:")
            print("  cd backend && python -m app.seed")
            return 1

        print(f"Loading data for {len(states)} states and {len(counties)} counties...")

        # States first so county batches find fresh ancestors and skip re-fetching them
        print(f"\n[1/2] States ({len(states)})")
        ensure_metric_values(db, list(states), freshness=freshness)
        print("      done")

        # Counties batched by state — Census API groups by (level, state_fips) so each
        # batch triggers exactly one Census API call for all counties in that state.
        by_state: dict[str, list[Location]] = {}
        for county in counties:
            by_state.setdefault(county.state_fips or "??", []).append(county)

        total_batches = len(by_state)
        print(f"\n[2/2] Counties ({len(counties)} across {total_batches} states)")
        for i, (state_fips, locs) in enumerate(sorted(by_state.items()), 1):
            state_abbr = locs[0].state_abbr or state_fips
            print(f"  [{i:2d}/{total_batches}] {state_abbr}: {len(locs)} counties", end="", flush=True)
            ensure_metric_values(db, locs, freshness=freshness)
            print(" ✓")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
