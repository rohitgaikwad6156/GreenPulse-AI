"""Build demonstration 30 m ML grid Parquet table and metadata for GreenPulse AI."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "processed"
SEED = 42

WARDS = [
    ("DEMO_WARD_01", "Shivajinagar"),
    ("DEMO_WARD_02", "Kothrud"),
    ("DEMO_WARD_03", "Hadapsar"),
    ("DEMO_WARD_04", "Pimpri"),
    ("DEMO_WARD_05", "Chinchwad"),
    ("DEMO_WARD_06", "Bhosari"),
]

FEATURES = [
    "ndvi",
    "ndbi",
    "tree_canopy_pct",
    "built_pct",
    "albedo",
    "road_density",
    "distance_green_m",
    "population_density",
    "ndvi_mean_3x3",
    "ndvi_mean_5x5",
    "ndbi_mean_3x3",
    "ndbi_mean_5x5",
    "roof_fraction",
]


def generate_demo_ml_grid() -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    # 4 blocks in X, 3 blocks in Y -> 12 spatial 5 km blocks
    n_blocks_x = 4
    n_blocks_y = 3
    block_size_m = 5000.0
    cells_per_dim = 16  # 16 x 16 = 256 cells per block
    cell_size_m = 30.0

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    to_wgs84 = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    center_x, center_y = to_utm.transform(73.85, 18.55)
    origin_x = float(int(np.floor(center_x / block_size_m) * block_size_m - 10000.0))
    origin_y = float(int(np.floor(center_y / block_size_m) * block_size_m - 5000.0))

    grid_ids = []
    ward_ids = []
    ward_names = []
    xs = []
    ys = []
    lons = []
    lats = []
    lst_cs = []

    feature_arrays = {name: [] for name in FEATURES}

    cell_counter = 1
    for by in range(n_blocks_y):
        for bx in range(n_blocks_x):
            ward_idx = (bx % 2) + by * 2
            w_id, w_name = WARDS[ward_idx]
            block_base_x = origin_x + bx * block_size_m + 500.0
            block_base_y = origin_y + by * block_size_m + 500.0

            # Generate cells within this block
            row_idx, col_idx = np.indices((cells_per_dim, cells_per_dim))
            row_flat = row_idx.ravel()
            col_flat = col_idx.ravel()

            cell_x = block_base_x + col_flat * cell_size_m + 15.0
            cell_y = block_base_y + row_flat * cell_size_m + 15.0
            lon, lat = to_wgs84.transform(cell_x, cell_y)

            # Block urbanity factor
            urbanity = np.clip(0.3 + 0.15 * bx + 0.1 * by + rng.normal(0, 0.08, len(cell_x)), 0.1, 0.9)
            ndvi_raw = np.clip(0.65 - 0.55 * urbanity + rng.normal(0, 0.06, len(cell_x)), -0.05, 0.80)
            ndbi_raw = np.clip(-0.25 + 0.60 * urbanity + rng.normal(0, 0.06, len(cell_x)), -0.30, 0.55)
            canopy = np.clip(10.0 + 65.0 * ndvi_raw + rng.normal(0, 5.0, len(cell_x)), 0.0, 75.0)
            built = np.clip(10.0 + 80.0 * urbanity + rng.normal(0, 5.0, len(cell_x)), 5.0, 95.0)
            albedo = np.clip(0.18 + 0.04 * ndvi_raw + rng.normal(0, 0.03, len(cell_x)), 0.10, 0.38)
            road_dens = np.clip(1.0 + 8.0 * urbanity + rng.normal(0, 1.0, len(cell_x)), 0.0, 15.0)
            dist_green = np.clip(20.0 + 500.0 * urbanity + rng.normal(0, 60.0, len(cell_x)), 0.0, 850.0)
            pop_dens = np.clip(1000.0 + 20000.0 * urbanity + rng.normal(0, 1500.0, len(cell_x)), 500.0, 28000.0)
            roof_frac = np.clip((built / 100.0) * rng.uniform(0.4, 0.8, len(cell_x)), 0.05, 0.60)

            # 2D local smoothing for focal context
            ndvi_grid = ndvi_raw.reshape((cells_per_dim, cells_per_dim))
            ndbi_grid = ndbi_raw.reshape((cells_per_dim, cells_per_dim))

            def focal(grid_2d: np.ndarray, k: int) -> np.ndarray:
                pad = k // 2
                padded = np.pad(grid_2d, pad, mode="edge")
                res = np.zeros_like(grid_2d)
                for r in range(grid_2d.shape[0]):
                    for c in range(grid_2d.shape[1]):
                        res[r, c] = np.mean(padded[r : r + k, c : c + k])
                return res.ravel()

            ndvi_3x3 = np.clip(focal(ndvi_grid, 3), -1.0, 1.0)
            ndvi_5x5 = np.clip(focal(ndvi_grid, 5), -1.0, 1.0)
            ndbi_3x3 = np.clip(focal(ndbi_grid, 3), -1.0, 1.0)
            ndbi_5x5 = np.clip(focal(ndbi_grid, 5), -1.0, 1.0)

            # Realistic LST model with smooth spatial signal + noise
            block_effect = 0.5 * (bx - 1.5) - 0.4 * (by - 1.0)
            lst_c = (
                33.5
                + 4.8 * ndbi_raw
                + 3.2 * (built / 100.0)
                - 4.2 * ndvi_raw
                - 2.2 * (canopy / 100.0)
                - 11.0 * (albedo - 0.20)
                + 0.18 * road_dens
                + 0.35 * (dist_green / 1000.0)
                + block_effect
                + rng.normal(0, 0.65, len(cell_x))
            )

            for i in range(len(cell_x)):
                grid_ids.append(f"DEMO_G_{cell_counter:04d}")
                ward_ids.append(w_id)
                ward_names.append(w_name)
                xs.append(float(cell_x[i]))
                ys.append(float(cell_y[i]))
                lons.append(float(np.round(lon[i], 7)))
                lats.append(float(np.round(lat[i], 7)))
                lst_cs.append(float(np.round(lst_c[i], 3)))
                cell_counter += 1

            feature_arrays["ndvi"].extend(np.round(ndvi_raw, 4))
            feature_arrays["ndbi"].extend(np.round(ndbi_raw, 4))
            feature_arrays["tree_canopy_pct"].extend(np.round(canopy, 2))
            feature_arrays["built_pct"].extend(np.round(built, 2))
            feature_arrays["albedo"].extend(np.round(albedo, 4))
            feature_arrays["road_density"].extend(np.round(road_dens, 3))
            feature_arrays["distance_green_m"].extend(np.round(dist_green, 2))
            feature_arrays["population_density"].extend(np.round(pop_dens, 2))
            feature_arrays["ndvi_mean_3x3"].extend(np.round(ndvi_3x3, 4))
            feature_arrays["ndvi_mean_5x5"].extend(np.round(ndvi_5x5, 4))
            feature_arrays["ndbi_mean_3x3"].extend(np.round(ndbi_3x3, 4))
            feature_arrays["ndbi_mean_5x5"].extend(np.round(ndbi_5x5, 4))
            feature_arrays["roof_fraction"].extend(np.round(roof_frac, 4))

    row_count = len(grid_ids)
    parquet_path = OUTPUT_DIR / "greenpulse_ml_grid.parquet"
    metadata_path = OUTPUT_DIR / "metadata.json"

    data_dict = {
        "grid_id": grid_ids,
        "ward_id": ward_ids,
        "ward_name": ward_names,
        "x": xs,
        "y": ys,
        "longitude": lons,
        "latitude": lats,
        "lst_c": lst_cs,
    }
    for name in FEATURES:
        data_dict[name] = feature_arrays[name]

    table = pa.Table.from_pydict(data_dict)
    pq.write_table(table, parquet_path)

    metadata = {
        "crs": "EPSG:32643",
        "raster_resolution_m": 30,
        "row_count": row_count,
        "date_range": "2025-03-01/2025-05-31",
        "features": FEATURES,
        "source": "DEMO / SYNTHETIC DATA",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {row_count} cells across {n_blocks_x * n_blocks_y} spatial blocks.")
    print(f"Parquet: {parquet_path}")
    print(f"Metadata: {metadata_path}")
    return parquet_path, metadata_path


if __name__ == "__main__":
    generate_demo_ml_grid()
