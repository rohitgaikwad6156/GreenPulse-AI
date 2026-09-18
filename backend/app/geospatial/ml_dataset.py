"""Assemble a real, aligned 30 m GreenPulse LST training table.

This module never creates climate measurements or trains a model. Every row
comes from QA-masked source rasters and verified ward polygons.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.enums import MergeAlg
from rasterio.features import rasterize
from rasterio.windows import Window
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as transform_geometry

from backend.app.geospatial.features import focal_mean
from backend.app.geospatial.landsat_lst import TARGET_CRS, load_municipal_boundary, target_grid

REQUIRED_RASTERS = {
    "lst_c": "data/processed/lst_pune_30m.tif",
    "ndvi": "data/processed/ndvi_pune_30m.tif",
    "ndbi": "data/processed/ndbi_pune_30m.tif",
    "tree_canopy_pct": "data/interim/morphology/tree_canopy_pct_pune_30m.tif",
    "built_pct": "data/interim/morphology/built_pct_pune_30m.tif",
    "road_density": "data/interim/morphology/road_density_pune_30m.tif",
    "distance_green_m": "data/interim/morphology/distance_green_m_pune_30m.tif",
    "population_density": "data/interim/morphology/population_density_pune_30m.tif",
}
FOCAL_NAMES = ("ndvi_mean_3x3", "ndvi_mean_5x5", "ndbi_mean_3x3", "ndbi_mean_5x5")
MODEL_BASE = ("ndvi", "ndbi", "tree_canopy_pct", "built_pct", "road_density",
              "distance_green_m", "population_density")
LIMITS = {"lst_c": (-273.15, math.inf), "ndvi": (-1, 1), "ndbi": (-1, 1),
          "tree_canopy_pct": (0, 100), "built_pct": (0, 100), "albedo": (0, 1),
          "road_density": (0, math.inf), "distance_green_m": (0, math.inf),
          "population_density": (0, math.inf),
          **{name: (-1, 1) for name in FOCAL_NAMES}}


@dataclass(frozen=True)
class Ward:
    """One official WGS84 ward projected to the LST metric grid."""

    ward_id: str
    ward_name: str
    geometry: Polygon | MultiPolygon


def load_wards(path: Path) -> list[Ward]:
    """Read verified PMC/PCMC ward GeoJSON; reject missing/invalid IDs or CRS.

    Each feature needs municipality, ward_id, ward_name and WGS84 polygon.
    IDs are qualified as `PMC:id` or `PCMC:id` to avoid collisions. Inputs
    without both municipalities or with duplicate qualified IDs are invalid.
    """
    if not path.is_file():
        raise ValueError(f"Verified ward GeoJSON is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read ward GeoJSON: {path}") from exc
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise ValueError("Ward boundary must be a GeoJSON FeatureCollection")
    transformer = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    wards, seen, municipalities = [], set(), set()
    for feature in document["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
            raise ValueError("Ward feature is missing geometry")
        props = feature.get("properties") or {}
        municipality = props.get("municipality")
        raw_id, name = props.get("ward_id"), props.get("ward_name")
        if municipality not in ("PMC", "PCMC") or raw_id is None or not str(raw_id).strip() or not isinstance(name, str) or not name.strip():
            raise ValueError("Every ward needs municipality PMC/PCMC, ward_id, and ward_name")
        ward_id = f"{municipality}:{str(raw_id).strip()}"
        if ward_id in seen:
            raise ValueError(f"Duplicate ward_id: {ward_id}")
        seen.add(ward_id)
        municipalities.add(municipality)
        try:
            geom = shape(feature["geometry"])
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise ValueError(f"Invalid geometry for {ward_id}") from exc
        if not isinstance(geom, (Polygon, MultiPolygon)) or geom.is_empty or not geom.is_valid:
            raise ValueError(f"Invalid polygon for {ward_id}")
        min_x, min_y, max_x, max_y = geom.bounds
        if not all(math.isfinite(v) for v in geom.bounds) or not (-180 <= min_x <= max_x <= 180 and -90 <= min_y <= max_y <= 90):
            raise ValueError(f"Ward coordinates must be WGS84 longitude/latitude: {ward_id}")
        projected = transform_geometry(transformer.transform, geom)
        if projected.is_empty or not projected.is_valid:
            raise ValueError(f"Ward projection failed: {ward_id}")
        wards.append(Ward(ward_id, name.strip(), projected))
    if municipalities != {"PMC", "PCMC"}:
        raise ValueError("Ward boundary must contain both PMC and PCMC wards")
    return wards


def ward_index_grid(wards: list[Ward], transform: Affine, height: int, width: int,
                    inside: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Assign ward only where exactly one polygon contains the cell centre.

    Returns 1-based ward index and overlap-count grids. Zero or multiple
    centre matches remain unassigned rather than inventing a ward label.
    """
    if not wards or inside.shape != (height, width):
        raise ValueError("Wards and municipal grid mask are required")
    shapes = [(mapping(ward.geometry), index) for index, ward in enumerate(wards, 1)]
    ward_index = rasterize(shapes, out_shape=(height, width), transform=transform,
                           fill=0, all_touched=False, dtype="int32")
    count = rasterize([(geom, 1) for geom, _ in shapes], out_shape=(height, width),
                      transform=transform, fill=0, all_touched=False,
                      merge_alg=MergeAlg.add, dtype="uint16")
    ward_index[(count != 1) | ~inside] = 0
    return ward_index, count


def _validate_raster(source: rasterio.io.DatasetReader, reference: rasterio.io.DatasetReader,
                     name: str) -> None:
    """Require exact CRS, transform, shape, float32, and declared nodata."""
    if (source.count != 1 or source.crs != reference.crs or source.transform != reference.transform
            or source.shape != reference.shape or source.res != (30.0, 30.0)
            or source.dtypes[0] != "float32" or source.nodata is None):
        raise ValueError(f"{name} differs from LST CRS, transform, extent, dimensions, 30 m resolution, float32 type, or nodata contract")


def _read_values(source: rasterio.io.DatasetReader, window: Window) -> np.ndarray:
    values = source.read(1, window=window, masked=True).astype(np.float32)
    return np.asarray(values.filled(np.nan), dtype=np.float32)


def _check_ranges(name: str, values: np.ndarray, inside: np.ndarray) -> None:
    """Reject impossible finite in-boundary values; no clipping or invented QA bounds."""
    selected = values[inside]
    if np.isinf(selected).any():
        raise ValueError(f"{name} contains infinity")
    finite = selected[np.isfinite(selected)]
    lower, upper = LIMITS[name]
    if finite.size and (np.any(finite <= lower if name == "lst_c" else finite < lower - 1e-5)
                        or np.any(finite > upper + 1e-5)):
        raise ValueError(f"{name} contains values outside valid range ({lower}, {upper})")


def _schema(feature_names: list[str]) -> pa.Schema:
    fields = [pa.field("grid_id", pa.string()), pa.field("x", pa.float64()), pa.field("y", pa.float64()),
              pa.field("latitude", pa.float64()), pa.field("longitude", pa.float64()),
              pa.field("ward_id", pa.string()), pa.field("ward_name", pa.string()),
              pa.field("lst_c", pa.float32())]
    fields.extend(pa.field(name, pa.float32()) for name in feature_names)
    return pa.schema(fields)


def _correlation_from_sums(names: list[str], n: int, sums: np.ndarray,
                           products: np.ndarray) -> tuple[dict, list[dict], dict]:
    if n == 0:
        raise ValueError("No complete rows for correlations")
    covariance = products - np.outer(sums, sums) / n
    variances = np.diag(covariance)
    correlations = {}
    pairs = []
    for i, first in enumerate(names):
        correlations[first] = {}
        for j, second in enumerate(names):
            divisor = math.sqrt(max(0, variances[i]) * max(0, variances[j]))
            value = float(covariance[i, j] / divisor) if divisor > 1e-10 else None
            correlations[first][second] = value
            if i < j and value is not None and abs(value) >= 0.85:
                pairs.append({"first": first, "second": second, "pearson_r": value})
    # VIF is algebraic from the feature correlation matrix. It is descriptive
    # screening only; do not use it to automatically remove predictors.
    vif = {}
    for i, name in enumerate(names):
        if variances[i] <= 1e-10:
            vif[name] = None
            continue
        others = [j for j in range(len(names)) if j != i and variances[j] > 1e-10]
        if not others:
            vif[name] = 1.0
            continue
        matrix = covariance[np.ix_(others, others)]
        vector = covariance[others, i]
        r2 = float(vector @ np.linalg.pinv(matrix) @ vector / covariance[i, i])
        vif[name] = float(1 / max(1e-12, 1 - r2))
    return correlations, pairs, vif


def _correlation_plot(correlations: dict, names: list[str], path: Path) -> None:
    matrix = np.array([[np.nan if correlations[a][b] is None else correlations[a][b]
                        for b in names] for a in names], dtype=float)
    fig, ax = plt.subplots(figsize=(max(8, len(names) * 0.8), max(7, len(names) * 0.75)), constrained_layout=True)
    image = ax.imshow(matrix, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(names)), labels=names, rotation=65, ha="right")
    ax.set_yticks(range(len(names)), labels=names)
    fig.colorbar(image, ax=ax, label="Pearson correlation")
    ax.set_title("GreenPulse source-feature correlations (complete-case grid)")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def build_ml_dataset(root: Path, ward_path: Path, output_path: Path, metadata_path: Path,
                     albedo_path: Path | None = None, csv_sample_rows: int = 200,
                     chunk_rows: int = 128) -> dict:
    """Join verified real rasters into one Parquet row per complete 30 m cell.

    Missing LST or any required feature/ward excludes the cell. No imputation,
    clipping, model fitting, or synthetic fill occurs. Optional albedo is a
    feature only when a documented aligned raster is explicitly supplied.
    Outputs appear only after all chunks pass validation.
    """
    if csv_sample_rows < 0 or chunk_rows < 1:
        raise ValueError("csv_sample_rows must be nonnegative and chunk_rows positive")
    paths = {name: root / relative for name, relative in REQUIRED_RASTERS.items()}
    if albedo_path is not None:
        paths["albedo"] = albedo_path
    for name, path in paths.items():
        if not path.is_file():
            raise ValueError(f"Required aligned {name} raster is missing: {path}")
    boundary_path = root / "data" / "boundaries" / "pmc_pcmc.geojson"
    boundary = load_municipal_boundary(boundary_path)
    transform, height, width, inside = target_grid(boundary)
    wards = load_wards(ward_path)
    ward_index, ward_count = ward_index_grid(wards, transform, height, width, inside)
    feature_names = list(MODEL_BASE)
    if albedo_path is not None:
        feature_names.append("albedo")
    feature_names.extend(FOCAL_NAMES)
    schema = _schema(feature_names)
    missing = {name: 0 for name in ["lst_c", *feature_names, "ward_id"]}
    rejected = {"outside_municipality": int((~inside).sum()), "missing_lst": 0,
                "missing_required_feature": 0, "unassigned_or_ambiguous_ward": 0}
    feature_sum = np.zeros(len(feature_names), dtype=np.float64)
    feature_products = np.zeros((len(feature_names), len(feature_names)), dtype=np.float64)
    row_count = 0
    csv_rows: list[dict] = []
    sources = {}
    lst_period = None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.Env():
        from contextlib import ExitStack
        with ExitStack() as stack:
            rasters = {name: stack.enter_context(rasterio.open(path)) for name, path in paths.items()}
            reference = rasters["lst_c"]
            if reference.crs is None or reference.crs.to_string() != TARGET_CRS or reference.transform != transform or reference.shape != (height, width):
                raise ValueError("LST raster does not match the verified PMC/PCMC 30 m grid")
            for name, source in rasters.items():
                _validate_raster(source, reference, name)
                sources[name] = {"path": str(paths[name]), "tags": source.tags()}
            lst_period = reference.tags().get("period")
            if not lst_period or not re.fullmatch(r"(\d{4})-03-01/\1-05-31", lst_period):
                raise ValueError("LST raster requires a March-May period tag from Step 9")
            for name in ("ndvi", "ndbi"):
                if rasters[name].tags().get("period") != lst_period:
                    raise ValueError(f"{name} period differs from LST March-May period")
            if albedo_path is not None:
                albedo_tags = rasters["albedo"].tags()
                if albedo_tags.get("period") != lst_period or not albedo_tags.get("source"):
                    raise ValueError("Optional albedo requires documented source and the same March-May period as LST")
            for name, count_name in (("lst_c", "lst_pune_30m_valid_count.tif"),
                                     ("ndvi", "ndvi_pune_30m_valid_count.tif"),
                                     ("ndbi", "ndbi_pune_30m_valid_count.tif")):
                count_path = root / "data" / "processed" / count_name
                if not count_path.is_file():
                    raise ValueError(f"QA valid-count raster is missing: {count_path}")
                count_source = stack.enter_context(rasterio.open(count_path))
                if (count_source.count != 1 or count_source.crs != reference.crs
                        or count_source.transform != reference.transform or count_source.shape != reference.shape
                        or count_source.dtypes[0] != "uint16"):
                    raise ValueError(f"QA count grid differs from LST: {count_path}")
                rasters[name + "_valid_count"] = count_source
                sources[name + "_valid_count"] = {"path": str(count_path), "tags": count_source.tags()}
            qc_path = root / "data" / "interim" / "morphology" / "morphology_qc.json"
            if not qc_path.is_file():
                raise ValueError(f"Morphology provenance report is missing: {qc_path}")
            try:
                morphology_qc = json.loads(qc_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Cannot read morphology QC report: {qc_path}") from exc
            if morphology_qc.get("data_type") != "REAL-SOURCE URBAN MORPHOLOGY FEATURES":
                raise ValueError("Morphology QC report does not identify real-source layers")
            transformer = Transformer.from_crs(TARGET_CRS, "EPSG:4326", always_xy=True)
            with tempfile.TemporaryDirectory(prefix="greenpulse_ml_", dir=output_path.parent) as temporary:
                temporary_path = Path(temporary) / "greenpulse_ml_grid.parquet"
                with pq.ParquetWriter(temporary_path, schema, compression="zstd") as writer:
                    for start in range(0, height, chunk_rows):
                        stop = min(start + chunk_rows, height)
                        rows = stop - start
                        window = Window(0, start, width, rows)
                        local_inside = inside[start:stop]
                        values = {name: _read_values(rasters[name], window) for name in paths}
                        for name in ("lst_c", "ndvi", "ndbi"):
                            count = rasters[name + "_valid_count"].read(1, window=window)
                            values[name][count == 0] = np.nan
                        halo_start, halo_stop = max(0, start - 2), min(height, stop + 2)
                        halo_window = Window(0, halo_start, width, halo_stop - halo_start)
                        focal = {}
                        for name in ("ndvi", "ndbi"):
                            context = _read_values(rasters[name], halo_window)
                            count_context = rasters[name + "_valid_count"].read(1, window=halo_window)
                            context[count_context == 0] = np.nan
                            for size, min_valid in ((3, 5), (5, 13)):
                                key = f"{name}_mean_{size}x{size}"
                                calculated = focal_mean(context, size, min_valid)
                                focal[key] = calculated[start - halo_start:stop - halo_start].astype(np.float32)
                        values.update(focal)
                        for name, array in values.items():
                            _check_ranges(name, array, local_inside)
                            missing[name] += int(np.count_nonzero(local_inside & ~np.isfinite(array)))
                        ward_block = ward_index[start:stop]
                        missing["ward_id"] += int(np.count_nonzero(local_inside & (ward_block == 0)))
                        target_ok = local_inside & np.isfinite(values["lst_c"])
                        features_ok = np.ones((rows, width), dtype=bool)
                        for name in feature_names:
                            features_ok &= np.isfinite(values[name])
                        ward_ok = ward_block != 0
                        rejected["missing_lst"] += int(np.count_nonzero(local_inside & ~target_ok))
                        rejected["missing_required_feature"] += int(np.count_nonzero(target_ok & ~features_ok))
                        rejected["unassigned_or_ambiguous_ward"] += int(np.count_nonzero(target_ok & features_ok & ~ward_ok))
                        keep = target_ok & features_ok & ward_ok
                        row, col = np.nonzero(keep)
                        if not row.size:
                            continue
                        absolute_row = row + start
                        x = transform.c + (col.astype(np.float64) + 0.5) * 30
                        y = transform.f - (absolute_row.astype(np.float64) + 0.5) * 30
                        lon, lat = transformer.transform(x, y)
                        chosen_wards = ward_block[row, col]
                        data = {"grid_id": [f"utm43n_{int(transform.c + int(c) * 30)}_{int(transform.f - int(r) * 30)}"
                                            for r, c in zip(absolute_row, col)],
                                "x": x, "y": y, "latitude": lat, "longitude": lon,
                                "ward_id": [wards[i - 1].ward_id for i in chosen_wards],
                                "ward_name": [wards[i - 1].ward_name for i in chosen_wards],
                                "lst_c": values["lst_c"][row, col]}
                        matrix = np.column_stack([values[name][row, col].astype(np.float64) for name in feature_names])
                        feature_sum += matrix.sum(axis=0)
                        feature_products += matrix.T @ matrix
                        for name in feature_names:
                            data[name] = values[name][row, col]
                        table = pa.Table.from_pydict(data, schema=schema)
                        writer.write_table(table)
                        if len(csv_rows) < csv_sample_rows:
                            take = min(csv_sample_rows - len(csv_rows), row.size)
                            for index in range(take):
                                csv_rows.append({name: data[name][index] for name in schema.names})
                        row_count += int(row.size)
                if row_count == 0:
                    raise ValueError("No complete real-data grid cells remain after QA and missing-data filters")
                correlations, pairs, vif = _correlation_from_sums(feature_names, row_count, feature_sum, feature_products)
                report = {
                    "system": "GreenPulse AI — An AI-powered Urban Climate Decision-Support System",
                    "target": "continuous observed land surface temperature, lst_c, degrees Celsius",
                    "crs": TARGET_CRS, "raster_resolution_m": 30,
                    "date_range": lst_period, "row_count": row_count,
                    "municipal_grid_cells": int(inside.sum()),
                    "source_layers": sources,
                    "municipal_boundary": str(boundary_path),
                    "ward_boundary": str(ward_path),
                    "morphology_source_report": str(qc_path),
                    "morphology_original_sources": morphology_qc.get("source_files", {}),
                    "missing_data_policy": "Complete case: exclude cells with missing/QA-rejected LST, any required feature, or unassigned/ambiguous ward. Never impute or fill with zero. Optional albedo column is omitted unless supplied.",
                    "missing_cells_by_column_before_filter": missing,
                    "rejected_cells_sequential": rejected,
                    "ambiguous_ward_cells": int(np.count_nonzero(inside & (ward_count > 1))),
                    "unassigned_ward_cells": int(np.count_nonzero(inside & (ward_index == 0))),
                    "features": feature_names,
                    "correlation_method": "Pearson on complete-case rows; descriptive only",
                    "feature_correlations": correlations,
                    "severe_pairwise_correlations_abs_r_ge_0_85": pairs,
                    "variance_inflation_factors": vif,
                    "severe_vif_gt_5": [name for name, value in vif.items() if value is not None and value > 5],
                    "notes": ["No ML training or accuracy estimates in this step.",
                              "LST is surface temperature, not pedestrian air temperature.",
                              "WorldCover tree cover and built-up class are proxies; WorldPop is coarser than 30 m.",
                              "Correlations and VIF do not establish causation; correlated features are not removed automatically."]}
                os.replace(temporary_path, output_path)
    metadata_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _correlation_plot(correlations, feature_names, output_path.with_name("greenpulse_ml_correlations.png"))
    if csv_sample_rows and csv_rows:
        sample_path = output_path.with_name("greenpulse_ml_grid_sample.csv")
        with sample_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=schema.names)
            writer.writeheader()
            writer.writerows(csv_rows)
    return report
