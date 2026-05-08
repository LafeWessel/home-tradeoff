from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..metrics_catalog import CATALOG_BY_KEY
from ..models.preset import Preference, Preset
from .schemas import (
    PreferenceIn,
    PreferenceOut,
    PresetIn,
    PresetOut,
    PresetUpdate,
)

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _to_out(p: Preset) -> PresetOut:
    return PresetOut(
        id=p.id,
        name=p.name,
        description=p.description,
        created_at=p.created_at,
        updated_at=p.updated_at,
        preferences=[
            PreferenceOut(
                id=pr.id,
                metric_key=pr.metric_key,
                weight=pr.weight,
                direction=pr.direction,
                ideal=pr.ideal,
                cap=pr.cap,
                tolerance=pr.tolerance,
                enabled=pr.enabled,
            )
            for pr in p.preferences
        ],
    )


@router.get("", response_model=list[PresetOut])
def list_presets(db: Session = Depends(get_db)) -> list[PresetOut]:
    rows = db.execute(select(Preset).order_by(Preset.name)).scalars().all()
    return [_to_out(p) for p in rows]


@router.post("", response_model=PresetOut, status_code=201)
def create_preset(body: PresetIn, db: Session = Depends(get_db)) -> PresetOut:
    if db.execute(select(Preset).where(Preset.name == body.name)).scalar_one_or_none():
        raise HTTPException(409, f"preset '{body.name}' already exists")
    p = Preset(name=body.name, description=body.description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.get("/{preset_id}", response_model=PresetOut)
def get_preset(preset_id: int, db: Session = Depends(get_db)) -> PresetOut:
    p = db.get(Preset, preset_id)
    if p is None:
        raise HTTPException(404, "preset not found")
    return _to_out(p)


@router.patch("/{preset_id}", response_model=PresetOut)
def update_preset(preset_id: int, body: PresetUpdate, db: Session = Depends(get_db)) -> PresetOut:
    p = db.get(Preset, preset_id)
    if p is None:
        raise HTTPException(404, "preset not found")
    if body.name is not None:
        existing = db.execute(
            select(Preset).where(Preset.name == body.name, Preset.id != preset_id)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(409, f"preset '{body.name}' already exists")
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: int, db: Session = Depends(get_db)) -> None:
    p = db.get(Preset, preset_id)
    if p is None:
        raise HTTPException(404, "preset not found")
    db.delete(p)
    db.commit()


@router.put("/{preset_id}/preferences", response_model=PresetOut)
def replace_preferences(
    preset_id: int, body: list[PreferenceIn], db: Session = Depends(get_db)
) -> PresetOut:
    """Replace ALL preferences in this preset with the given list."""
    p = db.get(Preset, preset_id)
    if p is None:
        raise HTTPException(404, "preset not found")

    seen_keys: set[str] = set()
    for pref in body:
        if pref.metric_key not in CATALOG_BY_KEY:
            raise HTTPException(400, f"unknown metric_key: {pref.metric_key}")
        if pref.metric_key in seen_keys:
            raise HTTPException(400, f"duplicate metric_key: {pref.metric_key}")
        seen_keys.add(pref.metric_key)

    # Wipe & rebuild
    for old in list(p.preferences):
        db.delete(old)
    db.flush()
    for pref in body:
        db.add(
            Preference(
                preset_id=p.id,
                metric_key=pref.metric_key,
                weight=pref.weight,
                direction=pref.direction,
                ideal=pref.ideal,
                cap=pref.cap,
                tolerance=pref.tolerance,
                enabled=pref.enabled,
            )
        )
    db.commit()
    db.refresh(p)
    return _to_out(p)
