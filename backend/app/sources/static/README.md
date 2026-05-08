# Curated static data

Files in this directory are *bundled* with the app because they're either too
big or too irregular to hit a live API for every comparison.

| File | Source | Refresh cadence | Notes |
|------|--------|-----------------|-------|
| `state_taxes.json` | Tax Foundation, NCSL, state DORs | Annual (Jan) | Income / sales / property / estate |
| `state_climate.json` | NOAA NCEI 1991–2020 normals | ~10 yr | Already 1991–2020 normals; next update due 2031 |
| `state_rpp.json` | BEA Regional Price Parities | Annual (~Dec) | All-items RPP, indexed to US=100 |
| `county_fema_nri.json` | FEMA National Risk Index | Annual | Composite risk score per county FIPS |

**Provenance.** Every value loaded from these files is written to the metric
cache with `source` + `source_year` so the UI can show a clear "as of" stamp.

**Refreshing.** When you want to update one of these files, replace the JSON
and bump `source_year`. The next request that reads metric values will not
automatically re-read from disk — run:

```bash
python -m app.refresh static
```

to invalidate the cached static rows.
