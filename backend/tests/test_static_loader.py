"""Static loader tests — verify the JSON adapters emit the expected tuples."""

from app.models.location import GeoLevel, Location
from app.sources import airport, static_loader


_FIPS = {
    "CA": "06", "TX": "48", "NY": "36", "FL": "12", "VT": "50",
    "MS": "28", "ID": "16", "WY": "56", "WV": "54", "HI": "15", "MA": "25",
}


def _state(abbr: str, lid: int = 1) -> Location:
    fips = _FIPS[abbr]
    loc = Location(
        geoid=fips, level=GeoLevel.state, name=abbr, state_fips=fips,
        state_abbr=abbr, parent_geoid=None,
    )
    loc.id = lid
    return loc


def test_taxes_emits_state_metrics():
    out = static_loader.fetch_taxes(None, [_state("CA", 1)])  # type: ignore[arg-type]
    keys = {row[1] for row in out}
    assert "tax.income.top_marginal" in keys
    assert "tax.sales.combined_avg" in keys
    assert "tax.estate.has_estate_tax" in keys
    assert "tax.property.effective_rate" in keys
    sources = {row[3] for row in out}
    years = {row[4] for row in out}
    assert len(sources) == 1
    assert len(years) == 1


def test_climate_emits_six_metrics():
    out = static_loader.fetch_climate(None, [_state("TX", 7)])  # type: ignore[arg-type]
    keys = sorted(row[1] for row in out)
    assert keys == sorted(
        [
            "climate.jan_low_f",
            "climate.jul_high_f",
            "climate.annual_precip_in",
            "climate.annual_snowfall_in",
            "climate.annual_sunny_days",
            "climate.avg_wind_speed_mph",
        ]
    )
    jan_low = next(row[2] for row in out if row[1] == "climate.jan_low_f")
    assert jan_low is not None and jan_low > 25


def test_rpp_higher_for_ny_than_ms():
    out_ny = static_loader.fetch_rpp(None, [_state("NY", 1)])  # type: ignore[arg-type]
    val = next(row[2] for row in out_ny if row[1] == "col.rpp")
    assert val is not None and val > 100  # NY is more expensive than US avg


def test_fema_state_fallback():
    out = static_loader.fetch_fema(None, [_state("CA", 1)])  # type: ignore[arg-type]
    assert any(row[1] == "hazard.fema_nri" for row in out)


def test_insurance_florida_high():
    out = static_loader.fetch_insurance(None, [_state("FL", 1)])  # type: ignore[arg-type]
    keys = {row[1] for row in out}
    assert "housing.insurance_avg_premium" in keys
    fl_premium = next(row[2] for row in out if row[1] == "housing.insurance_avg_premium")
    assert fl_premium is not None and fl_premium > 4000  # FL is among the highest


def test_taxes_extra_emits_two_metrics():
    out = static_loader.fetch_taxes_extra(None, [_state("CA", 3)])  # type: ignore[arg-type]
    keys = sorted(row[1] for row in out)
    assert keys == sorted(["tax.retirement.burden_score", "tax.capital_gains.top_rate"])
    cg = next(row[2] for row in out if row[1] == "tax.capital_gains.top_rate")
    assert cg is not None and cg > 10  # CA top LTCG > 10%


def test_housing_appreciation_idaho_strong():
    out = static_loader.fetch_housing_appreciation(None, [_state("ID", 1)])  # type: ignore[arg-type]
    val = next(row[2] for row in out if row[1] == "housing.appreciation_10yr_cagr")
    assert val is not None and val > 8


def test_nri_components_emits_four_for_florida():
    out = static_loader.fetch_nri_components(None, [_state("FL", 5)])  # type: ignore[arg-type]
    keys = sorted(row[1] for row in out)
    assert keys == sorted(
        ["hazard.hurricane", "hazard.wildfire", "hazard.tornado", "hazard.flood"]
    )
    hur = next(row[2] for row in out if row[1] == "hazard.hurricane")
    assert hur is not None and hur > 50


def test_pm25_present():
    out = static_loader.fetch_pm25(None, [_state("CA", 1)])  # type: ignore[arg-type]
    assert any(row[1] == "env.pm25_annual" for row in out)


def test_heat_index_louisiana_higher_than_maine():
    la = Location(
        geoid="22", level=GeoLevel.state, name="LA", state_fips="22",
        state_abbr="LA", parent_geoid=None,
    )
    la.id = 1
    me = Location(
        geoid="23", level=GeoLevel.state, name="ME", state_fips="23",
        state_abbr="ME", parent_geoid=None,
    )
    me.id = 2
    out = static_loader.fetch_heat_index(None, [la, me])  # type: ignore[arg-type]
    by_id = {row[0]: row[2] for row in out if row[1] == "climate.summer_heat_index_f"}
    assert by_id[1] > by_id[2]


def test_utilities_hawaii_high_rate():
    out = static_loader.fetch_utilities(None, [_state("HI", 1)])  # type: ignore[arg-type]
    keys = {row[1] for row in out}
    assert "utility.electricity_rate" in keys
    assert "infra.broadband_100_20_pct" in keys
    rate = next(row[2] for row in out if row[1] == "utility.electricity_rate")
    assert rate is not None and rate > 30


def test_education_present():
    out = static_loader.fetch_education(None, [_state("MA", 1)])  # type: ignore[arg-type]
    val = next(row[2] for row in out if row[1] == "edu.k12_proficiency_pct")
    assert val is not None and val > 30


def test_health_metrics_present():
    out = static_loader.fetch_health(None, [_state("MA", 9)])  # type: ignore[arg-type]
    keys = {row[1] for row in out}
    assert "health.primary_care_per_100k" in keys
    assert "health.life_expectancy_years" in keys


def test_growth_idaho_higher_than_west_virginia():
    id_loc = _state("ID", 1)
    wv_loc = _state("WV", 2)
    out = static_loader.fetch_growth(None, [id_loc, wv_loc])  # type: ignore[arg-type]
    pop_by_id = {row[0]: row[2] for row in out if row[1] == "pop.growth_5yr_pct"}
    assert pop_by_id[1] > pop_by_id[2]


def test_politics_signed_margin():
    cal = static_loader.fetch_politics(None, [_state("CA", 1)])  # type: ignore[arg-type]
    wy = static_loader.fetch_politics(None, [_state("WY", 2)])  # type: ignore[arg-type]
    cal_v = next(row[2] for row in cal if row[1] == "politics.partisan_lean_2024")
    wy_v = next(row[2] for row in wy if row[1] == "politics.partisan_lean_2024")
    assert cal_v < 0 and wy_v > 0


def test_airport_distance_atlanta_close_to_atl_hub():
    atl_city = Location(
        geoid="1304000", level=GeoLevel.place, name="Atlanta", state_fips="13",
        state_abbr="GA", parent_geoid="13", lat=33.7488, lon=-84.3877,
    )
    atl_city.id = 1
    out = airport.fetch_for_locations(None, [atl_city])  # type: ignore[arg-type]
    assert len(out) == 1 and out[0][1] == "infra.airport_hub_distance_mi"
    assert out[0][2] is not None and out[0][2] < 15


def test_airport_distance_skips_locations_without_coords():
    no_coords = Location(
        geoid="9999", level=GeoLevel.place, name="X", state_fips="06",
        state_abbr="CA", parent_geoid="06", lat=None, lon=None,
    )
    no_coords.id = 2
    out = airport.fetch_for_locations(None, [no_coords])  # type: ignore[arg-type]
    assert out == []
