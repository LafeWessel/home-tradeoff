"""Pydantic schemas — the wire format between backend and frontend."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LocationOut(BaseModel):
    id: int
    geoid: str
    level: str
    name: str
    display_name: str
    state_abbr: str | None
    state_fips: str | None
    parent_geoid: str | None
    population: int | None
    lat: float | None
    lon: float | None


class MetricDefOut(BaseModel):
    key: str
    label: str
    category: str
    unit: str
    direction: str
    description: str
    source_label: str
    finest_level: str


class MetricValueOut(BaseModel):
    value: float | None
    source: str | None
    source_year: int | None
    fetched_at: str | None
    level_resolved: str | None
    resolved_geoid: str | None


class LocationMetricsOut(BaseModel):
    location: LocationOut
    metrics: dict[str, MetricValueOut]


class CompareRequest(BaseModel):
    geoids: list[str] = Field(..., min_length=1, max_length=20)


class CompareResponse(BaseModel):
    metrics: list[MetricDefOut]
    locations: list[LocationMetricsOut]


class PreferenceIn(BaseModel):
    metric_key: str
    weight: float = 5.0
    direction: Literal["lower_better", "higher_better", "target"] | None = None
    ideal: float | None = None
    cap: float | None = None
    tolerance: float | None = None
    enabled: bool = True


class PreferenceOut(PreferenceIn):
    id: int


class PresetIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = None


class PresetOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    preferences: list[PreferenceOut]


class PresetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ScoreRequest(BaseModel):
    preset_id: int
    geoids: list[str] = Field(..., min_length=1, max_length=20)


class ScoredMetricOut(BaseModel):
    metric_key: str
    raw_value: float | None
    score: float | None
    weight: float
    direction: str
    ideal: float | None
    cap: float | None
    tolerance: float | None


class ScoredLocationOut(BaseModel):
    location: LocationOut
    overall_score: float | None
    metrics: list[ScoredMetricOut]
    missing_metric_keys: list[str]


class ScoreResponse(BaseModel):
    preset: PresetOut
    locations: list[ScoredLocationOut]
