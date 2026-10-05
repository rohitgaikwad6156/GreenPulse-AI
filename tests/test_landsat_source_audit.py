"""Small synthetic fixtures for the source audit; never used as source data."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from scripts import audit_landsat_sources as audit


PRODUCT_ID = "LC08_L2SP_147047_20250302_20250311_02_T1"


def make_scene(folder: Path, *, qa_width: int = 2) -> Path:
    scene = folder / PRODUCT_ID
    scene.mkdir()
    (scene / f"{PRODUCT_ID}_MTL.txt").write_text(
        f'LANDSAT_PRODUCT_ID = "{PRODUCT_ID}"\n'
        "PROCESSING_LEVEL = L2SP\nCOLLECTION_NUMBER = 02\n"
        "COLLECTION_CATEGORY = T1\nSPACECRAFT_ID = LANDSAT_8\n"
        "WRS_PATH = 147\nWRS_ROW = 47\nDATE_ACQUIRED = 2025-03-02\n"
        "CLOUD_COVER = 2.19\nTEMPERATURE_MULT_BAND_ST_B10 = 0.00341802\n"
        "TEMPERATURE_ADD_BAND_ST_B10 = 149.0\n"
        f"LANDSAT_PRODUCT_ID = LC08_L1TP_147047_20250302_20250311_02_T1\n",
        encoding="utf-8",
    )
    for suffix in ("ST_B10", "QA_PIXEL", "QA_RADSAT"):
        width = 2 if suffix == "ST_B10" else qa_width
        with rasterio.open(
            scene / f"{PRODUCT_ID}_{suffix}.TIF", "w", driver="GTiff", width=width,
            height=2, count=1, dtype="uint16", crs="EPSG:32643",
            transform=from_origin(100, 200, 30, 30),
        ) as dst:
            dst.write(np.ones((2, width), dtype="uint16"), 1)
    return scene


def test_valid_scene_and_hashes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    result = audit.audit_scene(make_scene(tmp_path))
    assert result["status"] == "PASS"
    assert len(result["files"]) == 4
    assert all(len(file["sha256"]) == 64 for file in result["files"].values())


def test_raster_dimension_mismatch_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    result = audit.audit_scene(make_scene(tmp_path, qa_width=3))
    assert result["status"] == "FAIL"
    assert any("width differs from ST_B10.TIF" in error for error in result["errors"])


def test_missing_file_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    scene = make_scene(tmp_path)
    (scene / f"{PRODUCT_ID}_QA_RADSAT.TIF").unlink()
    result = audit.audit_scene(scene)
    assert result["status"] == "FAIL"
    assert result["required_files"]["QA_RADSAT.TIF"] is False
