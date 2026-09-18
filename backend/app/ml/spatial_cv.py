"""Deterministic 5 km spatial-block cross-validation infrastructure.

No estimator is fitted here. Coordinates must be projected metres in
EPSG:32643, as in GreenPulse's 30 m ML Parquet table.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from matplotlib.patches import Patch, Rectangle

BLOCK_SIZE_M = 5000.0
N_FOLDS = 5
EXPECTED_CRS = "EPSG:32643"


@dataclass(frozen=True)
class BlockAssignment:
    """Per-row spatial blocks and held-out fold IDs, with frozen origin."""

    block_x: np.ndarray
    block_y: np.ndarray
    block_id: np.ndarray
    validation_fold: np.ndarray
    x_min: float
    y_min: float
    block_size_m: float
    n_folds: int


def assign_spatial_blocks(x: object, y: object, block_size_m: float = BLOCK_SIZE_M,
                          x_min: float | None = None, y_min: float | None = None
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Apply floor((x−x_min)/size), floor((y−y_min)/size) in projected metres.

    Returns integer block_x, block_y, string block_id, and the frozen metre
    origin. Coordinates must be finite, 1D, equal-length, and nonempty. The
    optional origin allows later observations to reuse the original lattice.
    """
    try:
        x_values = np.asarray(x, dtype=np.float64)
        y_values = np.asarray(y, dtype=np.float64)
        size = float(block_size_m)
    except (TypeError, ValueError) as exc:
        raise ValueError("x, y, and block_size_m must be numeric") from exc
    if x_values.ndim != 1 or y_values.ndim != 1 or x_values.shape != y_values.shape or not x_values.size:
        raise ValueError("x and y must be nonempty equal-length 1D arrays")
    if not np.isfinite(x_values).all() or not np.isfinite(y_values).all():
        raise ValueError("x and y must contain only finite projected coordinates")
    if not math.isfinite(size) or size <= 0:
        raise ValueError("block_size_m must be finite and positive")
    try:
        origin_x = float(np.min(x_values) if x_min is None else x_min)
        origin_y = float(np.min(y_values) if y_min is None else y_min)
    except (TypeError, ValueError) as exc:
        raise ValueError("block origins must be numeric") from exc
    if not math.isfinite(origin_x) or not math.isfinite(origin_y):
        raise ValueError("block origins must be finite")
    block_x = np.floor((x_values - origin_x) / size).astype(np.int64)
    block_y = np.floor((y_values - origin_y) / size).astype(np.int64)
    block_id = np.char.add(np.char.add(block_x.astype(str), ":"), block_y.astype(str))
    return block_x, block_y, block_id, origin_x, origin_y


def make_spatial_folds(x: object, y: object, n_folds: int = N_FOLDS,
                       block_size_m: float = BLOCK_SIZE_M,
                       x_min: float | None = None, y_min: float | None = None) -> BlockAssignment:
    """Assign whole spatial blocks to approximately balanced validation folds.

    An equivalent to non-shuffled GroupKFold: sort unique groups by descending
    row count (ties by block coordinates), then place each group into the
    currently lightest fold. Every block validates exactly once. Requires at
    least `n_folds` distinct blocks; no random pixel splitting is used.
    """
    if isinstance(n_folds, bool) or not isinstance(n_folds, int) or n_folds < 2:
        raise ValueError("n_folds must be an integer at least 2")
    bx, by, ids, origin_x, origin_y = assign_spatial_blocks(x, y, block_size_m, x_min, y_min)
    unique, inverse, counts = np.unique(ids, return_inverse=True, return_counts=True)
    if unique.size < n_folds:
        raise ValueError(f"Need at least {n_folds} distinct spatial blocks; found {unique.size}")
    # Sort by descending populated-cell count, then numeric block coordinates.
    unique_coords = np.array([tuple(map(int, item.split(":"))) for item in unique], dtype=np.int64)
    order = sorted(range(unique.size), key=lambda i: (-int(counts[i]), int(unique_coords[i, 0]), int(unique_coords[i, 1])))
    fold_load = np.zeros(n_folds, dtype=np.int64)
    group_fold = np.full(unique.size, -1, dtype=np.int16)
    for group in order:
        fold = int(np.argmin(fold_load))
        group_fold[group] = fold
        fold_load[fold] += counts[group]
    validation_fold = group_fold[inverse] + 1  # user-facing folds are 1..K
    if np.any(validation_fold < 1) or np.any(validation_fold > n_folds):
        raise AssertionError("A spatial block was not assigned exactly once")
    return BlockAssignment(bx, by, ids, validation_fold, origin_x, origin_y, float(block_size_m), n_folds)


class SpatialBlockCV:
    """Scikit-learn-style splitter over precomputed whole-block assignments."""

    def __init__(self, assignment: BlockAssignment):
        if not isinstance(assignment, BlockAssignment):
            raise ValueError("assignment must come from make_spatial_folds")
        self.assignment = assignment

    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        """Return the number of folds; data arguments are ignored."""
        return self.assignment.n_folds

    def split(self, X=None, y=None, groups=None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield train/validation row indices with no shared spatial block.

        X and y are optional because assignments already fix row order. If X
        or groups is supplied, its length must match the assignment. Groups,
        when supplied, must equal the computed block IDs. Each row is used
        for validation once and for training in the other K−1 folds.
        """
        count = self.assignment.validation_fold.size
        if X is not None and len(X) != count:
            raise ValueError("X length differs from spatial assignment")
        if groups is not None:
            supplied = np.asarray(groups)
            if supplied.shape != (count,) or not np.array_equal(supplied.astype(str), self.assignment.block_id):
                raise ValueError("groups must match the spatial block IDs and row order")
        for fold in range(1, self.assignment.n_folds + 1):
            validation = np.flatnonzero(self.assignment.validation_fold == fold)
            training = np.flatnonzero(self.assignment.validation_fold != fold)
            if not validation.size or not training.size:
                raise ValueError(f"Fold {fold} lacks training or validation rows")
            train_blocks = set(self.assignment.block_id[training])
            validation_blocks = set(self.assignment.block_id[validation])
            if train_blocks & validation_blocks:
                raise AssertionError(f"Spatial block leakage in fold {fold}")
            yield training, validation


def summarize_blocks(assignment: BlockAssignment) -> tuple[list[dict], list[dict]]:
    """Return unique-block map records and per-fold held-out row/block counts."""
    ids, first, counts = np.unique(assignment.block_id, return_index=True, return_counts=True)
    blocks = [{"block_id": str(block_id), "block_x": int(assignment.block_x[index]),
               "block_y": int(assignment.block_y[index]),
               "validation_fold": int(assignment.validation_fold[index]),
               "row_count": int(count)}
              for block_id, index, count in zip(ids, first, counts)]
    folds = [{"fold": fold, "validation_rows": int(np.count_nonzero(assignment.validation_fold == fold)),
              "validation_blocks": int(sum(block["validation_fold"] == fold for block in blocks))}
             for fold in range(1, assignment.n_folds + 1)]
    return blocks, folds


def plot_block_folds(blocks: list[dict], assignment: BlockAssignment, path: Path) -> None:
    """Save a 5 km block map coloured by held-out validation fold."""
    if not blocks:
        raise ValueError("No blocks to plot")
    palette = plt.get_cmap("tab10")
    fig, ax = plt.subplots(figsize=(9, 8), constrained_layout=True)
    for block in blocks:
        west = assignment.x_min + block["block_x"] * assignment.block_size_m
        south = assignment.y_min + block["block_y"] * assignment.block_size_m
        rectangle = Rectangle((west / 1000, south / 1000), assignment.block_size_m / 1000,
                              assignment.block_size_m / 1000,
                              facecolor=palette((block["validation_fold"] - 1) % 10),
                              edgecolor="white", linewidth=0.8)
        ax.add_patch(rectangle)
    ax.autoscale_view()
    ax.set_aspect("equal", adjustable="box")
    ax.set(xlabel="UTM easting (km, EPSG:32643)", ylabel="UTM northing (km, EPSG:32643)",
           title=f"GreenPulse spatial CV — {assignment.block_size_m / 1000:g} km blocks, {assignment.n_folds} folds")
    ax.legend(handles=[Patch(facecolor=palette((fold - 1) % 10), label=f"Validation fold {fold}")
                       for fold in range(1, assignment.n_folds + 1)], loc="best")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def build_cv_artifacts(dataset_path: Path, output_dir: Path,
                       block_size_m: float = BLOCK_SIZE_M,
                       n_folds: int = N_FOLDS) -> dict:
    """Read real ML table coordinates and save block map, mapping, and QA JSON.

    Only x/y are read from Parquet; no target or features are accessed and no
    model is fitted. Outputs are written after validation confirms exclusivity.
    """
    if not dataset_path.is_file():
        raise ValueError(f"Real ML Parquet dataset is missing: {dataset_path}")
    metadata_path = dataset_path.with_name("metadata.json")
    if not metadata_path.is_file():
        raise ValueError(f"ML metadata is missing: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read ML metadata: {metadata_path}") from exc
    if metadata.get("crs") != EXPECTED_CRS or metadata.get("raster_resolution_m") != 30:
        raise ValueError("ML table metadata must declare EPSG:32643 and 30 m grid")
    try:
        table = pq.read_table(dataset_path, columns=["x", "y"])
    except (OSError, KeyError, pa.ArrowException) as exc:
        raise ValueError(f"Cannot read x/y columns from Parquet: {dataset_path}") from exc
    if metadata.get("row_count") != table.num_rows:
        raise ValueError("ML metadata row count differs from Parquet row count")
    assignment = make_spatial_folds(table.column("x").to_numpy(), table.column("y").to_numpy(),
                                    n_folds, block_size_m)
    # Force all train/validation disjointness assertions before writing.
    for _ in SpatialBlockCV(assignment).split():
        pass
    blocks, folds = summarize_blocks(assignment)
    report = {"source_dataset": str(dataset_path), "source_metadata": str(metadata_path),
              "crs": EXPECTED_CRS, "block_size_m": assignment.block_size_m,
              "x_min": assignment.x_min, "y_min": assignment.y_min,
              "formula": "block_x=floor((x-x_min)/block_size_m); block_y=floor((y-y_min)/block_size_m)",
              "block_id_format": "block_x:block_y", "n_folds": assignment.n_folds,
              "row_count": int(table.num_rows), "unique_blocks": len(blocks),
              "fold_summary": folds, "block_overlap_between_train_and_validation": False,
              "method": "deterministic GroupKFold-equivalent, greedy balance by populated row count",
              "caution": "Adjacent blocks can remain spatially correlated; assess a held-out buffer or larger blocks before claiming strict geographic transfer."}
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="greenpulse_cv_", dir=output_dir) as temporary:
        folder = Path(temporary)
        block_path = folder / "spatial_cv_blocks.parquet"
        map_path = folder / "spatial_cv_folds.png"
        report_path = folder / "spatial_cv_metadata.json"
        pq.write_table(pa.table({key: [block[key] for block in blocks]
                                 for key in ("block_id", "block_x", "block_y", "validation_fold", "row_count")}),
                       block_path, compression="zstd")
        plot_block_folds(blocks, assignment, map_path)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for temporary_path in (block_path, map_path, report_path):
            os.replace(temporary_path, output_dir / temporary_path.name)
    return report


def load_cv_assignment(x: object, y: object, dataset_path: Path,
                       cv_dir: Path) -> BlockAssignment:
    """Reattach the *saved* block-to-fold mapping to rows in the ML table.

    Requires matching source path, row count, CRS, frozen origin, block size,
    per-block row counts, and all five fold IDs. Never silently regenerates a
    different CV split for model evaluation.
    """
    report_path = cv_dir / "spatial_cv_metadata.json"
    mapping_path = cv_dir / "spatial_cv_blocks.parquet"
    if not report_path.is_file() or not mapping_path.is_file():
        raise ValueError(f"Saved spatial CV metadata/block mapping is missing in {cv_dir}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        blocks = pq.read_table(mapping_path).to_pydict()
    except (OSError, json.JSONDecodeError, pa.ArrowException) as exc:
        raise ValueError("Cannot read saved spatial CV artifacts") from exc
    if (Path(report.get("source_dataset", "")).resolve() != dataset_path.resolve()
            or report.get("crs") != EXPECTED_CRS
            or report.get("n_folds") != N_FOLDS
            or report.get("block_size_m") != BLOCK_SIZE_M
            or report.get("row_count") != len(x)):
        raise ValueError("Saved CV metadata disagrees with this dataset, CRS, block size, fold count, or row count")
    bx, by, ids, origin_x, origin_y = assign_spatial_blocks(
        x, y, report["block_size_m"], report.get("x_min"), report.get("y_min"))
    if origin_x != report["x_min"] or origin_y != report["y_min"]:
        raise ValueError("Saved CV origin is inconsistent")
    required = ("block_id", "block_x", "block_y", "validation_fold", "row_count")
    if not all(key in blocks for key in required):
        raise ValueError("Saved CV block table is missing required fields")
    lookup = {}
    for values in zip(*(blocks[key] for key in required)):
        block_id, block_x, block_y, fold, count = values
        if block_id in lookup or block_id != f"{block_x}:{block_y}" or fold not in range(1, N_FOLDS + 1) or count < 1:
            raise ValueError("Saved CV block mapping contains duplicate or invalid entries")
        lookup[block_id] = (int(fold), int(count))
    unique, counts = np.unique(ids, return_counts=True)
    if set(unique) != set(lookup):
        raise ValueError("Saved CV blocks do not match dataset coordinates")
    for block_id, count in zip(unique, counts):
        if int(count) != lookup[block_id][1]:
            raise ValueError(f"Saved CV row count differs for block {block_id}")
    if len(lookup) != report.get("unique_blocks"):
        raise ValueError("Saved CV unique-block count differs from metadata")
    fold_summary = report.get("fold_summary")
    if not isinstance(fold_summary, list) or len(fold_summary) != N_FOLDS:
        raise ValueError("Saved CV fold summary is missing or incomplete")
    for fold in range(1, N_FOLDS + 1):
        expected = fold_summary[fold - 1]
        rows = sum(count for assigned, count in lookup.values() if assigned == fold)
        block_count = sum(assigned == fold for assigned, _ in lookup.values())
        if (expected.get("fold") != fold or expected.get("validation_rows") != rows
                or expected.get("validation_blocks") != block_count):
            raise ValueError(f"Saved CV fold {fold} mapping differs from metadata")
    folds = np.array([lookup[block_id][0] for block_id in ids], dtype=np.int16)
    assignment = BlockAssignment(bx, by, ids, folds, origin_x, origin_y, BLOCK_SIZE_M, N_FOLDS)
    for _ in SpatialBlockCV(assignment).split():
        pass
    return assignment
