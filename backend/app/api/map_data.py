"""Map-ready real ward geometry, viewport LST predictions, and selection detail."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pyarrow.parquet as pq
from pyproj import Transformer
from xgboost import XGBRegressor

from backend.app.api import services
from backend.app.geospatial.ml_dataset import load_wards
from backend.app.ml.heat_hazard import score_from_model_metadata
from backend.app.ml.shap_explain import _shap_values, feature_category
from backend.app.ml.uncertainty import UncertaintyUnavailableError, spatial_cv_rmse_from_metadata


BOUNDARY = services.ROOT / "data" / "boundaries" / "pmc_pcmc_wards.geojson"
MAX_VIEW_CELLS = 2500


def _signature() -> tuple:
    paths = (services.GRID, services.GRID_METADATA, services.MODEL, services.MODEL_METADATA)
    for path in paths:
        if not path.is_file():
            raise services.DataUnavailableError(f"Required real map artifact is missing: {path}")
    return tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths)


@lru_cache(maxsize=2)
def _verified_model(signature: tuple) -> tuple[XGBRegressor, tuple[str, ...], dict]:
    """Cache a trusted model only while all four artifact signatures match."""
    # Close Parquet's Windows file handle after checking row count/schema.
    reader, grid_meta = services._real_grid()
    reader.close()
    model_meta = services._read_json(services.MODEL_METADATA)
    digest = hashlib.sha256()
    with services.GRID.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    names = grid_meta["features"]
    if (grid_meta.get("crs") != "EPSG:32643"
            or model_meta.get("dataset_version") != f"sha256:{digest.hexdigest()}"
            or model_meta.get("feature_list") != names
            or model_meta.get("dataset_rows") != grid_meta["row_count"]
            or model_meta.get("target") != "lst_c"
            or model_meta.get("objective") != "reg:squarederror"
            or model_meta.get("crs") != grid_meta.get("crs")
            or model_meta.get("resolution_m") != 30):
        raise services.DataUnavailableError("Map model metadata does not match the real 30 m ML dataset")
    # joblib uses pickle: load only the trusted model artifact produced locally.
    try:
        model = joblib.load(services.MODEL)
    except Exception as exc:
        raise services.DataUnavailableError("Cannot load the saved XGBoost model") from exc
    if (not isinstance(model, XGBRegressor) or model.n_features_in_ != len(names)
            or model.get_params().get("objective") != "reg:squarederror"):
        raise services.DataUnavailableError("Saved map model is not the matching XGBoost LST regressor")
    return model, tuple(names), model_meta


def _bundle() -> tuple[XGBRegressor, tuple[str, ...], dict]:
    return _verified_model(_signature())


def ward_boundaries() -> dict:
    """Return the same WGS84 verified-input GeoJSON used by the ML pipeline."""
    if not BOUNDARY.is_file():
        raise services.DataUnavailableError(f"PMC/PCMC ward boundary GeoJSON is missing: {BOUNDARY}")
    try:
        wards = load_wards(BOUNDARY)
        document = json.loads(BOUNDARY.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise services.DataUnavailableError(f"Cannot validate PMC/PCMC ward boundaries: {exc}") from exc
    features = []
    for ward, source in zip(wards, document["features"]):
        features.append({"type": "Feature", "geometry": source["geometry"],
                         "properties": {"ward_id": ward.ward_id, "ward_name": ward.ward_name,
                                        "municipality": ward.ward_id.split(":", 1)[0]}})
    return {"type": "FeatureCollection", "features": features,
            "source": "PMC/PCMC WGS84 ward boundary input used by ML grid; verify source/version before municipal use"}


def _batches(columns: list[str]):
    reader = pq.ParquetFile(services.GRID)
    try:
        for batch in reader.iter_batches(batch_size=20_000, columns=columns):
            yield batch.to_pydict()
    finally:
        reader.close()


def _matrix(data: dict, names: tuple[str, ...], indices: list[int] | np.ndarray) -> np.ndarray:
    matrix = np.column_stack([np.asarray(data[name], dtype=float)[indices] for name in names])
    if not np.isfinite(matrix).all():
        raise services.DataUnavailableError("Real map grid has missing or nonfinite model features")
    return matrix


def _cell_polygon(x: float, y: float) -> dict:
    """WGS84 GeoJSON footprint of one 30 m UTM grid cell centered at x/y."""
    transformer = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    corners = [(x - 15, y - 15), (x + 15, y - 15),
               (x + 15, y + 15), (x - 15, y + 15), (x - 15, y - 15)]
    return {"type": "Polygon", "coordinates": [[list(transformer.transform(px, py))
                                                   for px, py in corners]]}


@lru_cache(maxsize=2)
def _ward_prediction_summary(signature: tuple) -> dict:
    model, names, _ = _verified_model(signature)
    totals = defaultdict(lambda: [0.0, 0])
    for data in _batches(["ward_id", *names]):
        matrix = _matrix(data, names, slice(None))
        predictions = np.asarray(model.predict(matrix), dtype=float)
        if not np.isfinite(predictions).all():
            raise services.DataUnavailableError("Saved model produced nonfinite map predictions")
        for ward_id, prediction in zip(data["ward_id"], predictions):
            totals[str(ward_id)][0] += float(prediction)
            totals[str(ward_id)][1] += 1
    return {ward_id: {"predicted_lst_c": total / count, "grid_cell_count": count}
            for ward_id, (total, count) in totals.items() if count}


def ward_heat() -> dict:
    boundaries = ward_boundaries()
    summaries = _ward_prediction_summary(_signature())
    features = []
    for feature in boundaries["features"]:
        ward_id = feature["properties"]["ward_id"]
        summary = summaries.get(ward_id)
        if summary is not None:
            features.append({**feature, "properties": {**feature["properties"], **summary}})
    values = [item["properties"]["predicted_lst_c"] for item in features]
    return {"type": "FeatureCollection", "features": features,
            "temperature_range_c": {"min": min(values), "max": max(values)} if values else None,
            "unit": "°C", "aggregation": "mean XGBoost predicted LST across complete-case 30 m cells assigned to each ward",
            "missing_wards": len(boundaries["features"]) - len(features)}


def cell_heat(west: float, south: float, east: float, north: float) -> dict:
    """Return up to 2500 visible real 30 m prediction polygons; never sample silently."""
    model, names, _ = _bundle()
    selected = []
    for data in _batches(["grid_id", "ward_id", "x", "y", "latitude", "longitude", *names]):
        for i, (lat, lon) in enumerate(zip(data["latitude"], data["longitude"])):
            if south <= lat <= north and west <= lon <= east:
                selected.append({key: data[key][i] for key in data})
                if len(selected) > MAX_VIEW_CELLS:
                    return {"type": "FeatureCollection", "features": [], "too_many_cells": True,
                            "max_cells": MAX_VIEW_CELLS, "unit": "°C",
                            "message": "Zoom in until the viewport contains at most 2500 complete-case 30 m cells"}
    if not selected:
        return {"type": "FeatureCollection", "features": [], "too_many_cells": False,
                "max_cells": MAX_VIEW_CELLS, "unit": "°C", "message": "No real modeled cells in this viewport"}
    matrix = np.array([[float(row[name]) for name in names] for row in selected], dtype=float)
    if not np.isfinite(matrix).all():
        raise services.DataUnavailableError("Real map grid has invalid model features")
    predictions = np.asarray(model.predict(matrix), dtype=float)
    if not np.isfinite(predictions).all():
        raise services.DataUnavailableError("Saved model produced nonfinite map predictions")
    features = []
    for row, temperature in zip(selected, predictions):
        x, y = float(row["x"]), float(row["y"])
        features.append({"type": "Feature", "geometry": _cell_polygon(x, y),
                         "properties": {"grid_id": str(row["grid_id"]), "ward_id": str(row["ward_id"]),
                                        "predicted_lst_c": float(temperature)}})
    return {"type": "FeatureCollection", "features": features, "too_many_cells": False,
            "max_cells": MAX_VIEW_CELLS, "unit": "°C", "message": None}


def _score_and_confidence(predicted_lst_c: float) -> tuple[float | None, str, dict]:
    try:
        score = float(score_from_model_metadata(predicted_lst_c, services.MODEL_METADATA))
        score_status = "Calibrated from documented LST references"
    except ValueError as exc:
        score, score_status = None, str(exc)
    try:
        rmse, _ = spatial_cv_rmse_from_metadata(services.MODEL_METADATA)
        confidence = {"label": "Cell-level interval not calibrated", "spatial_cv_rmse_c": rmse,
                      "note": "Held-out spatial CV RMSE is a model error summary, not a cell-level prediction interval."}
    except UncertaintyUnavailableError as exc:
        confidence = {"label": "Unavailable", "spatial_cv_rmse_c": None, "note": str(exc)}
    return score, score_status, confidence


def _factor_rows(names: tuple[str, ...], matrix: np.ndarray, model: XGBRegressor) -> list[dict]:
    _, values = _shap_values(model, matrix)
    signed = values.mean(axis=0)
    magnitude = np.abs(values).mean(axis=0)
    rows = [{"feature": name, "category": feature_category(name),
             "mean_shap_value_c": float(signed[i]),
             "mean_abs_shap_c": float(magnitude[i]),
             "direction": "warming" if signed[i] > 0 else "cooling" if signed[i] < 0 else "neutral"}
            for i, name in enumerate(names)]
    rows.sort(key=lambda item: item["mean_abs_shap_c"], reverse=True)
    return rows[:5]


def cell_detail(grid_id: str) -> dict:
    model, names, model_meta = _bundle()
    found = None
    for data in _batches(["grid_id", "ward_id", "ward_name", "x", "y", "latitude", "longitude", *names]):
        for i, value in enumerate(data["grid_id"]):
            if str(value) == grid_id:
                if found is not None:
                    raise services.DataUnavailableError("Duplicate grid ID in real map dataset")
                found = {key: data[key][i] for key in data}
    if found is None:
        raise services.ResourceNotFoundError(f"Grid cell not found: {grid_id}")
    matrix = np.array([[float(found[name]) for name in names]], dtype=float)
    prediction = float(model.predict(matrix)[0])
    if not math.isfinite(prediction):
        raise services.DataUnavailableError("Saved model returned nonfinite LST")
    score, score_status, confidence = _score_and_confidence(prediction)
    return {"selection_type": "grid_cell", "grid_id": grid_id,
            "ward_id": str(found["ward_id"]), "ward_name": str(found["ward_name"]),
            "latitude": float(found["latitude"]), "longitude": float(found["longitude"]),
            "geometry": _cell_polygon(float(found["x"]), float(found["y"])),
            "predicted_lst_c": prediction, "heat_hazard_score": score,
            "heat_hazard_score_status": score_status, "confidence": confidence,
            "top_shap_factors": _factor_rows(names, matrix, model),
            "shap_scope": "TreeSHAP contributions for this one grid-cell prediction; not causal effects",
            "model_dataset_version": model_meta["dataset_version"], "unit": "°C"}


def ward_detail(ward_id: str) -> dict:
    boundary_ids = {feature["properties"]["ward_id"] for feature in ward_boundaries()["features"]}
    if ward_id not in boundary_ids:
        raise services.ResourceNotFoundError(f"Ward boundary not found: {ward_id}")
    model, names, model_meta = _bundle()
    summary = _ward_prediction_summary(_signature()).get(ward_id)
    if summary is None:
        raise services.ResourceNotFoundError(f"No complete-case model grid cells in ward: {ward_id}")
    sample = []
    seen = 0
    rng = np.random.default_rng(42)
    ward_name = None
    for data in _batches(["ward_id", "ward_name", *names]):
        for i, found_id in enumerate(data["ward_id"]):
            if found_id != ward_id:
                continue
            ward_name = str(data["ward_name"][i])
            seen += 1
            row = [float(data[name][i]) for name in names]
            if len(sample) < 100:
                sample.append(row)
            else:
                pick = int(rng.integers(0, seen))
                if pick < 100:
                    sample[pick] = row
    matrix = np.asarray(sample, dtype=float)
    if not np.isfinite(matrix).all():
        raise services.DataUnavailableError("Ward SHAP sample contains invalid model features")
    prediction = float(summary["predicted_lst_c"])
    score, score_status, confidence = _score_and_confidence(prediction)
    return {"selection_type": "ward", "ward_id": ward_id, "ward_name": ward_name,
            "grid_cell_count": summary["grid_cell_count"], "predicted_lst_c": prediction,
            "heat_hazard_score": score, "heat_hazard_score_status": score_status,
            "confidence": confidence, "top_shap_factors": _factor_rows(names, matrix, model),
            "shap_scope": f"Mean TreeSHAP across a deterministic sample of {len(sample)} ward cells; not causal effects",
            "model_dataset_version": model_meta["dataset_version"], "unit": "°C"}
