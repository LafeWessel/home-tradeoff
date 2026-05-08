"""Resolver tests — cascading lookups across the geography hierarchy."""

from datetime import datetime, timezone


def test_get_ancestors_walks_chain(tmp_db):
    from app.models.location import GeoLevel, Location
    from app.resolver import get_ancestors

    with tmp_db.SessionLocal() as db:
        state = Location(
            geoid="06", level=GeoLevel.state, name="California", state_fips="06",
            state_abbr="CA", parent_geoid=None
        )
        county = Location(
            geoid="06037", level=GeoLevel.county, name="Los Angeles County",
            state_fips="06", state_abbr="CA", county_fips="037", parent_geoid="06"
        )
        place = Location(
            geoid="0644000", level=GeoLevel.place, name="Los Angeles",
            state_fips="06", state_abbr="CA", place_fips="44000", parent_geoid="06"
        )
        db.add_all([state, county, place])
        db.commit()

        chain = get_ancestors(db, place)
        assert [c.geoid for c in chain] == ["0644000", "06"]

        chain = get_ancestors(db, county)
        assert [c.geoid for c in chain] == ["06037", "06"]


def test_resolved_metrics_cascades_to_state(tmp_db):
    """A place asking for a state-level metric should inherit the state's value."""
    from app.models.location import GeoLevel, Location
    from app.models.metric_value import MetricValue
    from app.resolver import get_resolved_metrics

    with tmp_db.SessionLocal() as db:
        state = Location(
            geoid="06", level=GeoLevel.state, name="California", state_fips="06",
            state_abbr="CA", parent_geoid=None
        )
        place = Location(
            geoid="0644000", level=GeoLevel.place, name="Los Angeles",
            state_fips="06", state_abbr="CA", place_fips="44000", parent_geoid="06"
        )
        db.add_all([state, place])
        db.commit()
        # Tax metric only present at state level
        db.add(
            MetricValue(
                location_id=state.id,
                metric_key="tax.income.top_marginal",
                value=13.3,
                source="curated",
                source_year=2024,
                fetched_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        resolved = get_resolved_metrics(db, place)
        m = resolved["tax.income.top_marginal"]
        assert m["value"] == 13.3
        assert m["level_resolved"] == "state"
        assert m["resolved_geoid"] == "06"


def test_resolved_metrics_prefers_finer_level(tmp_db):
    """When both place and state have a value, the place value wins."""
    from app.models.location import GeoLevel, Location
    from app.models.metric_value import MetricValue
    from app.resolver import get_resolved_metrics

    with tmp_db.SessionLocal() as db:
        state = Location(
            geoid="06", level=GeoLevel.state, name="California", state_fips="06",
            state_abbr="CA", parent_geoid=None
        )
        place = Location(
            geoid="0644000", level=GeoLevel.place, name="Los Angeles",
            state_fips="06", state_abbr="CA", place_fips="44000", parent_geoid="06"
        )
        db.add_all([state, place])
        db.commit()
        db.add_all(
            [
                MetricValue(
                    location_id=state.id, metric_key="housing.median_value",
                    value=684_800.0, source="ACS", source_year=2023,
                    fetched_at=datetime.now(timezone.utc),
                ),
                MetricValue(
                    location_id=place.id, metric_key="housing.median_value",
                    value=977_300.0, source="ACS", source_year=2023,
                    fetched_at=datetime.now(timezone.utc),
                ),
            ]
        )
        db.commit()

        resolved = get_resolved_metrics(db, place)
        assert resolved["housing.median_value"]["value"] == 977_300.0
        assert resolved["housing.median_value"]["level_resolved"] == "place"
