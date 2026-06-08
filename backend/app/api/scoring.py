from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.location import GeoLevel, Location
from ..models.preset import Preset
from ..resolver import ensure_metric_values, get_bulk_resolved_metrics, get_resolved_metrics
from ..scoring.engine import PrefSpec, score_locations
from .locations import _to_out as loc_to_out
from .presets import _to_out as preset_to_out
from .schemas import (
    MapScoreEntry,
    MapScoreResponse,
    ScoredLocationOut,
    ScoredMetricOut,
    ScorePreviewRequest,
    ScorePreviewResponse,
    ScoreRequest,
    ScoreResponse,
)

router = APIRouter(prefix="/api", tags=["scoring"])


@router.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest, db: Session = Depends(get_db)) -> ScoreResponse:
    preset = db.get(Preset, req.preset_id)
    if preset is None:
        raise HTTPException(404, "preset not found")

    locs = db.execute(select(Location).where(Location.geoid.in_(req.geoids))).scalars().all()
    found = {l.geoid for l in locs}
    missing = [g for g in req.geoids if g not in found]
    if missing:
        raise HTTPException(404, f"unknown geoids: {missing}")

    by_geoid = {l.geoid: l for l in locs}
    ordered = [by_geoid[g] for g in req.geoids]

    ensure_metric_values(db, ordered)

    location_metrics = {loc.id: get_resolved_metrics(db, loc) for loc in ordered}

    prefs = _build_prefs(preset.preferences)
    results = score_locations(location_metrics, prefs)
    by_loc_id = {loc.id: loc for loc in ordered}
    return ScoreResponse(
        preset=preset_to_out(preset),
        locations=[
            ScoredLocationOut(
                location=loc_to_out(by_loc_id[r.location_id]),
                overall_score=r.overall_score,
                metrics=[ScoredMetricOut(**vars(m)) for m in r.metrics],
                missing_metric_keys=r.missing_metric_keys,
            )
            for r in results
        ],
    )


def _build_prefs(raw_prefs: list) -> list[PrefSpec]:
    from ..metrics_catalog import CATALOG_BY_KEY

    prefs = [
        PrefSpec(
            metric_key=p.metric_key,
            weight=p.weight,
            direction=p.direction or "",
            ideal=p.ideal,
            cap=p.cap,
            tolerance=p.tolerance,
            enabled=p.enabled,
        )
        for p in raw_prefs
    ]
    for pref in prefs:
        if not pref.direction:
            md = CATALOG_BY_KEY.get(pref.metric_key)
            if md is not None:
                pref.direction = md.direction.value
    return prefs


@router.get("/score/map", response_model=MapScoreResponse)
def score_map(
    level: str,
    preset_id: int,
    metric_key: str | None = None,
    db: Session = Depends(get_db),
) -> MapScoreResponse:
    """Return per-location scores for all states or counties, for use as a map layer.

    Uses cached metric values only (no live fetch) so it's fast even for 3k+ counties.
    Score is 0–100 when the metric has a preference in the preset, else null (raw_value
    is always returned for metric-key mode to allow client-side normalization).
    """
    if level not in ("state", "county"):
        raise HTTPException(400, "level must be 'state' or 'county'")

    preset = db.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(404, "preset not found")

    geo_level = GeoLevel(level)
    locs = db.execute(
        select(Location).where(Location.level == geo_level)
    ).scalars().all()

    location_metrics = get_bulk_resolved_metrics(db, list(locs))

    prefs = _build_prefs(preset.preferences)
    if metric_key:
        prefs = [p for p in prefs if p.metric_key == metric_key]

    scores: dict[str, MapScoreEntry] = {}

    if metric_key and not prefs:
        # Metric absent from preset — return raw values so client can color by min/max
        for loc in locs:
            mv = location_metrics.get(loc.id, {}).get(metric_key, {})
            scores[loc.geoid] = MapScoreEntry(
                score=None,
                raw_value=mv.get("value"),
                lat=loc.lat,
                lon=loc.lon,
            )
        return MapScoreResponse(scores=scores)

    results = score_locations(location_metrics, prefs)
    loc_by_id = {loc.id: loc for loc in locs}

    for r in results:
        loc = loc_by_id[r.location_id]
        if metric_key:
            sm = next((m for m in r.metrics if m.metric_key == metric_key), None)
            scores[loc.geoid] = MapScoreEntry(
                score=sm.score if sm else None,
                raw_value=sm.raw_value if sm else None,
                lat=loc.lat,
                lon=loc.lon,
            )
        else:
            scores[loc.geoid] = MapScoreEntry(
                score=r.overall_score,
                raw_value=None,
                lat=loc.lat,
                lon=loc.lon,
            )

    return MapScoreResponse(scores=scores)


@router.post("/score/preview", response_model=ScorePreviewResponse)
def score_preview(req: ScorePreviewRequest, db: Session = Depends(get_db)) -> ScorePreviewResponse:
    locs = db.execute(select(Location).where(Location.geoid.in_(req.geoids))).scalars().all()
    found = {l.geoid for l in locs}
    missing = [g for g in req.geoids if g not in found]
    if missing:
        raise HTTPException(404, f"unknown geoids: {missing}")

    by_geoid = {l.geoid: l for l in locs}
    ordered = [by_geoid[g] for g in req.geoids]

    ensure_metric_values(db, ordered)
    location_metrics = {loc.id: get_resolved_metrics(db, loc) for loc in ordered}

    prefs = _build_prefs(req.preferences)
    results = score_locations(location_metrics, prefs)
    by_loc_id = {loc.id: loc for loc in ordered}
    return ScorePreviewResponse(
        locations=[
            ScoredLocationOut(
                location=loc_to_out(by_loc_id[r.location_id]),
                overall_score=r.overall_score,
                metrics=[ScoredMetricOut(**vars(m)) for m in r.metrics],
                missing_metric_keys=r.missing_metric_keys,
            )
            for r in results
        ]
    )
