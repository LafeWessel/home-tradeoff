from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..metrics_catalog import CATALOG
from ..models.location import Location
from ..resolver import ensure_metric_values, get_resolved_metrics
from .locations import _to_out
from .schemas import (
    CompareRequest,
    CompareResponse,
    LocationMetricsOut,
    MetricDefOut,
    MetricValueOut,
)  # noqa: F401  (CompareRequest etc. used as response/request types)

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics", response_model=list[MetricDefOut])
def list_metrics() -> list[MetricDefOut]:
    return [
        MetricDefOut(
            key=m.key,
            label=m.label,
            category=m.category,
            unit=m.unit,
            direction=m.direction.value,
            description=m.description,
            source_label=m.source_label,
            finest_level=m.finest_level,
        )
        for m in CATALOG
    ]


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    locs = (
        db.execute(select(Location).where(Location.geoid.in_(req.geoids))).scalars().all()
    )
    if len(locs) != len(set(req.geoids)):
        found = {l.geoid for l in locs}
        missing = [g for g in req.geoids if g not in found]
        raise HTTPException(404, f"unknown geoids: {missing}")

    # Preserve request order
    by_geoid = {l.geoid: l for l in locs}
    locs = [by_geoid[g] for g in req.geoids]

    ensure_metric_values(db, locs)

    out = CompareResponse(
        metrics=list_metrics(),
        locations=[
            LocationMetricsOut(
                location=_to_out(loc),
                metrics={k: MetricValueOut(**v) for k, v in get_resolved_metrics(db, loc).items()},
            )
            for loc in locs
        ],
    )
    return out
