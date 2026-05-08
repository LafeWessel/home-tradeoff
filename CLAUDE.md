# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This is a locally-hosted decision-support tool for comparing US locations as potential places to live for the next 10–20 years. The application surfaces and compares location data at three levels of granularity: **state**, **county**, and **local/municipal**. Data accuracy and freshness are critical — stale or incorrect information undermines the entire purpose.

## Data Categories

Every location should expose data across these dimensions:

- **Taxes**: property tax rates, state/local income tax, sales tax, estate/inheritance tax
- **Housing**: median home prices, rent prices, price trends, property appreciation history
- **Cost of living**: grocery, transportation, healthcare, childcare indices vs. national average
- **Utilities**: average electric, gas, water/sewer, internet costs
- **Climate**: temperature ranges, precipitation, extreme weather frequency (hurricanes, tornadoes, wildfires, flooding risk), air quality
- **Crime**: violent crime rate, property crime rate — sourced at city/county level, not just state
- **Employment**: major employers, unemployment rate, industry mix
- **Demographics & quality of life**: population size/growth, school ratings, healthcare access, walkability

## Architecture Intent

- **Backend**: A persistent-database webservice exposing a REST (or GraphQL) API. The database stores cached/normalized location data so the UI doesn't re-fetch on every comparison.
- **Frontend**: A locally-served UI (no public hosting required) for searching, browsing, and side-by-side comparison of locations.
- **Data sourcing**: Data will come from public APIs and datasets (Census Bureau, BLS, IRS, FBI UCR/NIBRS, NOAA, etc.) and may be periodically refreshed. The architecture should treat data collection/refresh as a separate concern from the API that serves the UI.
- **Scope**: US only — state + county + municipality hierarchy. No international locations.

## Development Guidelines

- **Always commit and push after making changes.** Every completed change should be committed with a meaningful message and pushed to the remote.
- **Maintainability and extensibility over cleverness.** Code should be easy to modify as new data sources, geographies, or comparison dimensions are added later.
- **Write tests for error-prone areas** (data parsing, API integrations, geographic hierarchy logic, data refresh pipelines) and run them regularly. Failing silently is worse than failing loudly.

## Key Design Constraints

- Comparisons must work across all three geographic levels (state vs. state, county vs. county, city vs. city, or mixed).
- Data sources should be recorded alongside each data point (provenance) so figures can be verified and refreshed.
- The app is single-user and local — no auth, no multi-tenancy, no public deployment concerns.
