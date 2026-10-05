"""Synthetic scenes only: verify the non-production Landsat smoke test."""

import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from scripts.audit_landsat_processing import audit_scene, run_audit, write_reports


PRODUCT_ID = "LC08_L2SP_147047_20250302_20250311_02_T1"
MULTIPLIER = 0.00341802
OFFSET = 149.0


def make_scene(
    root: Path, *, qa_flag: int = 0, radsat_flag: int = 0,
    bad_grid: str | None = None,
) -> Path:
    directory = root / PRODUCT_ID
    directory.mkdir()
    (directory / f"{PRODUCT_ID}_MTL.txt").write_text(
        f'LANDSAT_PRODUCT_ID = "{PRODUCT_ID}"\n'
        "PROCESSING_LEVEL = L2SP\nCOLLECTION_NUMBER = 02\nCOLLECTION_CATEGORY = T1\n"
        "WRS_PATH = 147\nWRS_ROW = 47\nSPACECRAFT_ID = LANDSAT_8\n"
        "DATE_ACQUIRED = 2025-03-02\n"
        f"TEMPERATURE_MULT_BAND_ST_B10 = {MULTIPLIER}\n"
        f"TEMPERATURE_ADD_BAND_ST_B10 = {OFFSET}\n",
        encoding="utf-8",
    )
    for suffix, values in (
        ("ST_B10", np.array([[45000, 45000]], dtype=np.uint16)),
        ("QA_PIXEL", np.array([[0, qa_flag]], dtype=np.uint16)),
        ("QA_RADSAT", np.array([[0, radsat_flag]], dtype=np.uint16)),
    ):
        profile = {
            "driver": "GTiff", "count": 1, "dtype": "uint16", "height": 1, "width": 2,
            "crs": "EPSG:32643", "transform": from_origin(375000, 2050110, 30, 30),
        }
        if suffix == "QA_PIXEL" and bad_grid == "dimensions":
            profile["width"] = 1
            values = values[:, :1]
        if suffix == "QA_PIXEL" and bad_grid == "crs":
            profile["crs"] = "EPSG:32644"
        if suffix == "QA_PIXEL" and bad_grid == "transform":
            profile["transform"] = from_origin(375030, 2050110, 30, 30)
        with rasterio.open(directory / f"{PRODUCT_ID}_{suffix}.TIF", "w", **profile) as dataset:
            dataset.write(values, 1)
    return directory


def test_dn_to_celsius_and_no_masked_values(tmp_path: Path) -> None:
    scene = make_scene(tmp_path, qa_flag=1 << 3)
    result = audit_scene(scene, PRODUCT_ID)
    expected = 45000 * MULTIPLIER + OFFSET - 273.15
    assert result["processing_status"] == "PASS"
    assert result["total_raster_pixels"] == 2
    assert result["nonzero_st_pixels"] == 2
    assert result["qa_valid_pixel_count"] == result["finite_celsius_pixel_count"] == 1
    assert result["qa_valid_percent"] == 50.0
    for key in ("minimum_celsius", "maximum_celsius", "mean_celsius", "median_celsius"):
        assert math.isclose(result[key], expected, abs_tol=1e-10)


@pytest.mark.parametrize("bit", (0, 1, 2, 3, 4, 5, 7))
def test_production_pixel_qa_rejects_flagged_pixels(tmp_path: Path, bit: int) -> None:
    result = audit_scene(make_scene(tmp_path, qa_flag=1 << bit), PRODUCT_ID)
    assert result["processing_status"] == "PASS"
    assert result["qa_valid_pixel_count"] == 1


def test_production_terrain_occlusion_rejected(tmp_path: Path) -> None:
    result = audit_scene(make_scene(tmp_path, radsat_flag=1 << 11), PRODUCT_ID)
    assert result["processing_status"] == "PASS"
    assert result["qa_valid_pixel_count"] == 1


@pytest.mark.parametrize("bad_grid", ("dimensions", "crs", "transform"))
def test_mismatched_grids_fail(tmp_path: Path, bad_grid: str) -> None:
    result = audit_scene(make_scene(tmp_path, bad_grid=bad_grid), PRODUCT_ID)
    assert result["processing_status"] == "FAIL"
    assert any("differ from ST_B10" in error for error in result["errors"])


def test_reports_only_no_production_artifact(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_scene(source, qa_flag=1 << 3)
    reports = tmp_path / "reports"
    result = run_audit(source, (PRODUCT_ID,))
    write_reports(result, reports / "audit.json", reports / "audit.csv", reports / "audit.md")
    assert result["overall_status"] == "PASS"
    assert {path.name for path in reports.iterdir()} == {"audit.json", "audit.csv", "audit.md"}
    assert not list(reports.rglob("*.tif"))
    assert not (tmp_path / "data" / "processed").exists()
