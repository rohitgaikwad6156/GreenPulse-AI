"""Generate clearly labelled synthetic GreenPulse grid data and QA charts.

This is a DEMO / SYNTHETIC DATA generator, not an LST prediction model.
No satellite image, station observation, or official ward boundary is used.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer


SEED = 20260917
GRID_SIZE = 60
CELL_SIZE_M = 30
LABEL = "DEMO / SYNTHETIC DATA"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "demo"
FIGURE_DIR = OUTPUT_DIR / "figures"


def create_grid() -> pd.DataFrame:
    """Create 3,600 square-cell centroids near Pune for UI testing only."""
    rng = np.random.default_rng(SEED)
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    to_wgs84 = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)

    # The centre is only a map-testing anchor; it is not a measured sample.
    centre_x, centre_y = to_utm.transform(73.85, 18.55)
    first_x = int(np.floor(centre_x / CELL_SIZE_M) * CELL_SIZE_M + 15 - 30 * CELL_SIZE_M)
    first_y = int(np.floor(centre_y / CELL_SIZE_M) * CELL_SIZE_M + 15 - 30 * CELL_SIZE_M)

    row, col = np.indices((GRID_SIZE, GRID_SIZE))
    row = row.ravel()
    col = col.ravel()
    x = first_x + col * CELL_SIZE_M
    y = first_y + row * CELL_SIZE_M
    longitude, latitude = to_wgs84.transform(x, y)

    # Smooth urban gradient plus local variation creates related but distinct features.
    spatial_pattern = (
        0.16 * np.sin(col / 8.0)
        + 0.12 * np.cos(row / 10.0)
        + 0.12 * (col / (GRID_SIZE - 1))
        - 0.08 * (row / (GRID_SIZE - 1))
    )
    urbanity = np.clip(0.52 + spatial_pattern + rng.normal(0, 0.11, len(row)), 0.05, 0.95)

    ndvi = np.clip(0.58 - 0.56 * urbanity + rng.normal(0, 0.085, len(row)), -0.10, 0.85)
    ndbi = np.clip(-0.20 + 0.65 * urbanity + rng.normal(0, 0.085, len(row)), -0.35, 0.60)
    tree_canopy_pct = np.clip(9 + 64 * ndvi + rng.normal(0, 8.5, len(row)), 0, 85)
    built_pct = np.clip(9 + 79 * urbanity + rng.normal(0, 8.5, len(row)), 0, 100)
    albedo = np.clip(0.19 + 0.035 * ndvi + rng.normal(0, 0.038, len(row)), 0.08, 0.38)
    road_density = np.clip(1.2 + 7.2 * urbanity + rng.normal(0, 1.1, len(row)), 0, 12)
    distance_green_m = np.clip(30 + 530 * urbanity + rng.normal(0, 95, len(row)), 0, 900)
    elevation_m = 555 + 20 * (row / (GRID_SIZE - 1)) + rng.normal(0, 4.0, len(row))
    population_density = np.clip(900 + 18000 * urbanity + rng.normal(0, 2300, len(row)), 0, 30000)

    # Artificial label equation. Its coefficients are illustrative assumptions only.
    # Independent noise and a mild spatial term prevent a perfect relationship.
    spatial_lstdelta = 0.45 * np.sin(col / 7.0) * np.cos(row / 9.0)
    lst_c = (
        32.0
        + 5.2 * ndbi
        + 3.8 * (built_pct / 100)
        - 4.8 * ndvi
        - 2.5 * (tree_canopy_pct / 100)
        - 13.0 * (albedo - 0.20)
        + 0.20 * road_density
        + 0.50 * (distance_green_m / 1000)
        - 0.45 * ((elevation_m - 560) / 100)
        + spatial_lstdelta
        + rng.normal(0, 1.45, len(row))
    )

    ward_number = (row // 30) * 3 + (col // 20) + 1
    data = pd.DataFrame(
        {
            "grid_id": [f"DEMO_G_{i:04d}" for i in range(1, len(row) + 1)],
            "latitude": np.round(latitude, 7),
            "longitude": np.round(longitude, 7),
            "x": x,
            "y": y,
            "ward_id": [f"DEMO_WARD_{n:02d}" for n in ward_number],
            "ward_name": [f"DEMO Ward {n:02d}" for n in ward_number],
            "lst_c": np.round(lst_c, 3),
            "ndvi": np.round(ndvi, 4),
            "ndbi": np.round(ndbi, 4),
            "tree_canopy_pct": np.round(tree_canopy_pct, 2),
            "built_pct": np.round(built_pct, 2),
            "albedo": np.round(albedo, 4),
            "road_density": np.round(road_density, 3),
            "distance_green_m": np.round(distance_green_m, 2),
            "elevation_m": np.round(elevation_m, 2),
            "population_density": np.round(population_density, 2),
            "data_label": LABEL,
        }
    )
    return data


def validate(data: pd.DataFrame) -> pd.Series:
    """Check structure, units, grid spacing, and intended synthetic directions."""
    assert len(data) == GRID_SIZE**2
    assert data.grid_id.is_unique
    assert not data.isna().any().any()
    assert data.data_label.eq(LABEL).all()
    assert data.ward_id.nunique() == 6
    assert data.groupby("ward_id").size().eq(600).all()
    assert len(np.unique(data.x)) == GRID_SIZE
    assert len(np.unique(data.y)) == GRID_SIZE
    assert np.diff(np.sort(data.x.unique())).min() == CELL_SIZE_M
    assert np.diff(np.sort(data.x.unique())).max() == CELL_SIZE_M
    assert np.diff(np.sort(data.y.unique())).min() == CELL_SIZE_M
    assert np.diff(np.sort(data.y.unique())).max() == CELL_SIZE_M
    assert data[["x", "y"]].drop_duplicates().shape[0] == len(data)
    assert data.latitude.between(-90, 90).all()
    assert data.longitude.between(-180, 180).all()
    assert data.lst_c.between(20, 50).all()
    assert data.ndvi.between(-1, 1).all()
    assert data.ndbi.between(-1, 1).all()
    assert data.tree_canopy_pct.between(0, 100).all()
    assert data.built_pct.between(0, 100).all()
    assert data.albedo.between(0, 1).all()
    assert data.road_density.ge(0).all()
    assert data.distance_green_m.ge(0).all()
    assert data.population_density.ge(0).all()

    features = ["ndvi", "tree_canopy_pct", "ndbi", "built_pct", "albedo"]
    correlations = data[features + ["lst_c"]].corr()["lst_c"].drop("lst_c")
    assert (correlations[["ndvi", "tree_canopy_pct", "albedo"]] < 0).all()
    assert (correlations[["ndbi", "built_pct"]] > 0).all()
    assert (correlations.abs() < 0.95).all()
    return correlations


def create_charts(data: pd.DataFrame) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        ("lst_c", "LST (°C)"),
        ("ndvi", "NDVI (unitless)"),
        ("ndbi", "NDBI (unitless)"),
        ("tree_canopy_pct", "Tree canopy (%)"),
        ("built_pct", "Built area (%)"),
        ("albedo", "Albedo (fraction)"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.5), constrained_layout=True)
    fig.suptitle("DEMO / SYNTHETIC DATA — feature distributions", fontsize=15, fontweight="bold")
    for axis, (column, label) in zip(axes.flat, fields):
        axis.hist(data[column], bins=28, color="#327a60", edgecolor="white", linewidth=0.4)
        axis.set_xlabel(label)
        axis.set_ylabel("Grid cells")
        axis.grid(axis="y", alpha=0.18)
    fig.savefig(FIGURE_DIR / "demo_distributions.png", dpi=160)
    plt.close(fig)

    corr_fields = ["lst_c", "ndvi", "ndbi", "tree_canopy_pct", "built_pct", "albedo"]
    matrix = data[corr_fields].corr()
    fig, axis = plt.subplots(figsize=(8, 7), constrained_layout=True)
    image = axis.imshow(matrix, vmin=-1, vmax=1, cmap="RdYlGn_r")
    axis.set_xticks(range(len(corr_fields)), corr_fields, rotation=35, ha="right")
    axis.set_yticks(range(len(corr_fields)), corr_fields)
    for i in range(len(corr_fields)):
        for j in range(len(corr_fields)):
            axis.text(j, i, f"{matrix.iloc[i, j]:.2f}", ha="center", va="center", fontsize=9)
    axis.set_title("DEMO / SYNTHETIC DATA — Pearson correlations", fontsize=14, fontweight="bold")
    fig.colorbar(image, ax=axis, label="Correlation r")
    fig.savefig(FIGURE_DIR / "demo_correlations.png", dpi=160)
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = create_grid()
    correlations = validate(data)
    output_file = OUTPUT_DIR / "greenpulse_demo_grid.csv"
    data.to_csv(output_file, index=False)
    create_charts(data)
    print(f"{LABEL}: created {len(data):,} cells in {data.ward_id.nunique()} fictional wards")
    print("Grid: 60 x 60 cells; 30 m centroid spacing; EPSG:32643 x/y")
    print(f"CSV: {output_file}")
    print(f"LST range (synthetic only): {data.lst_c.min():.3f} to {data.lst_c.max():.3f} deg C")
    print("Synthetic Pearson r with LST (diagnostic, not model performance):")
    for name, value in correlations.items():
        print(f"  {name}: {value:+.3f}")
    print(f"Charts: {FIGURE_DIR / 'demo_distributions.png'}")
    print(f"        {FIGURE_DIR / 'demo_correlations.png'}")
    print("Validation: PASS - structure, spacing, ranges, labels, and correlation directions")


if __name__ == "__main__":
    main()
