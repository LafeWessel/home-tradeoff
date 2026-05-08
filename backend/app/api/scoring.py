from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.location import Location
from ..models.preset import Preset
from ..resolver import ensure_metric_values, get_resolved_metrics
from ..scoring.engine import PrefSpec, score_locations
from .locations import _to_out as loc_to_out
from .presets import _to_out as preset_to_out
from .schemas import (
    ScoredLocationOut,
    ScoredMetricOut,
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

    prefs = [
        PrefSpec(
            metric_key=p.metric_key,
            weight=p.weight,
            direction=p.direction or "",  # filled in from catalog inside engine
            ideal=p.ideal,
            cap=p.cap,
            tolerance=p.tolerance,
            enabled=p.enabled,
        )
        for p in preset.preferences
    ]
    # Fill in default direction from catalog when prefspec.direction is empty
    from ..metrics_catalog import CATALOG_BY_KEY

    for pref in prefs:
        if not pref.direction:
            md = CATALOG_BY_KEY.get(pref.metric_key)
            if md is not None:
                pref.direction = md.direction.value

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
