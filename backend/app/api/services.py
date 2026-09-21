"""Read only verified local artifacts; never fall back to the demo CSV."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GRID = ROOT / "data" / "processed" / "greenpulse_ml_grid.parquet"
GRID_METADATA = ROOT / "data" / "processed" / "metadata.json"
MODEL = ROOT / "models" / "xgboost_lst.joblib"
MODEL_METADATA = ROOT / "models" / "model_metadata.json"
CATALOG = ROOT / "data" / "interventions" / "location_catalog.json"
VALIDATION_IMPORTS = ROOT / "data" / "validation" / "imported"
VALIDATION_REPORTS = ROOT / "data" / "validation" / "reports"
SENSOR_IMPORTS = ROOT / "data" / "research" / "sensors"
RESEARCH_LAYERS = ROOT / "data" / "research" / "research_layers.json"
SOURCE_MANIFEST = ROOT / "data" / "source_manifest.json"


class DataUnavailableError(RuntimeError):
    """A required real artifact has not yet been generated."""


class ResourceNotFoundError(LookupError):
    """A requested grid cell or ward is absent from the real dataset."""


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise DataUnavailableError(f"Required real artifact is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataUnavailableError(f"Cannot read artifact metadata: {path}") from exc
    if not isinstance(value, dict):
        raise DataUnavailableError(f"Artifact metadata is invalid: {path}")
    return value


def _real_grid():
    """Open the real Parquet and verify its companion metadata."""
    if not GRID.is_file():
        raise DataUnavailableError(f"Required real ML grid is missing: {GRID}")
    metadata = _read_json(GRID_METADATA)
    if (metadata.get("raster_resolution_m") != 30
            or not isinstance(metadata.get("features"), list)
            or not isinstance(metadata.get("row_count"), int)
            or metadata["row_count"] <= 0):
        raise DataUnavailableError("ML grid metadata lacks a valid 30 m schema and row count")
    import pyarrow.parquet as pq
    reader = None
    try:
        reader = pq.ParquetFile(GRID)
        required = {"grid_id", "x", "y", "latitude", "longitude", "ward_id",
                    "ward_name", "lst_c", *metadata["features"]}
        if reader.metadata.num_rows != metadata["row_count"] or not required.issubset(reader.schema_arrow.names):
            raise DataUnavailableError("ML grid and metadata columns or row count disagree")
    except DataUnavailableError:
        if reader is not None:
            reader.close()
        raise
    except Exception as exc:
        if reader is not None:
            reader.close()
        raise DataUnavailableError("Cannot read real ML grid Parquet") from exc
    return reader, metadata


def model_metrics() -> dict:
    if not MODEL.is_file():
        raise DataUnavailableError(f"Required trained XGBoost model is missing: {MODEL}")
    metadata = _read_json(MODEL_METADATA)
    if (metadata.get("target") != "lst_c" or metadata.get("objective") != "reg:squarederror"
            or not isinstance(metadata.get("spatial_cv_metrics"), dict)
            or not metadata["spatial_cv_metrics"]
            or not metadata.get("dataset_version")
            or not metadata.get("spatial_validation_method")):
        raise DataUnavailableError("Model metadata lacks validated spatial LST metrics")
    return {"target": "lst_c", "unit": "°C", "model_name": metadata.get("model_name", "XGBoost LST regressor"),
            "dataset_version": metadata["dataset_version"],
            "spatial_validation_method": metadata["spatial_validation_method"],
            "metrics": metadata["spatial_cv_metrics"]}


def list_wards() -> dict:
    reader, _ = _real_grid()
    counts = Counter()
    names = {}
    with reader:
        for batch in reader.iter_batches(batch_size=50_000, columns=["ward_id", "ward_name"]):
            data = batch.to_pydict()
            for ward_id, ward_name in zip(data["ward_id"], data["ward_name"]):
                if ward_id in names and names[ward_id] != ward_name:
                    raise DataUnavailableError(f"Conflicting ward names for {ward_id}")
                names[ward_id] = ward_name
                counts[ward_id] += 1
    wards = [{"ward_id": ward_id, "ward_name": names[ward_id], "grid_cell_count": counts[ward_id]}
             for ward_id in sorted(counts)]
    return {"wards": wards, "total": len(wards), "source": "real processed 30 m ML grid"}


def list_grid(*, limit: int, offset: int, ward_id: str | None) -> dict:
    reader, metadata = _real_grid()
    base = ["grid_id", "ward_id", "ward_name", "latitude", "longitude", "x", "y", "lst_c"]
    features = metadata["features"]
    cells = []
    matched = 0
    with reader:
        for batch in reader.iter_batches(batch_size=10_000, columns=[*base, *features]):
            data = batch.to_pydict()
            for index in range(batch.num_rows):
                if ward_id is not None and data["ward_id"][index] != ward_id:
                    continue
                if offset <= matched < offset + limit:
                    cells.append({
                        "grid_id": str(data["grid_id"][index]),
                        "ward_id": str(data["ward_id"][index]),
                        "ward_name": str(data["ward_name"][index]),
                        "latitude": float(data["latitude"][index]),
                        "longitude": float(data["longitude"][index]),
                        "x": float(data["x"][index]), "y": float(data["y"][index]),
                        "observed_lst_c": float(data["lst_c"][index]),
                        "features": {name: float(data[name][index]) for name in features},
                    })
                matched += 1
    if ward_id is not None and matched == 0:
        raise ResourceNotFoundError(f"Ward was not found in the real ML grid: {ward_id}")
    return {"cells": cells, "total": matched, "limit": limit, "offset": offset,
            "source": "real processed 30 m ML grid; observed LST is not model prediction"}


def ward_summary(ward_id: str) -> dict:
    reader, _ = _real_grid()
    count = 0
    total = 0.0
    minimum = math.inf
    maximum = -math.inf
    ward_name = None
    with reader:
        for batch in reader.iter_batches(batch_size=50_000, columns=["ward_id", "ward_name", "lst_c"]):
            data = batch.to_pydict()
            for found_id, found_name, value in zip(data["ward_id"], data["ward_name"], data["lst_c"]):
                if found_id != ward_id:
                    continue
                if ward_name is not None and ward_name != found_name:
                    raise DataUnavailableError(f"Conflicting ward names for {ward_id}")
                ward_name = found_name
                number = float(value)
                if not math.isfinite(number):
                    raise DataUnavailableError(f"Nonfinite observed LST in ward {ward_id}")
                count += 1
                total += number
                minimum = min(minimum, number)
                maximum = max(maximum, number)
    if not count:
        raise ResourceNotFoundError(f"Ward was not found in the real ML grid: {ward_id}")
    return {"ward_id": ward_id, "ward_name": ward_name, "grid_cell_count": count,
            "observed_lst_c_mean": total / count, "observed_lst_c_min": minimum,
            "observed_lst_c_max": maximum, "unit": "°C",
            "source": "observed Landsat LST in real processed 30 m ML grid"}


def predict_grid_cell(grid_id: str) -> dict:
    if not all(path.is_file() for path in (GRID, GRID_METADATA, MODEL, MODEL_METADATA)):
        raise DataUnavailableError("Real ML grid, trained model, and matching metadata are required")
    import numpy as np
    from backend.app.simulation.tree_canopy import load_saved_grid_cell
    try:
        model, names, features, metadata = load_saved_grid_cell(GRID, MODEL, MODEL_METADATA, grid_id)
    except ValueError as exc:
        if "grid_id was not found" in str(exc):
            raise ResourceNotFoundError(str(exc)) from exc
        raise DataUnavailableError(f"Saved model/grid validation failed: {exc}") from exc
    estimate = float(model.predict(np.array([[features[name] for name in names]], dtype=float))[0])
    if not math.isfinite(estimate):
        raise DataUnavailableError("Saved model returned a nonfinite LST prediction")
    return {"grid_id": grid_id, "predicted_lst_c": estimate,
            "target": "land_surface_temperature", "unit": "°C",
            "model_dataset_version": metadata["dataset_version"]}


def methodology() -> dict:
    optimizer_location_available = False
    if CATALOG.is_file():
        try:
            from backend.app.optimizer.location_catalog import list_planning_locations
            optimizer_location_available = bool(
                list_planning_locations(CATALOG, project_root=ROOT)["total"])
        except RuntimeError:
            optimizer_location_available = False
    from backend.app.validation.workflow import list_imported_datasets
    real_validation_available = bool(list_imported_datasets(VALIDATION_IMPORTS)["total"])
    return {
        "system": "GreenPulse AI — An AI-powered Urban Climate Decision-Support System",
        "target": "continuous Landsat land surface temperature (LST) in °C",
        "spatial_unit": "30 m × 30 m analysis cell",
        "reporting_unit": "PMC/PCMC ward",
        "pipeline": ["Satellite/GIS data", "30 m spatial grid", "Feature engineering",
                     "XGBoost LST prediction", "5 km spatial block validation", "TreeSHAP explanation",
                     "What-if intervention simulation", "Approximate prediction uncertainty",
                     "MILP climate action optimization", "Ward-level action plan",
                     "Post-implementation validation"],
        "validation": "Five-fold spatial block cross-validation; post-implementation Difference-in-Differences requires observed pre/post treated and control cells.",
        "limitations": ["LST is not pedestrian air temperature.",
                        "SHAP explains model predictions and does not prove causation.",
                        "Intervention estimates need local calibration and later field validation.",
                        "The optimization is optimal only under its modeled objective, assumptions and constraints."],
        "data_status": {"real_ml_grid_available": GRID.is_file() and GRID_METADATA.is_file(),
                        "trained_model_available": MODEL.is_file() and MODEL_METADATA.is_file(),
                        "intervention_catalog_available": CATALOG.is_file(),
                        "optimizer_location_available": optimizer_location_available,
                        "real_validation_dataset_available": real_validation_available},
    }
