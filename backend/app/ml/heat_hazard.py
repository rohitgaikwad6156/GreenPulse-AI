"""Transparent post-processing of predicted LST into a Heat Hazard Score.

This module never trains on the score. References must be observed LST from
the same documented March–May season, including a separate peri-urban sample.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.ml.baselines import _read_ml_inputs
from backend.app.ml.xgboost_lst import _sha256


def heat_hazard_score(predicted_lst_c: float | np.ndarray,
                      background_lst_c: float, hot_reference_lst_c: float
                      ) -> float | np.ndarray:
    """Return 0–100 Heat Hazard Score from predicted surface temperature.

    All temperatures are LST in °C. Input may be a finite scalar or finite
    NumPy array. References must be finite, above absolute zero, and strictly
    ordered. Missing, nonnumeric, or physically impossible input raises
    ValueError. The output is dimensionless and clipped to [0, 100].
    """
    try:
        prediction = np.asarray(predicted_lst_c, dtype=np.float64)
        background = float(background_lst_c)
        hot = float(hot_reference_lst_c)
    except (TypeError, ValueError) as exc:
        raise ValueError("Heat Hazard Score requires numeric LST values in °C") from exc
    if (prediction.ndim > 1 or prediction.size == 0 or not np.isfinite(prediction).all()
            or np.any(prediction <= -273.15) or not math.isfinite(background)
            or not math.isfinite(hot) or background <= -273.15 or hot <= background):
        raise ValueError("LST and references must be finite, physical, and hot reference must exceed background")
    result = 100.0 * np.clip((prediction - background) / (hot - background), 0.0, 1.0)
    return float(result) if prediction.ndim == 0 else result


def _read_documented_periurban_sample(sample_path: Path, provenance_path: Path,
                                      municipal_ids: set[str], date_range: str
                                      ) -> tuple[np.ndarray, dict]:
    if not sample_path.is_file() or not provenance_path.is_file():
        raise ValueError("Documented real peri-urban LST Parquet and provenance JSON are required")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read peri-urban LST provenance JSON") from exc
    required_text = ("source_organization", "source_product", "source_scene_or_composite",
                     "periurban_area_definition", "area_boundary_source", "qa_mask_method")
    if (not isinstance(provenance, dict)
            or any(not isinstance(provenance.get(key), str) or not provenance[key].strip()
                   for key in required_text)
            or provenance.get("temperature_variable") != "land_surface_temperature"
            or provenance.get("units") != "degC"
            or provenance.get("date_range") != date_range
            or provenance.get("region") != "Pune rural/peri-urban outside PMC/PCMC"):
        raise ValueError("Peri-urban provenance must document same-season observed LST, QA, and area selection")
    try:
        table = pq.read_table(sample_path, columns=["grid_id", "lst_c"])
        values = np.asarray(table.column("lst_c").to_numpy(), dtype=np.float64)
        identifiers = [str(value) for value in table.column("grid_id").to_pylist()]
    except (OSError, KeyError, TypeError, ValueError, pa.ArrowException) as exc:
        raise ValueError("Peri-urban Parquet requires grid_id and numeric lst_c columns") from exc
    if (len(values) == 0 or len(identifiers) != len(set(identifiers))
            or any(not identifier or identifier == "None" for identifier in identifiers)
            or set(identifiers) & municipal_ids or not np.isfinite(values).all()
            or np.any(values <= -273.15)):
        raise ValueError("Peri-urban sample has missing, duplicate, overlapping, or invalid LST cells")
    return values, provenance


def derive_heat_hazard_references(dataset_path: Path, model_path: Path,
                                  model_metadata_path: Path, periurban_path: Path,
                                  periurban_provenance_path: Path) -> dict:
    """Store observed-LST score references in the existing model metadata.

    The background is the median observed March–May LST of a documented
    separate Pune rural/peri-urban sample. The hot reference is the 95th
    percentile of observed municipal LST in the model's matching real table.
    No metadata is written if any provenance or consistency check fails.
    """
    if not model_path.is_file() or not model_metadata_path.is_file():
        raise ValueError("Real trained XGBoost model and metadata are required before score calibration")
    _, _, observed, _, features, dataset_metadata = _read_ml_inputs(
        dataset_path, dataset_path.with_name("metadata.json"))
    try:
        model_metadata = json.loads(model_metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read model metadata") from exc
    if (model_metadata.get("dataset_version") != f"sha256:{_sha256(dataset_path)}"
            or model_metadata.get("feature_list") != features
            or model_metadata.get("dataset_rows") != len(observed)
            or model_metadata.get("target") != "lst_c"
            or model_metadata.get("objective") != "reg:squarederror"
            or model_metadata.get("dataset_date_range") != dataset_metadata.get("date_range")
            or model_metadata.get("crs") != dataset_metadata.get("crs")
            or model_metadata.get("resolution_m") != dataset_metadata.get("raster_resolution_m")):
        raise ValueError("Model metadata and real observed-LST table do not match")
    date_range = dataset_metadata.get("date_range")
    if not isinstance(date_range, str) or not re.fullmatch(r"(\d{4})-03-01/\1-05-31", date_range):
        raise ValueError("ML table must document its March–May date range")
    try:
        municipal_ids = {str(item) for item in pq.read_table(dataset_path, columns=["grid_id"])
                         .column("grid_id").to_pylist()}
    except (OSError, KeyError, pa.ArrowException) as exc:
        raise ValueError("ML dataset must contain grid_id") from exc
    if len(municipal_ids) != len(observed):
        raise ValueError("Municipal grid_id values must be unique")
    background_values, provenance = _read_documented_periurban_sample(
        periurban_path, periurban_provenance_path, municipal_ids, date_range)
    background = float(np.median(background_values))
    hot = float(np.percentile(observed, 95))
    if hot <= background:
        raise ValueError("Observed municipal 95th percentile must exceed peri-urban median")
    reference = {
        "name": "Heat Hazard Score", "status": "calibrated", "unit": "dimensionless 0-100",
        "formula": "100 * clip((predicted_lst_c - background_lst_c) / (hot_reference_lst_c - background_lst_c), 0, 1)",
        "background_lst_c": background, "background_method": "median observed QA-valid peri-urban LST",
        "background_rows": int(len(background_values)),
        "background_source": str(periurban_path),
        "background_source_sha256": _sha256(periurban_path),
        "background_provenance_sha256": _sha256(periurban_provenance_path),
        "background_provenance": provenance,
        "hot_reference_lst_c": hot, "hot_reference_method": "95th percentile observed QA-valid municipal LST",
        "hot_reference_percentile": 95, "hot_reference_rows": int(len(observed)),
        "hot_reference_dataset_sha256": _sha256(dataset_path),
        "model_dataset_version": model_metadata["dataset_version"],
        "reference_date_range": date_range,
        "calibrated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": "0 is at or below the observed peri-urban median; 100 is at or above the observed municipal summer 95th percentile; intermediate values linearly locate predicted LST between them.",
        "limitations": ["A relative LST hazard index, not a human health risk estimate.",
                        "LST is not pedestrian air temperature.",
                        "A single March–May season is a seasonal reference, not a historical extreme.",
                        "Clipping hides differences below the background and above the hot reference."]}
    model_metadata["heat_hazard_score"] = reference
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json",
                                     prefix="heat_hazard_", dir=model_metadata_path.parent,
                                     delete=False) as stream:
        temporary_path = Path(stream.name)
        json.dump(model_metadata, stream, indent=2, allow_nan=False)
        stream.write("\n")
    try:
        os.replace(temporary_path, model_metadata_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return reference


def score_from_model_metadata(predicted_lst_c: float | np.ndarray,
                              model_metadata_path: Path) -> float | np.ndarray:
    """Apply calibrated references in model metadata to predicted LST °C.

    Raises ValueError when calibration is absent or the reference provenance
    is incomplete. Does not alter or train the LST prediction model.
    """
    if not model_metadata_path.is_file():
        raise ValueError("Model metadata with calibrated Heat Hazard Score is required")
    try:
        metadata = json.loads(model_metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read model metadata") from exc
    reference = metadata.get("heat_hazard_score")
    if (not isinstance(reference, dict) or reference.get("status") != "calibrated"
            or reference.get("model_dataset_version") != metadata.get("dataset_version")):
        raise ValueError("Heat Hazard Score references are unavailable; do not display a numeric score")
    return heat_hazard_score(predicted_lst_c, reference.get("background_lst_c"),
                             reference.get("hot_reference_lst_c"))
