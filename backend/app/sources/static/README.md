# Curated static data

Files in this directory are *bundled* with the app because they're either too
big or too irregular to hit a live API for every comparison.

| File | Source | Refresh cadence | Notes |
|------|--------|-----------------|-------|
| `state_taxes.json` | Tax Foundation, NCSL, state DORs | Annual (Jan) | Income / sales / property / estate |
| `state_taxes_extra.json` | State revenue agencies | Annual | Retirement burden score, capital-gains top rate |
| `state_climate.json` | NOAA NCEI 1991–2020 normals | ~10 yr | Next update due 2031 |
| `state_heat_index.json` | NOAA | Annual | Summer apparent-temperature index |
| `state_rpp.json` | BEA Regional Price Parities | Annual (~Dec) | All-items RPP, indexed to US=100 |
| `state_col_components.json` | BEA SARPP (goods), Child Care Aware, KFF | Annual | Grocery index, infant childcare cost, marketplace health premium |
| `state_fema_nri.json` | FEMA National Risk Index | Annual | Composite hazard risk score per state |
| `state_nri_components.json` | FEMA NRI | Annual | Hurricane / wildfire / tornado / flood sub-scores |
| `state_crime.json` | FBI UCR / state agencies | Annual | Violent + property crime per 100k |
| `state_utilities.json` | EIA, FCC | Annual | Electricity rate (¢/kWh), broadband coverage % |
| `state_insurance.json` | Industry surveys | Annual | Avg annual homeowner insurance premium |
| `state_education.json` | NAEP | Biennial | K-12 proficiency % (4th-grade reading + math) |
| `state_health.json` | HRSA, CDC | Annual | Primary-care providers per 100k, life expectancy |
| `state_growth.json` | Census, BLS | Annual | 5-yr population growth %, 5-yr job growth % |
| `state_politics.json` | Cook PVI / 2024 election | Quadrennial | Partisan lean score |
| `state_pm25.json` | EPA AQS | Annual | Annual mean PM2.5 (µg/m³) |
| `state_housing_appreciation.json` | FHFA HPI | Annual | 10-yr home-price CAGR |
| `airports_large_hubs.json` | FAA | As needed | Large-hub airport coordinates for distance metric |
| `state_religion.json` | Pew Research Religious Landscape Study (2023-24) | ~10 yr | Christian / evangelical / Catholic / religiously unaffiliated adult share |
| `county_religion_adherence.json` | 2020 U.S. Religion Census (ASARB) | ~10 yr | County-level congregational adherence rate (any faith); different methodology than `state_religion.json`, not directly comparable |
| `county_religion_family.json` | 2020 U.S. Religion Census (ASARB), Group Detail file | ~10 yr | County-level Christian / evangelical / Catholic adherence rate; 372 denominations classified into RELTRAD-style families (see file's `_meta.notes`) |
| `state_water_quality.json` | America's Health Rankings (EPA SDWIS/ECHO) | Annual | Health-based drinking water violations per community water system |
| `state_marijuana.json` | NCSL / DISA Global Solutions | As changed | Marijuana legal status (illegal / medical / recreational); see file `_meta.notes` for recently-changed states |
| `state_abortion.json` | Guttmacher Institute / KFF | As changed | Abortion legal status by gestational limit; see file `_meta.notes` for contested/litigated states |

**Optional county-level overlays** (drop in to enable finer resolution):

| File | What it adds |
|------|-------------|
| `county_fema_nri.json` | Per-county FEMA NRI composite score keyed by 5-digit FIPS |
| `county_nri_components.json` | Per-county hurricane / wildfire / tornado / flood sub-scores |

If these files are absent the app falls back to state-level values automatically.

**Provenance.** Every value loaded from these files is written to the metric
cache with `source` + `source_year` so the UI can show a clear "as of" stamp.

**Refreshing.** When you want to update a file, edit the JSON in place and bump
`source_year`. Because the static loader caches file contents at process start
(`lru_cache`), you must **restart the API process** for the new values to take
effect:

```bash
# In the backend terminal, Ctrl+C then:
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

Or if using `scripts/dev.sh`, Ctrl+C and re-run it.
