"""Weighted ideal-or-range scoring.

Each preference (one per metric) defines:
  - weight (0..10) — relative importance
  - direction (lower_better | higher_better | target) — derived from metric, overridable
  - ideal — the "anchor": ceiling for lower_better, floor for higher_better, target value for target
  - cap — the unacceptable threshold (the worst value still earning >0 credit)
  - tolerance — for target only: the ± range outside which credit hits 0

Score is 0..100 per metric; final per-location score is weighted-mean rescaled to 0..100.

If a location is missing a value for a metric, that metric is **excluded** from
the location's denominator (so missing data doesn't unfairly penalize). The
report tells the UI which metrics were missing.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..metrics_catalog import CATALOG_BY_KEY


@dataclass
class ScoredMetric:
    metric_key: str
    raw_value: float | None
    score: float | None  # None if missing
    weight: float
    direction: str
    ideal: float | None
    cap: float | None
    tolerance: float | None
    level_resolved: str | None = None


@dataclass
class ScoredLocation:
    location_id: int
    overall_score: float | None  # None if no metrics scored
    metrics: list[ScoredMetric]
    missing_metric_keys: list[str]


def _score_lower_better(value: float, ideal: float, cap: float) -> float:
    if value <= ideal:
        return 100.0
    if value >= cap:
        return 0.0
    return 100.0 * (cap - value) / (cap - ideal)


def _score_higher_better(value: float, ideal: float, cap: float) -> float:
    if value >= ideal:
        return 100.0
    if value <= cap:
        return 0.0
    return 100.0 * (value - cap) / (ideal - cap)


def _score_target(value: float, target: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 100.0 if value == target else 0.0
    diff = abs(value - target)
    if diff >= tolerance:
        return 0.0
    return 100.0 * (1.0 - diff / tolerance)


def _score_one(
    value: float | None,
    direction: str,
    ideal: float | None,
    cap: float | None,
    tolerance: float | None,
) -> float | None:
    if value is None:
        return None
    if direction == "lower_better":
        if ideal is None or cap is None or cap <= ideal:
            return None
        return _score_lower_better(value, ideal, cap)
    if direction == "higher_better":
        if ideal is None or cap is None or cap >= ideal:
            return None
        return _score_higher_better(value, ideal, cap)
    if direction == "target":
        if ideal is None or tolerance is None or tolerance <= 0:
            return None
        return _score_target(value, ideal, tolerance)
    return None


@dataclass
class PrefSpec:
    metric_key: str
    weight: float
    direction: str
    ideal: float | None
    cap: float | None
    tolerance: float | None
    enabled: bool = True


def score_locations(
    location_metrics: dict[int, dict[str, dict]],
    preferences: list[PrefSpec],
) -> list[ScoredLocation]:
    """
    location_metrics: {location_id: {metric_key: {"value": float|None, ...}}}
    preferences: active prefs from the user's preset

    Returns a list of ScoredLocation, one per location_id, in input order.
    """
    out: list[ScoredLocation] = []
    active_prefs = [p for p in preferences if p.enabled and p.weight > 0]

    for loc_id, metrics in location_metrics.items():
        scored: list[ScoredMetric] = []
        missing: list[str] = []
        weighted_sum = 0.0
        weight_total = 0.0

        for p in active_prefs:
            mdef = CATALOG_BY_KEY.get(p.metric_key)
            if mdef is None:
                continue
            mv = metrics.get(p.metric_key, {})
            value = mv.get("value")
            direction = p.direction or mdef.direction.value
            s = _score_one(value, direction, p.ideal, p.cap, p.tolerance)
            scored.append(
                ScoredMetric(
                    metric_key=p.metric_key,
                    raw_value=value,
                    score=s,
                    weight=p.weight,
                    direction=direction,
                    ideal=p.ideal,
                    cap=p.cap,
                    tolerance=p.tolerance,
                    level_resolved=mv.get("level_resolved"),
                )
            )
            if s is None:
                missing.append(p.metric_key)
                continue
            weighted_sum += p.weight * s
            weight_total += p.weight

        overall = (weighted_sum / weight_total) if weight_total > 0 else None
        out.append(
            ScoredLocation(
                location_id=loc_id,
                overall_score=overall,
                metrics=scored,
                missing_metric_keys=missing,
            )
        )
    return out
