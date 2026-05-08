"""Canonical catalog of every metric the app understands.

The catalog is the single source of truth for: what dimensions exist, how to
display them, what unit they use, which direction is "good", and which is the
finest geographic level at which the value is meaningfully resolvable.

When the resolver is asked for a metric at a level finer than `finest_level`
it cascades up to the parent (e.g. asking for state income tax at a city
returns the state's tax — the city inherits).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models.metric import MetricDirection


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    category: str
    unit: str
    direction: MetricDirection
    description: str
    source_label: str
    finest_level: str  # state | county | place


CATALOG: list[MetricDef] = [
    # ───── Taxes (mostly state-level — counties/places inherit) ─────
    MetricDef(
        key="tax.income.top_marginal",
        label="Top marginal state income tax",
        category="taxes",
        unit="%",
        direction=MetricDirection.lower_better,
        description="Top marginal personal income tax rate at the state level.",
        source_label="Tax Foundation (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="tax.income.flat_or_progressive",
        label="Income tax structure",
        category="taxes",
        unit="text",
        direction=MetricDirection.target,
        description="None / Flat / Progressive.",
        source_label="Tax Foundation (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="tax.sales.combined_avg",
        label="Combined sales tax (state+local avg)",
        category="taxes",
        unit="%",
        direction=MetricDirection.lower_better,
        description="State sales tax plus average local sales tax.",
        source_label="Tax Foundation (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="tax.property.effective_rate",
        label="Effective property tax rate",
        category="taxes",
        unit="%",
        direction=MetricDirection.lower_better,
        description="Median property tax as % of median home value (state avg). "
        "County values overlay this when available.",
        source_label="Census ACS / Tax Foundation",
        finest_level="county",
    ),
    MetricDef(
        key="tax.estate.has_estate_tax",
        label="State estate or inheritance tax",
        category="taxes",
        unit="bool",
        direction=MetricDirection.lower_better,
        description="1 if the state levies an estate or inheritance tax, else 0.",
        source_label="Tax Foundation (curated)",
        finest_level="state",
    ),
    # ───── Housing (Census ACS — finest at place) ─────
    MetricDef(
        key="housing.median_value",
        label="Median home value",
        category="housing",
        unit="$",
        direction=MetricDirection.target,
        description="Median value of owner-occupied housing units. ACS B25077.",
        source_label="Census ACS 5-year",
        finest_level="place",
    ),
    MetricDef(
        key="housing.median_rent",
        label="Median gross rent",
        category="housing",
        unit="$/mo",
        direction=MetricDirection.lower_better,
        description="Median gross rent (rent + utilities). ACS B25064.",
        source_label="Census ACS 5-year",
        finest_level="place",
    ),
    MetricDef(
        key="housing.owner_occupied_pct",
        label="Owner-occupied housing rate",
        category="housing",
        unit="%",
        direction=MetricDirection.higher_better,
        description="Share of occupied housing that is owner-occupied. ACS B25003.",
        source_label="Census ACS 5-year",
        finest_level="place",
    ),
    # ───── Cost of living ─────
    MetricDef(
        key="col.rpp",
        label="Regional Price Parity",
        category="cost_of_living",
        unit="index (US=100)",
        direction=MetricDirection.lower_better,
        description="BEA Regional Price Parity — overall price level relative to US avg (100).",
        source_label="BEA RPP (curated)",
        finest_level="state",
    ),
    # ───── Climate ─────
    MetricDef(
        key="climate.jan_low_f",
        label="January average low",
        category="climate",
        unit="°F",
        direction=MetricDirection.target,
        description="Mean daily minimum temperature in January (1991–2020 normals).",
        source_label="NOAA NCEI Normals (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="climate.jul_high_f",
        label="July average high",
        category="climate",
        unit="°F",
        direction=MetricDirection.target,
        description="Mean daily maximum temperature in July (1991–2020 normals).",
        source_label="NOAA NCEI Normals (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="climate.annual_precip_in",
        label="Annual precipitation",
        category="climate",
        unit="in",
        direction=MetricDirection.target,
        description="Mean annual precipitation (1991–2020 normals).",
        source_label="NOAA NCEI Normals (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="climate.annual_snowfall_in",
        label="Annual snowfall",
        category="climate",
        unit="in",
        direction=MetricDirection.target,
        description="Mean annual snowfall (1991–2020 normals). State-wide average.",
        source_label="NOAA NCEI Normals (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="climate.annual_sunny_days",
        label="Sunny days per year",
        category="climate",
        unit="days",
        direction=MetricDirection.higher_better,
        description="Mean annual days with measurable sunshine (clear + partly cloudy). 1991–2020 normals.",
        source_label="NOAA NCEI Normals (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="climate.avg_wind_speed_mph",
        label="Average wind speed",
        category="climate",
        unit="mph",
        direction=MetricDirection.target,
        description="Mean annual wind speed (1991–2020 normals). State-wide average.",
        source_label="NOAA NCEI Normals (curated)",
        finest_level="state",
    ),
    MetricDef(
        key="hazard.fema_nri",
        label="FEMA National Risk Index",
        category="climate",
        unit="0–100",
        direction=MetricDirection.lower_better,
        description="Composite natural-hazard risk score (0 lowest, 100 highest).",
        source_label="FEMA NRI (curated)",
        finest_level="county",
    ),
    # ───── Crime (FBI CDE — state-level estimates) ─────
    MetricDef(
        key="crime.violent_per_100k",
        label="Violent crime",
        category="crime",
        unit="per 100k",
        direction=MetricDirection.lower_better,
        description="Annual violent-crime estimate per 100,000 population.",
        source_label="FBI CDE",
        finest_level="state",
    ),
    MetricDef(
        key="crime.property_per_100k",
        label="Property crime",
        category="crime",
        unit="per 100k",
        direction=MetricDirection.lower_better,
        description="Annual property-crime estimate per 100,000 population.",
        source_label="FBI CDE",
        finest_level="state",
    ),
    # ───── Employment (BLS LAUS) ─────
    MetricDef(
        key="employment.unemployment_rate",
        label="Unemployment rate",
        category="employment",
        unit="%",
        direction=MetricDirection.lower_better,
        description="Most recent annual-average unemployment rate (BLS LAUS).",
        source_label="BLS LAUS",
        finest_level="county",
    ),
    # ───── Demographics & quality of life (Census ACS) ─────
    MetricDef(
        key="pop.total",
        label="Population",
        category="demographics",
        unit="people",
        direction=MetricDirection.target,
        description="Total population. ACS B01003.",
        source_label="Census ACS 5-year",
        finest_level="place",
    ),
    MetricDef(
        key="pop.median_age",
        label="Median age",
        category="demographics",
        unit="years",
        direction=MetricDirection.target,
        description="Median age of all residents. ACS B01002.",
        source_label="Census ACS 5-year",
        finest_level="place",
    ),
    MetricDef(
        key="econ.median_household_income",
        label="Median household income",
        category="demographics",
        unit="$",
        direction=MetricDirection.higher_better,
        description="Median household income (inflation-adjusted). ACS B19013.",
        source_label="Census ACS 5-year",
        finest_level="place",
    ),
    MetricDef(
        key="edu.bachelors_or_higher_pct",
        label="Bachelor's degree or higher",
        category="demographics",
        unit="%",
        direction=MetricDirection.higher_better,
        description="Share of population 25+ with a bachelor's degree or higher. ACS B15003.",
        source_label="Census ACS 5-year",
        finest_level="place",
    ),
]


CATALOG_BY_KEY: dict[str, MetricDef] = {m.key: m for m in CATALOG}
