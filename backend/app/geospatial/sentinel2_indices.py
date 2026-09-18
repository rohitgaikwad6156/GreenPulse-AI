"""Real Sentinel-2 L2A March-May NDVI/NDBI, aligned to the Landsat LST grid."""

from __future__ import annotations

import json
import math
import re
import tempfile
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from rasterio.warp import reproject

from backend.app.geospatial.landsat_lst import (
    OUTPUT_NODATA,
    TARGET_CRS,
    load_municipal_boundary,
    target_grid,
)

EPSILON = 1e-8
VALID_SCL = (4, 5)  # vegetation and bare/built land; excludes water, cloud, shadow, snow
BAND_IDS = {"B04": "3", "B08": "7", "B11": "11"}
PRODUCT_NAME = re.compile(r"^S2[ABC]_MSIL2A_(\d{8})T\d{6}_.*\.SAFE$", re.IGNORECASE)


@dataclass(frozen=True)
class Granule:
    """One original L2A granule and its product-level radiometric metadata."""

    product_id: str
    granule_id: str
    acquisition_date: date
    bands: dict[str, Path]
    quantification: float
    offsets: dict[str, float]
    metadata_path: Path


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def read_boa_calibration(metadata_path: Path) -> tuple[float, dict[str, float]]:
    """Read BOA quantification and per-band additive DN offsets from SAFE XML.

    Returns unitless DN calibration. Baseline 04.00+ requires all three offsets;
    older products without offsets use zero. Missing/invalid XML raises ValueError.
    """
    try:
        root = ElementTree.parse(metadata_path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"Cannot read L2A product XML: {metadata_path}") from exc
    values = {}
    offsets_by_id = {}
    for element in root.iter():
        name = _local_name(element)
        if name in ("PROCESSING_BASELINE", "BOA_QUANTIFICATION_VALUE"):
            values[name] = (element.text or "").strip()
        elif name == "BOA_ADD_OFFSET":
            band_id = element.attrib.get("band_id")
            if band_id in offsets_by_id:
                raise ValueError(f"Duplicate BOA_ADD_OFFSET band_id={band_id} in {metadata_path}")
            offsets_by_id[band_id] = (element.text or "").strip()
    try:
        baseline = float(values["PROCESSING_BASELINE"])
        quantification = float(values["BOA_QUANTIFICATION_VALUE"])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Missing or invalid BOA calibration in {metadata_path}") from exc
    if not math.isfinite(baseline) or not math.isfinite(quantification) or quantification <= 0:
        raise ValueError(f"Invalid BOA calibration in {metadata_path}")
    offsets = {}
    for band, band_id in BAND_IDS.items():
        if baseline >= 4 and band_id not in offsets_by_id:
            raise ValueError(f"Missing BOA_ADD_OFFSET for {band} in {metadata_path}")
        try:
            offset = float(offsets_by_id.get(band_id, "0"))
        except ValueError as exc:
            raise ValueError(f"Invalid BOA_ADD_OFFSET for {band} in {metadata_path}") from exc
        if not math.isfinite(offset):
            raise ValueError(f"Non-finite BOA_ADD_OFFSET for {band} in {metadata_path}")
        offsets[band] = offset
    return quantification, offsets


def _find_band(directory: Path, band: str, resolution: int) -> Path:
    folder = directory / "IMG_DATA" / f"R{resolution}m"
    suffix = f"_{band}_{resolution}m.jp2" if band != "SCL" else f"_SCL_{resolution}m.jp2"
    matches = [p for p in folder.glob("*") if p.name.lower().endswith(suffix.lower())]
    if len(matches) != 1:
        raise ValueError(f"Expected one {band} {resolution} m JP2 in {folder}")
    return matches[0]


def discover_granules(scenes_dir: Path, year: int) -> list[Granule]:
    """Find complete extracted Sentinel-2 L2A SAFE granules for March-May year."""
    if not scenes_dir.is_dir():
        raise ValueError(f"Sentinel-2 scene directory is missing: {scenes_dir}")
    if not 2017 <= year <= date.today().year:
        raise ValueError("year must be from 2017 through the current year")
    granules = []
    seen = set()
    for product in sorted(p for p in scenes_dir.rglob("*.SAFE") if p.is_dir()):
        match = PRODUCT_NAME.match(product.name)
        if not match:
            continue
        acquisition = date.fromisoformat(match.group(1))
        if acquisition.year != year or acquisition.month not in (3, 4, 5):
            continue
        metadata_path = product / "MTD_MSIL2A.xml"
        quantification, offsets = read_boa_calibration(metadata_path)
        granule_directories = sorted(p for p in (product / "GRANULE").iterdir() if p.is_dir()) if (product / "GRANULE").is_dir() else []
        if not granule_directories:
            raise ValueError(f"No granules in {product}")
        for directory in granule_directories:
            key = (product.name, directory.name)
            if key in seen:
                raise ValueError(f"Duplicate granule {key}")
            seen.add(key)
            bands = {
                "B04": _find_band(directory, "B04", 10),
                "B08": _find_band(directory, "B08", 10),
                "B11": _find_band(directory, "B11", 20),
                "SCL": _find_band(directory, "SCL", 20),
            }
            granules.append(Granule(product.name, directory.name, acquisition, bands, quantification, offsets, metadata_path))
    if not granules:
        raise ValueError(f"No extracted Sentinel-2 L2A March-May {year} SAFE granules found under {scenes_dir}")
    return granules


def validate_reference(lst_path: Path, boundary_path: Path, year: int | None = None) -> tuple[Affine, int, int, np.ndarray]:
    """Require a 30 m LST GeoTIFF matching PMC/PCMC extent and, if set, year."""
    if not lst_path.is_file():
        raise ValueError(f"Real LST reference GeoTIFF is missing: {lst_path}")
    boundary = load_municipal_boundary(boundary_path)
    expected_transform, expected_height, expected_width, inside = target_grid(boundary)
    with rasterio.open(lst_path) as source:
        if (source.crs is None or source.crs.to_string() != TARGET_CRS or source.count != 1
                or source.transform != expected_transform or source.width != expected_width
                or source.height != expected_height or source.res != (30.0, 30.0)):
            raise ValueError("LST reference CRS, transform, extent, or dimensions disagree with the verified PMC/PCMC 30 m grid")
        if source.dtypes[0] != "float32":
            raise ValueError("LST reference must be a float32 GeoTIFF")
        if year is not None and source.tags().get("period") != f"{year}-03-01/{year}-05-31":
            raise ValueError(f"LST reference period must be March-May {year}; build LST for the same year first")
    return expected_transform, expected_height, expected_width, inside


def boa_reflectance(dn: np.ndarray, offset: float, quantification: float) -> np.ndarray:
    """Convert L2A uint16 DN to unitless BOA reflectance in [0,1]; invalid to NaN."""
    if dn.dtype != np.uint16 or not math.isfinite(offset) or not math.isfinite(quantification) or quantification <= 0:
        raise ValueError("Expected uint16 DN and finite BOA calibration with positive quantification")
    values = (dn.astype(np.float32) + offset) / quantification
    values[(dn == 0) | (values < 0) | (values > 1)] = np.nan
    return values


def index_from_reflectance(numerator_a: np.ndarray, numerator_b: np.ndarray, valid_scl: np.ndarray) -> np.ndarray:
    """Return (a-b)/(a+b+1e-8) on clear land; invalid pixels become NaN.

    Both inputs are unitless reflectance [0,1] with the same shape. Output is
    unitless [-1,1]. Rejects bad shapes and out-of-range finite reflectance.
    """
    if numerator_a.shape != numerator_b.shape or numerator_a.shape != valid_scl.shape:
        raise ValueError("Index reflectance and SCL masks must have matching shapes")
    if np.any(np.isfinite(numerator_a) & ((numerator_a < 0) | (numerator_a > 1))) or np.any(np.isfinite(numerator_b) & ((numerator_b < 0) | (numerator_b > 1))):
        raise ValueError("Reflectance values must be within [0,1] or NaN")
    valid = valid_scl & np.isfinite(numerator_a) & np.isfinite(numerator_b) & ((numerator_a + numerator_b) > 0)
    result = np.full(numerator_a.shape, np.nan, dtype=np.float32)
    result[valid] = ((numerator_a[valid] - numerator_b[valid]) / (numerator_a[valid] + numerator_b[valid] + EPSILON)).astype(np.float32)
    return result


def _read_vrt(path: Path, transform: Affine, height: int, width: int, window: Window, resampling: Resampling) -> np.ndarray:
    with rasterio.open(path) as source:
        if source.count != 1 or source.crs is None or source.dtypes[0] != "uint16":
            raise ValueError(f"Expected georeferenced single-band uint16 Sentinel-2 JP2: {path}")
        with WarpedVRT(source, crs=TARGET_CRS, transform=transform, width=width, height=height,
                       src_nodata=0, nodata=0, resampling=resampling) as vrt:
            return vrt.read(1, window=window)


def _aggregate_10m(index: np.ndarray, rows: int, width: int) -> np.ndarray:
    blocks = index.reshape(rows, 3, width, 3)
    count = np.isfinite(blocks).sum(axis=(1, 3))
    total = np.nansum(blocks, axis=(1, 3))
    result = np.full((rows, width), np.nan, dtype=np.float32)
    good = count >= 5  # at least five of nine subpixels have clear land observations
    result[good] = (total[good] / count[good]).astype(np.float32)
    return result


def _aggregate_20m(index: np.ndarray, source_transform: Affine, target_transform: Affine,
                   rows: int, width: int) -> np.ndarray:
    result = np.full((rows, width), np.nan, dtype=np.float32)
    coverage = np.zeros((rows, width), dtype=np.float32)
    reproject(index, result, src_transform=source_transform, src_crs=TARGET_CRS, src_nodata=np.nan,
              dst_transform=target_transform, dst_crs=TARGET_CRS, dst_nodata=np.nan, resampling=Resampling.average)
    reproject(np.isfinite(index).astype(np.float32), coverage, src_transform=source_transform,
              src_crs=TARGET_CRS, src_nodata=None, dst_transform=target_transform,
              dst_crs=TARGET_CRS, dst_nodata=0, resampling=Resampling.average)
    result[coverage < 0.5] = np.nan
    return result


def granule_indices(granule: Granule, transform: Affine, height: int, width: int, inside: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute 30 m indices with native 10 m NDVI and native 20 m B11 NDBI."""
    ndvi = np.full((height, width), np.nan, dtype=np.float32)
    ndbi = np.full((height, width), np.nan, dtype=np.float32)
    transform10 = Affine(10, 0, transform.c, 0, -10, transform.f)
    transform20 = Affine(20, 0, transform.c, 0, -20, transform.f)
    height20, width20 = math.ceil(height * 1.5), math.ceil(width * 1.5)
    for start in range(0, height, 64):  # even starts keep 20 m windows aligned
        rows = min(64, height - start)
        win10 = Window(0, start * 3, width * 3, rows * 3)
        start20 = start * 3 // 2
        rows20 = math.ceil(rows * 1.5)
        win20 = Window(0, start20, width20, rows20)
        b4_10 = _read_vrt(granule.bands["B04"], transform10, height * 3, width * 3, win10, Resampling.nearest)
        b8_10 = _read_vrt(granule.bands["B08"], transform10, height * 3, width * 3, win10, Resampling.nearest)
        scl10 = _read_vrt(granule.bands["SCL"], transform10, height * 3, width * 3, win10, Resampling.nearest)
        red = boa_reflectance(b4_10, granule.offsets["B04"], granule.quantification)
        nir10 = boa_reflectance(b8_10, granule.offsets["B08"], granule.quantification)
        ndvi_block = index_from_reflectance(nir10, red, np.isin(scl10, VALID_SCL))
        ndvi[start:start + rows] = _aggregate_10m(ndvi_block, rows, width)
        del b4_10, b8_10, scl10, red, nir10, ndvi_block

        b8_20 = _read_vrt(granule.bands["B08"], transform20, height20, width20, win20, Resampling.average)
        b11_20 = _read_vrt(granule.bands["B11"], transform20, height20, width20, win20, Resampling.nearest)
        scl20 = _read_vrt(granule.bands["SCL"], transform20, height20, width20, win20, Resampling.nearest)
        nir20 = boa_reflectance(b8_20, granule.offsets["B08"], granule.quantification)
        swir20 = boa_reflectance(b11_20, granule.offsets["B11"], granule.quantification)
        ndbi_block = index_from_reflectance(swir20, nir20, np.isin(scl20, VALID_SCL))
        source_transform = transform20 @ Affine.translation(0, start20)
        target_transform = transform @ Affine.translation(0, start)
        ndbi[start:start + rows] = _aggregate_20m(ndbi_block, source_transform, target_transform, rows, width)
    ndvi[~inside] = np.nan
    ndbi[~inside] = np.nan
    return ndvi, ndbi


def build_composites(granules: list[Granule], transform: Affine, height: int, width: int,
                     inside: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Mosaic granules per date, then take pixelwise March-May median by date."""
    dates = sorted({g.acquisition_date for g in granules})
    used = []
    ndvi_final = np.full((height, width), np.nan, dtype=np.float32)
    ndbi_final = np.full((height, width), np.nan, dtype=np.float32)
    ndvi_count = np.zeros((height, width), dtype=np.uint16)
    ndbi_count = np.zeros((height, width), dtype=np.uint16)
    with tempfile.TemporaryDirectory(prefix="greenpulse_sentinel2_") as temporary:
        date_paths = []
        for acquisition in dates:
            daily_ndvi = np.full((height, width), np.nan, dtype=np.float32)
            daily_ndbi = np.full((height, width), np.nan, dtype=np.float32)
            for granule in (g for g in granules if g.acquisition_date == acquisition):
                layer_ndvi, layer_ndbi = granule_indices(granule, transform, height, width, inside)
                added = False
                for daily, layer in ((daily_ndvi, layer_ndvi), (daily_ndbi, layer_ndbi)):
                    take = np.isfinite(layer) & ~np.isfinite(daily)
                    daily[take] = layer[take]
                    added |= bool(np.any(take))
                if added:
                    used.append(f"{granule.product_id}/{granule.granule_id}")
            if np.isfinite(daily_ndvi).any() or np.isfinite(daily_ndbi).any():
                paths = (Path(temporary) / f"ndvi_{acquisition}.npy", Path(temporary) / f"ndbi_{acquisition}.npy")
                np.save(paths[0], daily_ndvi)
                np.save(paths[1], daily_ndbi)
                date_paths.append(paths)
        if not date_paths:
            raise ValueError("All supplied March-May Sentinel-2 granules have zero QA-accepted PMC/PCMC pixels")
        for output, count, which in ((ndvi_final, ndvi_count, 0), (ndbi_final, ndbi_count, 1)):
            layers = [np.load(paths[which], mmap_mode="r") for paths in date_paths]
            for start in range(0, height, 64):
                end = min(start + 64, height)
                stack = np.stack([layer[start:end] for layer in layers])
                count[start:end] = np.isfinite(stack).sum(axis=0).astype(np.uint16)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=RuntimeWarning, message="All-NaN slice encountered")
                    output[start:end] = np.nanmedian(stack, axis=0).astype(np.float32)
            del stack, layers  # close Windows memmaps before TemporaryDirectory cleanup
    for output, count in ((ndvi_final, ndvi_count), (ndbi_final, ndbi_count)):
        output[~inside] = np.nan
        count[~inside] = 0
    return ndvi_final, ndbi_final, ndvi_count, ndbi_count, used


def summarize_index(values: np.ndarray, inside: np.ndarray) -> dict[str, int | float]:
    """Summarize in-boundary dimensionless index values and missingness."""
    if values.shape != inside.shape:
        raise ValueError("Index and municipal mask shapes differ")
    selected = values[inside]
    valid = selected[np.isfinite(selected)]
    if not valid.size:
        raise ValueError("No valid index pixels inside PMC/PCMC")
    if np.any((valid < -1.000001) | (valid > 1.000001)):
        raise ValueError("Index values outside expected [-1,1] range")
    return {"municipal_grid_cells": int(selected.size), "valid_grid_cells": int(valid.size),
            "nodata_percent": float(100 * (selected.size - valid.size) / selected.size),
            "min": float(valid.min()), "max": float(valid.max()), "mean": float(valid.mean(dtype=np.float64))}


def save_outputs(ndvi: np.ndarray, ndbi: np.ndarray, ndvi_count: np.ndarray, ndbi_count: np.ndarray,
                 transform: Affine, inside: np.ndarray, granules: list[Granule], used: list[str], year: int,
                 output_dir: Path) -> dict[str, dict[str, int | float]]:
    """Save real-data 30 m GeoTIFFs, valid-date counts, QA JSON, maps, histogram."""
    stats = {"ndvi": summarize_index(ndvi, inside), "ndbi": summarize_index(ndbi, inside)}
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", height=ndvi.shape[0], width=ndvi.shape[1], count=1,
                   crs=TARGET_CRS, transform=transform, compress="DEFLATE", tiled=True,
                   blockxsize=256, blockysize=256)
    for name, array, count in (("ndvi", ndvi, ndvi_count), ("ndbi", ndbi, ndbi_count)):
        path = output_dir / f"{name}_pune_30m.tif"
        with rasterio.open(path, "w", **profile, dtype="float32", nodata=OUTPUT_NODATA) as dst:
            dst.write(np.where(np.isfinite(array), array, OUTPUT_NODATA).astype(np.float32), 1)
            dst.update_tags(units="unitless", source="Copernicus Sentinel-2 Level-2A BOA reflectance",
                            period=f"{year}-03-01/{year}-05-31", composite="median of daily clear-land indices",
                            note="Real data only; spatial resolution of output is 30 m")
        with rasterio.open(output_dir / f"{name}_pune_30m_valid_count.tif", "w", **profile, dtype="uint16", nodata=0) as dst:
            dst.write(count, 1)
            dst.update_tags(units="valid acquisition dates")
    report = {"data_type": "REAL COPERNICUS SENTINEL-2 L2A BOA INDICES", "period": f"{year}-03-01/{year}-05-31",
              "crs": TARGET_CRS, "pixel_size_m": 30, "scl_accepted": list(VALID_SCL),
              "calibration": "(DN + product BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE",
              "ndvi": "(B08 - B04) / (B08 + B04 + 1e-8)",
              "ndbi": "(B11 - B08) / (B11 + B08 + 1e-8)",
              "granules_used": used,
              "source_metadata": sorted({str(g.metadata_path) for g in granules if f"{g.product_id}/{g.granule_id}" in used}),
              "summary": stats}
    (output_dir / "sentinel2_indices_pune_30m.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    for ax, name, array, cmap in zip(axes, ("NDVI", "NDBI"), (ndvi, ndbi), ("RdYlGn", "RdYlBu_r")):
        shown = np.ma.masked_invalid(array)
        image = ax.imshow(shown, cmap=cmap, vmin=-1, vmax=1, interpolation="nearest")
        ax.set(title=f"{name} — PMC/PCMC, Mar–May {year}", xlabel="30 m grid column", ylabel="30 m grid row")
        fig.colorbar(image, ax=ax, label=f"{name} (unitless)")
    fig.savefig(output_dir / "sentinel2_indices_pune_30m_maps.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for ax, name, array, color in zip(axes, ("NDVI", "NDBI"), (ndvi, ndbi), ("#397a53", "#8b7048")):
        ax.hist(array[inside & np.isfinite(array)], bins=40, range=(-1, 1), color=color)
        ax.set(xlabel=f"{name} (unitless)", ylabel="30 m grid cells", title=f"{name} distribution")
    fig.savefig(output_dir / "sentinel2_indices_pune_30m_histograms.png", dpi=150)
    plt.close(fig)
    return stats
