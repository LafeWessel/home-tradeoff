# Data Categories To Add

Items queued for future implementation. Do not start on these until explicitly requested.

- Social welfare programs
- Distance to family? Could put pins down on the map

## Politics & Policy

- Business/regulatory climate — permitting friction, occupational licensing burden, right-to-work status

## Lifestyle & Outdoors

- **Mountainousness (improved)** — Current impl: `env.elevation_ft` is centroid elevation only. Future: terrain ruggedness index (TRI), % land above elevation thresholds, elevation range per county. Requires raster analysis of USGS 3DEP DEM data.
- **Recreation access (improved)** — Current impl: `outdoor.nps_units_count` is a state-level NPS unit count, FY2020 vintage. Future: Trust for Public Land "City Park Facts" dataset (tpl.org/park-data-downloads) has real, current, place-level data — acres of parkland per 1,000 residents, % of residents within a 10-min walk of a park — for the ~100 largest US cities. Would need a place-name-matching loader and only covers those cities.
