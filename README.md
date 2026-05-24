# Home Tradeoff

A locally-hosted decision-support tool for comparing US locations as places to
live for the next 10–20 years. Surfaces and ranks **states**, **counties**, and
**municipalities** across taxes, housing, cost of living, climate, crime,
employment, and demographics — with your own preference presets so the
tradeoffs are explicit.

> Single-user, runs entirely on your machine. No public hosting required.

---

## Screenshots

```
┌─ Home Tradeoff ──────────────────────────────────┬──────────────────────┐
│                                                  │  🔎 Search…           │
│       ●  ●         ●        ●  ●                 │  Comparing (3)        │
│    ●           ●        ●                        │  [TX] [CA] [Miami,FL] │
│         ●     ●     ●           ●                │  ─────────────────── │
│                                                  │  Compare │ Rank │ … │
│             [ click a state to add ]             │                      │
│                                                  │  Taxes                │
│                                                  │   Top marginal …      │
│                                                  │   Sales tax …         │
│  ─── OpenStreetMap basemap ───                   │  Climate              │
└──────────────────────────────────────────────────┴──────────────────────┘
```

---

## What it does

- **Pick locations** at any granularity (state / county / place) by clicking
  the map or searching by name.
- **Compare them side-by-side** across every dimension we collect — best /
  worst per row are highlighted, and inherited values (e.g. a city's state
  income tax) are tagged so you know exactly where each number came from.
- **Define preference presets** — for each metric, set an ideal value or
  range, a weight (0–10), and a direction (lower-better, higher-better, or
  target).
- **See ranked scores** so the best fit for *your* preferences floats to the
  top.
- **Save multiple presets** ("retirement", "young family", "remote work") and
  switch between them to see how the ranking changes.
- **Mix granularities freely** — comparing a state vs. a county vs. a city
  works.

Data is fetched from public APIs (Census ACS, BLS, FBI Crime Data Explorer)
and **cached in a local SQLite database** so each comparison is fast and
re-runs do not re-hit the network. Static reference data (state taxes, NOAA
climate normals, BEA RPP, FEMA NRI) ships as curated JSON in
`backend/app/sources/static/`. Basemap tiles are *not* cached — they stream
live from OpenStreetMap.

---

## Quick start

### Prerequisites

- Python ≥ 3.11
- Node ≥ 20

### One-time setup

```bash
git clone <repo-url> home-tradeoff && cd home-tradeoff

# Optional but recommended — fill in API keys for live data
cp .env.example .env
$EDITOR .env

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# Seed the DB. With CENSUS_API_KEY set you get all states + ~3,143 counties +
# ~10–15k places (population ≥ 5000). Without a key you get the 51 states only,
# which is still enough to use every feature.
# Full seed takes ~5–10 min depending on Census API response time.
python -m app.seed                       # full seed (Census key required for counties/places)
# or:
# python -m app.seed --states-only       # 51 states only, no API key needed (~2 seconds)
# python -m app.seed --places-min-population 10000  # fewer places (faster)
# python -m app.seed --backfill-coords-only          # re-run lat/lon backfill only

# Frontend
cd ../frontend
npm install
```

### Run it

Two terminals:

```bash
# terminal 1 — API on :8765
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765

# terminal 2 — UI on :5173
cd frontend
npm run dev
```

…or one terminal:

```bash
./scripts/dev.sh
```

Then open <http://127.0.0.1:5173>.

### Test

```bash
# backend
cd backend && pytest

# frontend (typecheck only — UI tests are TODO)
cd frontend && npm run lint
```

### Build for "production" (still local)

```bash
cd frontend && npm run build         # outputs dist/
cd ../backend && uvicorn app.main:app --port 8765
# Serve frontend/dist with any static server you like.
```

---

## API keys (all free, all optional)

Even with **no keys at all**, the app is fully usable for state-level
comparisons — taxes, climate, cost of living, FEMA hazard, and structure all
ship as curated JSON.

| Source | What it adds | Sign up |
|--------|--------------|---------|
| Census Bureau ACS | Population, median income, home values, rents, education at state/county/place level + the seed list of counties and places | <https://api.census.gov/data/key_signup.html> |
| BLS | Live unemployment rate by state and county | <https://data.bls.gov/registrationEngine/> |
| FBI CDE | Live violent / property crime per 100k by state | <https://api.data.gov/signup/> |
| NOAA NCEI | Reserved for future county/place-level climate normals | <https://www.ncdc.noaa.gov/cdo-web/token> |

Set them in `.env` (template at `.env.example`).

---

## Architecture

```
home-tradeoff/
├── backend/                 FastAPI + SQLAlchemy + SQLite
│   ├── app/
│   │   ├── main.py          ASGI app + route wiring
│   │   ├── db.py            engine, session, init
│   │   ├── settings.py      env config
│   │   ├── metrics_catalog  canonical list of every metric the app understands
│   │   ├── models/          ORM (Location, Metric, MetricValue, Preset, Preference, ApiCache)
│   │   ├── api/             routes (locations, metrics, presets, scoring)
│   │   ├── sources/         Census, BLS, FBI + static_loader
│   │   │   └── static/      curated JSON: taxes, climate, RPP, FEMA NRI
│   │   ├── scoring/         preference scoring engine
│   │   ├── resolver.py      metric resolution + caching + cascading lookups
│   │   ├── seed.py          populates locations
│   │   └── seed_data/       hardcoded states list
│   └── tests/               pytest suite
├── frontend/                React + Vite + TypeScript + MapLibre GL
│   └── src/
│       ├── App.tsx
│       ├── components/      Map, Search, Tray, Compare, Score, Preferences
│       ├── api/             typed backend client
│       ├── store.ts         Zustand global store
│       ├── format.ts        value/score formatters
│       ├── defaults.ts      sensible default ideals/caps per metric
│       └── types.ts         shared TS types
└── scripts/dev.sh           run backend + frontend together
```

Design intent (see `CLAUDE.md`):

- **Data freshness over cleverness.** Every metric value carries source +
  `source_year` provenance. The UI shows the year alongside each cell.
- **Maintainability.** Adding a metric is one entry in `metrics_catalog.py`
  + one line in the source module that emits it.
- **Local-first.** SQLite cache, no auth, no telemetry. The DB file is
  ignored by git.
- **Cascading geographic resolution.** Asking for the state income tax of a
  city falls back to the city's state value automatically; the UI tags
  inherited values as `(state)` or `(county)` so it's never ambiguous.

---

## Data dictionary

20 metrics across 7 categories. Full definitions are in
`backend/app/metrics_catalog.py`. Highlights:

- **Taxes** — top marginal income tax, structure (none/flat/progressive),
  combined sales tax, effective property tax, estate/inheritance presence
- **Housing** — median home value, median rent, owner-occupied %
- **Cost of living** — BEA Regional Price Parity (US=100)
- **Climate** — Jan low °F, Jul high °F, annual precipitation, FEMA
  National Risk Index composite
- **Crime** — violent / property crime per 100k
- **Employment** — annual-average unemployment rate
- **Demographics** — population, median age, median household income,
  bachelor's-or-higher %
- **Education policy** — homeschool regulation level (1=no notice required →
  5=prior approval required) and school voucher/ESA program availability
  (0=none, 1=limited, 2=universal); sourced from HSLDA and EdChoice 2024

Each metric is tagged with a `direction` (`lower_better`, `higher_better`,
`target`) which determines how preference scoring normalizes it. Direction
can be overridden per-preset (e.g. someone wants colder summers).

---

## How scoring works

For each metric in your active preset:

1. Compute a per-location 0–100 score against your preference:
   - **lower_better**: full credit at/below ideal, drops linearly to 0 at
     the cap (the "unacceptable" threshold).
   - **higher_better**: full credit at/above ideal, drops to 0 at the cap.
   - **target**: full credit at the target, drops linearly within ±tolerance,
     0 outside.
2. Weight each score by importance (0–10).
3. Final score = `Σ(weight × metric_score) / Σ(weight)`, normalized 0–100.

**Missing data is not penalized.** The metric is excluded from that location's
denominator and surfaced in the UI so you know what's missing rather than
silently scoring it as zero.

---

## Refreshing curated data

`backend/app/sources/static/` ships with curated values that need periodic
refresh. Each file has a `_meta.source_year` and a `notes` field. To update:

1. Edit the JSON in place (or replace the file).
2. Bump `source_year`.
3. The next API call that touches static data will pick up the new values
   (the static loader reads them at process start; restart the API).

To force re-fetch of API-cached values, delete the relevant rows from
`api_cache` (or just `rm backend/data.db` for a full reset and re-seed).

---

## Roadmap

- School ratings (currently captured via educational attainment proxy)
- Healthcare access (HRSA HPSA scores)
- Walkability (Walk Score API — paid)
- County-level FEMA NRI overlay (drop a `county_fema_nri.json` keyed by
  5-digit FIPS into `backend/app/sources/static/`)
- Custom user-supplied metrics (CSV → metric registration → preference)
- Geographic boundary visualization on the map (county polygons)
- Frontend tests (Vitest + React Testing Library)

---

## License

Personal use. The data you fetch from public APIs remains under those
sources' terms.
