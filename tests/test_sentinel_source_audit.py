"""Synthetic SAFE fixtures for manual intake validation; no real imagery is made."""

import hashlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from scripts.audit_sentinel_sources import audit_product

PRODUCT_ID = "S2A_MSIL2A_20250314T052649_N0511_R105_T43QCA_20250314T095315"
ITEM = {"product_id": PRODUCT_ID, "acquisition_datetime": "2025-03-14T05:26:49.024Z", "mgrs_tile": "MGRS-43QCA"}


def make_safe(root: Path, *, wrong_resolution: str | None = None) -> Path:
    safe = root / f"{PRODUCT_ID}.SAFE"
    safe.mkdir()
    (safe / "MTD_MSIL2A.xml").write_text(
        "<root><PROCESSING_BASELINE>05.11</PROCESSING_BASELINE>"
        "<BOA_QUANTIFICATION_VALUE>10000</BOA_QUANTIFICATION_VALUE>"
        "<BOA_ADD_OFFSET band_id='3'>-1000</BOA_ADD_OFFSET>"
        "<BOA_ADD_OFFSET band_id='7'>-1000</BOA_ADD_OFFSET>"
        "<BOA_ADD_OFFSET band_id='11'>-1000</BOA_ADD_OFFSET></root>",
        encoding="utf-8",
    )
    granule = safe / "GRANULE" / "SYNTHETIC_TEST_GRANULE" / "IMG_DATA"
    for label, resolution, dtype in (("B04", 10, "uint16"), ("B08", 10, "uint16"),
                                      ("B11", 20, "uint16"), ("SCL", 20, "uint8")):
        folder = granule / f"R{resolution}m"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"T43QCA_20250314T052649_{label}_{resolution}m.jp2"
        actual_resolution = (20 if resolution == 10 else 10) if wrong_resolution == label else resolution
        size = 4 if resolution == 10 else 2
        with rasterio.open(path, "w", driver="JP2OpenJPEG", height=size, width=size,
                           count=1, dtype=dtype, crs="EPSG:32643",
                           transform=from_origin(375000, 2050120, actual_resolution, actual_resolution)) as dataset:
            dataset.write(np.ones((size, size), dtype=dtype), 1)
    return safe


def test_valid_10m_and_20m_source(tmp_path: Path) -> None:
    make_safe(tmp_path)
    result = audit_product(ITEM, tmp_path)
    assert result["status"] == "PASS"
    assert all(result["required_files"].values())
    bands = result["granules"][0]["bands"]
    assert bands["B04_10m"]["resolution_m"] == [10.0, 10.0]
    assert bands["B11_20m"]["resolution_m"] == [20.0, 20.0]
    assert bands["B04_10m"]["width"] != bands["B11_20m"]["width"]
    assert all(len(record["sha256"]) == 64 for record in bands.values())


@pytest.mark.parametrize("band", ("B04", "B11"))
def test_wrong_10m_or_20m_resolution_fails(tmp_path: Path, band: str) -> None:
    make_safe(tmp_path, wrong_resolution=band)
    result = audit_product(ITEM, tmp_path)
    assert result["status"] == "FAIL"
    assert any("Expected north-up" in error for error in result["errors"])


def test_missing_metadata_fails(tmp_path: Path) -> None:
    safe = make_safe(tmp_path)
    (safe / "MTD_MSIL2A.xml").unlink()
    result = audit_product(ITEM, tmp_path)
    assert result["status"] == "FAIL"
    assert result["required_files"]["MTD_MSIL2A.xml"] is False


def test_missing_band_fails(tmp_path: Path) -> None:
    safe = make_safe(tmp_path)
    next(safe.rglob("*_B11_20m.jp2")).unlink()
    result = audit_product(ITEM, tmp_path)
    assert result["status"] == "FAIL"
    assert result["required_files"]["B11_20m"] is False


def test_wrong_tile_fails(tmp_path: Path) -> None:
    make_safe(tmp_path)
    result = audit_product({**ITEM, "mgrs_tile": "MGRS-43QDA"}, tmp_path)
    assert result["status"] == "FAIL"
    assert any("tile disagrees" in error for error in result["errors"])


@pytest.mark.parametrize("change", ("date", "product"))
def test_wrong_date_or_product_fails(tmp_path: Path, change: str) -> None:
    make_safe(tmp_path)
    item = ({**ITEM, "acquisition_datetime": "2025-03-15T05:26:49Z"} if change == "date"
            else {**ITEM, "product_id": PRODUCT_ID.replace("MSIL2A", "MSIL1C")})
    result = audit_product(item, tmp_path)
    assert result["status"] == "FAIL"
    assert any("disagrees" in error or "Level-2A" in error for error in result["errors"])


def test_unreadable_raster_fails(tmp_path: Path) -> None:
    safe = make_safe(tmp_path)
    next(safe.rglob("*_B04_10m.jp2")).write_bytes(b"corrupt synthetic JP2 fixture")
    result = audit_product(ITEM, tmp_path)
    assert result["status"] == "FAIL"
    band = result["granules"][0]["bands"]["B04_10m"]
    assert band["present"] is True
    assert band["readable"] is False


def test_duplicate_backend_band_match_fails(tmp_path: Path) -> None:
    safe = make_safe(tmp_path)
    band = next(safe.rglob("*_B04_10m.jp2"))
    band.with_name("T43QCA_20250314T052650_B04_10m.jp2").write_bytes(band.read_bytes())
    result = audit_product(ITEM, tmp_path)
    assert result["status"] == "FAIL"
    assert any("backend expects exactly one B04_10m" in error for error in result["errors"])


def test_mismatched_metadata_product_uri_fails(tmp_path: Path) -> None:
    safe = make_safe(tmp_path)
    metadata = safe / "MTD_MSIL2A.xml"
    metadata.write_text(metadata.read_text(encoding="utf-8").replace(
        "<root>", "<root><PRODUCT_URI>S2A_MSIL2A_OTHER.SAFE</PRODUCT_URI>"), encoding="utf-8")
    result = audit_product(ITEM, tmp_path)
    assert result["status"] == "FAIL"
    assert any("Metadata product URI differs" in error for error in result["errors"])


def test_audit_does_not_modify_source(tmp_path: Path) -> None:
    safe = make_safe(tmp_path)
    before = {path.relative_to(safe): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in safe.rglob("*") if path.is_file()}
    audit_product(ITEM, tmp_path)
    after = {path.relative_to(safe): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in safe.rglob("*") if path.is_file()}
    assert before == after
