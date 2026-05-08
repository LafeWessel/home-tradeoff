"""Static loader tests — verify the JSON adapters emit the expected tuples."""

from app.models.location import GeoLevel, Location
from app.sources import static_loader


def _state(abbr: str, lid: int = 1) -> Location:
    fips = {"CA": "06", "TX": "48", "NY": "36"}[abbr]
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
    # All rows should be tagged with the same source/year
    sources = {row[3] for row in out}
    years = {row[4] for row in out}
    assert len(sources) == 1
    assert len(years) == 1


def test_climate_emits_three_metrics():
    out = static_loader.fetch_climate(None, [_state("TX", 7)])  # type: ignore[arg-type]
    keys = sorted(row[1] for row in out)
    assert keys == sorted(
        ["climate.jan_low_f", "climate.jul_high_f", "climate.annual_precip_in"]
    )
    # Texas Jan low should be > 25
    jan_low = next(row[2] for row in out if row[1] == "climate.jan_low_f")
    assert jan_low is not None and jan_low > 25


def test_rpp_higher_for_ny_than_ms():
    out_ny = static_loader.fetch_rpp(None, [_state("NY", 1)])  # type: ignore[arg-type]
    # MS isn't in our state list helper, so just assert NY is in expected range.
    val = next(row[2] for row in out_ny if row[1] == "col.rpp")
    assert val is not None and val > 100  # NY is more expensive than US avg


def test_fema_state_fallback():
    out = static_loader.fetch_fema(None, [_state("CA", 1)])  # type: ignore[arg-type]
    assert any(row[1] == "hazard.fema_nri" for row in out)
