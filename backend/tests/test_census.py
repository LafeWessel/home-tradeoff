"""Census ACS parsing — verify the 2D-array shape conversion handles real-world quirks."""

from app.sources.census import (
    _bachelors_or_higher_pct,
    _coerce_floats,
    _identity,
    _owner_occupied_pct,
    _parse_acs,
)


def test_parse_state_shape():
    raw = [
        ["NAME", "B19013_001E", "B25077_001E", "state"],
        ["Texas", "73035", "237400", "48"],
        ["California", "91905", "684800", "06"],
    ]
    rows = _parse_acs(raw)
    assert rows[0]["NAME"] == "Texas"
    assert rows[1]["state"] == "06"
    assert rows[1]["B25077_001E"] == "684800"


def test_parse_handles_null_string():
    raw = [["B25064_001E", "place", "state"], ["null", "06010", "06"]]
    rows = _parse_acs(raw)
    assert rows[0]["B25064_001E"] is None


def test_coerce_floats_handles_missing_and_blank():
    row = {"a": "12.5", "b": "", "c": None, "d": "not-a-number"}
    out = _coerce_floats(row, ["a", "b", "c", "d"])
    assert out == {"a": 12.5, "b": None, "c": None, "d": None}


def test_identity_drops_acs_sentinel():
    fn = _identity("X")
    assert fn({"X": -666666666.0}) is None
    assert fn({"X": -777777777.0}) is None
    assert fn({"X": 100.0}) == 100.0


def test_owner_occupied_pct():
    # 700 owners of 1000 occupied -> 70%
    out = _owner_occupied_pct({"B25003_001E": 1000, "B25003_002E": 700})
    assert abs(out - 70.0) < 1e-6


def test_owner_occupied_pct_missing_denominator_safe():
    assert _owner_occupied_pct({"B25003_001E": None, "B25003_002E": 5}) is None
    assert _owner_occupied_pct({"B25003_001E": 0, "B25003_002E": 5}) is None


def test_bachelors_pct():
    vals = {
        "B15003_001E": 100,
        "B15003_022E": 20,
        "B15003_023E": 10,
        "B15003_024E": 4,
        "B15003_025E": 1,
    }
    out = _bachelors_or_higher_pct(vals)
    assert abs(out - 35.0) < 1e-6


def test_bachelors_pct_missing_components_returns_none():
    vals = {"B15003_001E": 100, "B15003_022E": 20, "B15003_023E": None,
            "B15003_024E": 4, "B15003_025E": 1}
    assert _bachelors_or_higher_pct(vals) is None
