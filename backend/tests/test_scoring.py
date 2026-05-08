"""Scoring engine tests — exercise every direction and edge case."""

from app.scoring.engine import PrefSpec, score_locations


def _wrap(value):
    return {"value": value}


def test_lower_better_at_ideal_full_credit():
    out = score_locations(
        {1: {"crime.violent_per_100k": _wrap(150)}},
        [PrefSpec("crime.violent_per_100k", 5, "lower_better", 200, 800, None)],
    )
    assert out[0].metrics[0].score == 100.0
    assert out[0].overall_score == 100.0


def test_lower_better_at_cap_zero():
    out = score_locations(
        {1: {"crime.violent_per_100k": _wrap(800)}},
        [PrefSpec("crime.violent_per_100k", 5, "lower_better", 200, 800, None)],
    )
    assert out[0].metrics[0].score == 0.0


def test_lower_better_midpoint_50():
    out = score_locations(
        {1: {"crime.violent_per_100k": _wrap(500)}},
        [PrefSpec("crime.violent_per_100k", 5, "lower_better", 200, 800, None)],
    )
    assert out[0].metrics[0].score == 50.0


def test_higher_better_at_ideal_full():
    out = score_locations(
        {1: {"econ.median_household_income": _wrap(90_000)}},
        [PrefSpec("econ.median_household_income", 5, "higher_better", 90_000, 50_000, None)],
    )
    assert out[0].metrics[0].score == 100.0


def test_higher_better_below_floor_zero():
    out = score_locations(
        {1: {"econ.median_household_income": _wrap(50_000)}},
        [PrefSpec("econ.median_household_income", 5, "higher_better", 90_000, 50_000, None)],
    )
    assert out[0].metrics[0].score == 0.0


def test_target_at_value_full():
    out = score_locations(
        {1: {"climate.jan_low_f": _wrap(35)}},
        [PrefSpec("climate.jan_low_f", 5, "target", 35, None, 15)],
    )
    assert out[0].metrics[0].score == 100.0


def test_target_outside_tolerance_zero():
    out = score_locations(
        {1: {"climate.jan_low_f": _wrap(0)}},
        [PrefSpec("climate.jan_low_f", 5, "target", 35, None, 15)],
    )
    assert out[0].metrics[0].score == 0.0


def test_target_within_tolerance_linear():
    out = score_locations(
        {1: {"climate.jan_low_f": _wrap(28)}},  # 7 below 35, tol 15 -> ~53.33
        [PrefSpec("climate.jan_low_f", 5, "target", 35, None, 15)],
    )
    assert abs(out[0].metrics[0].score - (100 * (1 - 7 / 15))) < 1e-6


def test_missing_value_does_not_penalize():
    out = score_locations(
        {1: {"crime.violent_per_100k": {"value": None}, "tax.income.top_marginal": _wrap(2)}},
        [
            PrefSpec("crime.violent_per_100k", 5, "lower_better", 200, 800, None),
            PrefSpec("tax.income.top_marginal", 5, "lower_better", 0, 10, None),
        ],
    )
    # Crime missing -> excluded; tax 2 of [0..10] -> 80. Overall = 80.
    assert out[0].overall_score == 80.0
    assert "crime.violent_per_100k" in out[0].missing_metric_keys


def test_disabled_pref_ignored():
    out = score_locations(
        {1: {"crime.violent_per_100k": _wrap(800)}},
        [
            PrefSpec("crime.violent_per_100k", 5, "lower_better", 200, 800, None, enabled=False),
        ],
    )
    # All disabled => no scored metrics, overall None
    assert out[0].overall_score is None


def test_zero_weight_excluded():
    out = score_locations(
        {1: {"crime.violent_per_100k": _wrap(200), "tax.income.top_marginal": _wrap(10)}},
        [
            PrefSpec("crime.violent_per_100k", 0, "lower_better", 200, 800, None),
            PrefSpec("tax.income.top_marginal", 5, "lower_better", 0, 10, None),
        ],
    )
    # Crime weight 0 should be excluded; tax cap-value -> 0; overall 0
    assert out[0].overall_score == 0.0


def test_weighted_aggregation():
    out = score_locations(
        {
            1: {
                "tax.income.top_marginal": _wrap(0),  # ideal -> 100
                "crime.violent_per_100k": _wrap(800),  # cap -> 0
            }
        },
        [
            PrefSpec("tax.income.top_marginal", 1, "lower_better", 0, 10, None),
            PrefSpec("crime.violent_per_100k", 9, "lower_better", 200, 800, None),
        ],
    )
    # weighted: (1*100 + 9*0)/10 = 10
    assert out[0].overall_score == 10.0


def test_invalid_lower_better_returns_none():
    """ideal must be < cap for lower_better; otherwise score is None."""
    out = score_locations(
        {1: {"crime.violent_per_100k": _wrap(5)}},
        # ideal > cap -> invalid spec for lower_better
        [PrefSpec("crime.violent_per_100k", 5, "lower_better", 10, 5, None)],
    )
    assert out[0].metrics[0].score is None


def test_unknown_metric_silently_skipped():
    """Preferences for metric keys not in the catalog are dropped."""
    out = score_locations(
        {1: {"not.a.real.metric": _wrap(5)}},
        [PrefSpec("not.a.real.metric", 5, "lower_better", 0, 10, None)],
    )
    assert out[0].metrics == []
    assert out[0].overall_score is None


def test_ranking_order_preserved_in_input():
    """We don't reorder — sorting by score is the caller's responsibility."""
    out = score_locations(
        {
            10: {"crime.violent_per_100k": _wrap(0)},
            20: {"crime.violent_per_100k": _wrap(800)},
        },
        [PrefSpec("crime.violent_per_100k", 5, "lower_better", 0, 800, None)],
    )
    assert [o.location_id for o in out] == [10, 20]
