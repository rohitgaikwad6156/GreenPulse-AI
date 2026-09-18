"""Bounded GeoJSON routes for the interactive municipal heat map."""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.api import map_data, services


class FeatureCollectionResponse(BaseModel):
    type: str
    features: list[dict[str, Any]]
    source: str | None = None
    temperature_range_c: dict[str, float] | None = None
    unit: str | None = None
    aggregation: str | None = None
    missing_wards: int | None = None
    too_many_cells: bool | None = None
    max_cells: int | None = None
    message: str | None = None


class ConfidenceResponse(BaseModel):
    label: str
    spatial_cv_rmse_c: float | None
    note: str


class MapDetailResponse(BaseModel):
    selection_type: str
    grid_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geometry: dict[str, Any] | None = None
    ward_id: str
    ward_name: str
    grid_cell_count: int | None = None
    predicted_lst_c: float
    heat_hazard_score: float | None
    heat_hazard_score_status: str
    confidence: ConfidenceResponse
    top_shap_factors: list[dict[str, Any]]
    shap_scope: str
    model_dataset_version: str
    unit: str


router = APIRouter(prefix="/api/map", tags=["Interactive heat map"])


def _mapped(call, *args):
    try:
        return call(*args)
    except services.ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (services.DataUnavailableError, OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/wards", response_model=FeatureCollectionResponse)
def map_wards() -> dict:
    """WGS84 PMC/PCMC ward polygons from the verified-input boundary file."""
    return _mapped(map_data.ward_boundaries)


@router.get("/heat/wards", response_model=FeatureCollectionResponse)
def map_ward_heat() -> dict:
    """Ward polygons colored by mean predicted complete-case cell LST."""
    return _mapped(map_data.ward_heat)


@router.get("/heat/cells", response_model=FeatureCollectionResponse)
def map_cell_heat(
    west: float = Query(ge=-180, le=180), south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180), north: float = Query(ge=-90, le=90),
) -> dict:
    """Viewport 30 m polygons, capped at 2500; zoom in if the view exceeds cap."""
    if west >= east or south >= north:
        raise HTTPException(status_code=422, detail="Viewport west/east or south/north bounds are reversed")
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        raise HTTPException(status_code=422, detail="Viewport bounds must be finite")
    return _mapped(map_data.cell_heat, west, south, east, north)


@router.get("/cell/{grid_id}", response_model=MapDetailResponse)
def map_cell_detail(grid_id: str) -> dict:
    """Predicted LST, calibrated score if available, error status and local SHAP."""
    if not grid_id.strip() or len(grid_id) > 120:
        raise HTTPException(status_code=422, detail="grid_id must be 1–120 nonblank characters")
    return _mapped(map_data.cell_detail, grid_id)


@router.get("/ward/{ward_id}", response_model=MapDetailResponse)
def map_ward_detail(ward_id: str) -> dict:
    """Mean predicted ward LST and sampled descriptive ward SHAP factors."""
    if not ward_id.strip() or len(ward_id) > 120:
        raise HTTPException(status_code=422, detail="ward_id must be 1–120 nonblank characters")
    return _mapped(map_data.ward_detail, ward_id)
