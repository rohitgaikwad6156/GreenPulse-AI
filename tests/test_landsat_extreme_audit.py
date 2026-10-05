"""Synthetic-only checks for the read-only Landsat extreme investigation."""

import hashlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from scripts.audit_landsat_extremes import (
    HOT_SCENE,
    cluster_summary,
    extract_neighborhood,
    percentile_from_histogram,
    pixel_coordinates,
    run_audit,
    threshold_counts,
    write_reports,
)


def make_scene(root: Path) -> Path:
    directory = root / HOT_SCENE
    directory.mkdir()
    (directory / f"{HOT_SCENE}_MTL.txt").write_text(
        f'LANDSAT_PRODUCT_ID = "{HOT_SCENE}"\n'
        "DATE_ACQUIRED = 2025-03-10\n"
        "TEMPERATURE_MULT_BAND_ST_B10 = 1\n"
        "TEMPERATURE_ADD_BAND_ST_B10 = 273.15\n",
        encoding="utf-8",
    )
    dn = np.full((5, 5), 40, dtype=np.uint16)
    dn[2, 2], dn[2, 3], dn[0, 0], dn[1, 2] = 100, 85, 95, 120
    qa = np.zeros_like(dn)
    qa[1, 2] = 1 << 3  # The hotter cloud pixel must never become an extreme.
    radsat = np.zeros_like(dn)
    profile = {"driver": "GTiff", "height": 5, "width": 5, "count": 1,
               "dtype": "uint16", "crs": "EPSG:32643",
               "transform": from_origin(375000, 2050110, 30, 30)}
    for suffix, values in (("ST_B10", dn), ("QA_PIXEL", qa), ("QA_RADSAT", radsat)):
        with rasterio.open(directory / f"{HOT_SCENE}_{suffix}.TIF", "w", **profile) as dataset:
            dataset.write(values, 1)
    return directory


def test_coordinate_conversion_uses_pixel_centre() -> None:
    transform = from_origin(375000, 2050110, 30, 30)
    point = pixel_coordinates(transform, "EPSG:32643", 2, 3)
    assert point["x"] == 375105
    assert point["y"] == 2050035
    lon, lat = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform(375105, 2050035)
    assert point["longitude"] == pytest.approx(lon)
    assert point["latitude"] == pytest.approx(lat)


def test_histogram_percentiles_match_numpy_linear() -> None:
    codes = np.array([1, 1, 5, 10, 20, 100], dtype=np.uint16)
    histogram = np.bincount(codes, minlength=65536)
    for percentile in (1, 5, 25, 50, 75, 95, 99):
        expected = float(np.percentile(codes.astype(float) * 0.5 + 20 - 273.15, percentile))
        assert percentile_from_histogram(histogram, percentile, 0.5, 20) == pytest.approx(expected)


def test_threshold_counts_do_not_filter() -> None:
    codes = np.array([0, 5, 10, 15, 20, 70, 71, 81, 91, 101], dtype=np.uint16)
    counts = threshold_counts(np.bincount(codes, minlength=65536), 1, 263.15)
    assert counts == {"below_0": 2, "from_0_to_10": 2, "above_60": 4,
                      "above_70": 3, "above_80": 2, "above_90": 1}
    assert sum(np.bincount(codes, minlength=65536)) == len(codes)


def test_isolated_extreme_detection() -> None:
    mask = np.zeros((5, 5), dtype=bool)
    mask[2, 2] = True
    result = cluster_summary(mask, from_origin(100, 200, 30, 30), "EPSG:32643")
    assert (result["pixel_count"], result["cluster_count"], result["largest_cluster_size"]) == (1, 1, 1)
    assert result["largest_cluster_bounds"]["min_row"] == 2
    assert result["largest_cluster_bounds"]["max_column"] == 2


def test_diagonal_pixels_form_8_neighbour_cluster() -> None:
    mask = np.zeros((5, 5), dtype=bool)
    mask[0, 0] = mask[1, 1] = mask[2, 2] = mask[4, 4] = True
    result = cluster_summary(mask, from_origin(100, 200, 30, 30), "EPSG:32643")
    assert (result["pixel_count"], result["cluster_count"], result["largest_cluster_size"]) == (4, 2, 3)
    assert result["largest_cluster_bounds"]["min_row"] == 0
    assert result["largest_cluster_bounds"]["max_row"] == 2


def test_5x5_neighbourhood_and_qa_validity(tmp_path: Path) -> None:
    scene = make_scene(tmp_path)
    with rasterio.open(scene / f"{HOT_SCENE}_ST_B10.TIF") as st, rasterio.open(
        scene / f"{HOT_SCENE}_QA_PIXEL.TIF"
    ) as pixel, rasterio.open(scene / f"{HOT_SCENE}_QA_RADSAT.TIF") as radsat:
        neighborhood = extract_neighborhood({"ST_B10": st, "QA_PIXEL": pixel, "QA_RADSAT": radsat}, 2, 2, 1, 273.15)
    assert len(neighborhood) == 5 and all(len(row) == 5 for row in neighborhood)
    assert neighborhood[2][2]["celsius"] == 100
    assert neighborhood[2][2]["qa_valid"] is True
    assert neighborhood[1][2]["qa_valid"] is False
    assert neighborhood[1][2]["celsius"] is None
    assert neighborhood[1][2]["qa_pixel"] == 8


def test_source_unchanged_and_reports_only(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    scene = make_scene(source)
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in scene.iterdir()}
    result = run_audit(source, (HOT_SCENE,))
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in scene.iterdir()}
    assert before == after
    assert result["overall_status"] == "PASS"
    item = result["scenes"][0]
    assert item["maximum_pixel"]["celsius"] == 100
    assert item["maximum_pixel"]["qa_pixel"] == 0
    assert item["clusters"]["above_80"]["pixel_count"] == 3
    assert item["clusters"]["above_80"]["largest_cluster_size"] == 2
    assert item["clusters"]["above_90"]["cluster_count"] == 2
    reports = tmp_path / "reports"
    write_reports(result, reports / "audit.json", reports / "audit.csv", reports / "audit.md")
    assert {path.name for path in reports.iterdir()} == {"audit.json", "audit.csv", "audit.md"}
    assert not (tmp_path / "data" / "processed").exists()
