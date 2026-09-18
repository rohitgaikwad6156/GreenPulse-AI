"""Build a real March-May Landsat 8/9 Level-2 surface-temperature raster.

Only USGS Collection 2 L2SP scene files are accepted. No demonstration data,
temperature constants, or invented measurements are used in this pipeline.
"""

from __future__ import annotations

import json
import math
import re
import tempfile
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as transform_geometry
from shapely.ops import unary_union


TARGET_CRS = "EPSG:32643"
PIXEL_SIZE_M = 30
OUTPUT_NODATA = -9999.0
BAD_QA_PIXEL_BITS = sum(1 << bit for bit in (0, 1, 2, 3, 4, 5, 7))
TERRAIN_OCCLUSION_BIT = 1 << 11
MAX_OUTPUT_CELLS = 8_000_000


@dataclass(frozen=True)
class Scene:
    """Paths and official per-scene calibration for one Landsat L2SP product."""

    product_id: str
    acquisition_date: date
    multiplier: float
    offset: float
    st_path: Path
    pixel_qa_path: Path
    radsat_qa_path: Path
    metadata_path: Path


def parse_mtl(metadata_path: Path) -> dict[str, str]:
    """Read key/value fields from an original USGS ``*_MTL.txt`` file.

    Missing or malformed files raise ValueError. Values retain their source
    text; the caller validates expected fields and numeric calibration.
    """
    if not metadata_path.is_file():
        raise ValueError(f"Landsat metadata file is missing: {metadata_path}")
    fields: dict[str, str] = {}
    pattern = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")
    for line in metadata_path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            fields[match.group(1)] = match.group(2).strip('"')
    if not fields:
        raise ValueError(f"No Landsat metadata fields found: {metadata_path}")
    return fields


def _companion(directory: Path, product_id: str, suffix: str) -> Path:
    """Find one USGS scene companion by name, ignoring TIFF extension case."""
    matches = [p for p in directory.iterdir() if p.is_file() and p.name.upper() == f"{product_id}_{suffix}.TIF".upper()]
    if len(matches) != 1:
        raise ValueError(f"Expected one {suffix}.TIF beside {product_id}_MTL.txt in {directory}")
    return matches[0]


def discover_scenes(scenes_dir: Path, year: int) -> list[Scene]:
    """Select original Landsat 8/9 C02 L2SP scenes acquired March-May.

    Each scene must include ST_B10, QA_PIXEL, QA_RADSAT, and MTL.txt. The
    temperature multiplier and offset come from that scene's MTL metadata.
    No matching scenes or missing/malformed calibration raises ValueError.
    """
    if not scenes_dir.is_dir():
        raise ValueError(f"Landsat scene directory is missing: {scenes_dir}")
    if not 2013 <= year <= date.today().year:
        raise ValueError("year must be between 2013 and the current year")
    scenes: list[Scene] = []
    seen: set[str] = set()
    for metadata_path in sorted(scenes_dir.rglob("*_MTL.txt")):
        fields = parse_mtl(metadata_path)
        product_id = fields.get("LANDSAT_PRODUCT_ID", "")
        if not (product_id.startswith(("LC08_L2SP_", "LC09_L2SP_")) and fields.get("COLLECTION_NUMBER") == "02"):
            continue
        if fields.get("PROCESSING_LEVEL") != "L2SP":
            continue
        if metadata_path.name != f"{product_id}_MTL.txt":
            raise ValueError(f"Metadata filename disagrees with LANDSAT_PRODUCT_ID: {metadata_path}")
        try:
            acquisition_date = date.fromisoformat(fields["DATE_ACQUIRED"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Invalid DATE_ACQUIRED in {metadata_path}") from exc
        if acquisition_date.year != year or acquisition_date.month not in (3, 4, 5):
            continue
        if product_id in seen:
            raise ValueError(f"Duplicate Landsat product: {product_id}")
        seen.add(product_id)
        try:
            multiplier = float(fields["TEMPERATURE_MULT_BAND_ST_B10"])
            offset = float(fields["TEMPERATURE_ADD_BAND_ST_B10"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Missing ST_B10 calibration in {metadata_path}") from exc
        if not math.isfinite(multiplier) or multiplier <= 0 or not math.isfinite(offset):
            raise ValueError(f"Invalid ST_B10 calibration in {metadata_path}")
        directory = metadata_path.parent
        scenes.append(
            Scene(
                product_id=product_id,
                acquisition_date=acquisition_date,
                multiplier=multiplier,
                offset=offset,
                st_path=_companion(directory, product_id, "ST_B10"),
                pixel_qa_path=_companion(directory, product_id, "QA_PIXEL"),
                radsat_qa_path=_companion(directory, product_id, "QA_RADSAT"),
                metadata_path=metadata_path,
            )
        )
    if not scenes:
        raise ValueError(f"No Landsat 8/9 C02 L2SP March-May {year} scenes found under {scenes_dir}")
    return sorted(scenes, key=lambda item: (item.acquisition_date, item.product_id))


def load_municipal_boundary(boundary_path: Path) -> Polygon | MultiPolygon:
    """Load a verified PMC+PCMC GeoJSON boundary in longitude/latitude.

    Requires exactly one or more polygon features for each municipality,
    identified by a ``municipality`` property of ``PMC`` or ``PCMC``. Invalid,
    empty, or missing geometry raises ValueError. Input coordinates are WGS84
    degrees; output geometry is projected to EPSG:32643 metres.
    """
    if not boundary_path.is_file():
        raise ValueError(f"PMC/PCMC boundary GeoJSON is missing: {boundary_path}")
    try:
        document = json.loads(boundary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read GeoJSON boundary: {boundary_path}") from exc
    if document.get("type") != "FeatureCollection":
        raise ValueError("Boundary must be a GeoJSON FeatureCollection")
    geometries = []
    municipalities = set()
    for feature in document.get("features", []):
        name = feature.get("properties", {}).get("municipality")
        if name not in ("PMC", "PCMC"):
            raise ValueError("Each boundary feature needs municipality=PMC or PCMC")
        geometry = shape(feature.get("geometry"))
        if not isinstance(geometry, (Polygon, MultiPolygon)) or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Invalid polygon for municipality {name}")
        bounds = geometry.bounds
        if not all(math.isfinite(value) for value in bounds) or not (-180 <= bounds[0] <= bounds[2] <= 180) or not (-90 <= bounds[1] <= bounds[3] <= 90):
            raise ValueError("Boundary coordinates must be finite WGS84 longitude/latitude")
        geometries.append(geometry)
        municipalities.add(name)
    if municipalities != {"PMC", "PCMC"}:
        raise ValueError("Boundary must contain both PMC and PCMC polygon features")
    transformer = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    projected = unary_union([transform_geometry(transformer.transform, geom) for geom in geometries])
    if projected.is_empty or not projected.is_valid or projected.area <= 0:
        raise ValueError("Combined PMC/PCMC boundary is invalid after projection")
    return projected


def target_grid(boundary: Polygon | MultiPolygon) -> tuple[object, int, int, np.ndarray]:
    """Create a 30 m EPSG:32643 grid and an inside-boundary pixel mask.

    Units are metres and 30 m pixels. Grid size above MAX_OUTPUT_CELLS and
    an empty rasterized boundary raise ValueError. A pixel is inside when its
    centre lies within the municipal polygon.
    """
    min_x, min_y, max_x, max_y = boundary.bounds
    west = math.floor(min_x / PIXEL_SIZE_M) * PIXEL_SIZE_M
    north = math.ceil(max_y / PIXEL_SIZE_M) * PIXEL_SIZE_M
    width = math.ceil((max_x - west) / PIXEL_SIZE_M)
    height = math.ceil((north - min_y) / PIXEL_SIZE_M)
    if width <= 0 or height <= 0 or width * height > MAX_OUTPUT_CELLS:
        raise ValueError("Boundary creates an empty or unexpectedly large 30 m raster")
    transform = from_origin(west, north, PIXEL_SIZE_M, PIXEL_SIZE_M)
    inside = rasterize(
        [(mapping(boundary), 1)],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        all_touched=False,
        dtype="uint8",
    ).astype(bool)
    if not inside.any():
        raise ValueError("Boundary contains no 30 m grid-cell centres")
    return transform, height, width, inside


def qa_valid_mask(dn: np.ndarray, qa_pixel: np.ndarray, qa_radsat: np.ndarray) -> np.ndarray:
    """Select nonfill, clear, land ST pixels from Landsat 8/9 C02 QA bands.

    Inputs are same-shaped uint16 arrays. Output is Boolean. ST DN=0, QA_PIXEL
    fill/dilated cloud/cirrus/cloud/shadow/snow/water bits 0-5 and 7, and
    QA_RADSAT terrain-occlusion bit 11 are excluded. Bad shapes or types raise
    ValueError. This mask does not claim that every remaining pixel is exact.
    """
    if dn.shape != qa_pixel.shape or dn.shape != qa_radsat.shape:
        raise ValueError("ST and QA arrays must have identical shapes")
    if any(array.dtype != np.dtype("uint16") for array in (dn, qa_pixel, qa_radsat)):
        raise ValueError("ST and QA arrays must be uint16")
    return (
        (dn != 0)
        & ((qa_pixel & BAD_QA_PIXEL_BITS) == 0)
        & ((qa_radsat & TERRAIN_OCCLUSION_BIT) == 0)
    )


def _warp_band(path: Path, transform: object, height: int, width: int) -> np.ndarray:
    """Nearest-neighbour reproject one uint16 Landsat band onto the target grid.

    DN and QA code values are unchanged. Missing source CRS or unexpected band
    type raises ValueError. Destination pixels outside the scene remain zero.
    """
    destination = np.zeros((height, width), dtype=np.uint16)
    with rasterio.open(path) as source:
        if source.count != 1 or source.crs is None or source.dtypes[0] != "uint16":
            raise ValueError(f"Expected a georeferenced one-band uint16 Landsat GeoTIFF: {path}")
        reproject(
            source=rasterio.band(source, 1),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=source.nodata if source.nodata is not None else 0,
            dst_transform=transform,
            dst_crs=TARGET_CRS,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )
    return destination


def scene_lst_c(scene: Scene, transform: object, height: int, width: int, inside: np.ndarray) -> np.ndarray:
    """Convert one QA-accepted L2SP ST_B10 scene to Celsius on the target grid.

    Conversion uses the multiplier and offset parsed from this scene's MTL:
    Celsius = DN * multiplier + offset - 273.15. Output is float32 Celsius;
    masked/out-of-scene pixels are NaN. No empirical temperature range is
    invented or used to fill missing pixels.
    """
    dn = _warp_band(scene.st_path, transform, height, width)
    pixel_qa = _warp_band(scene.pixel_qa_path, transform, height, width)
    radsat_qa = _warp_band(scene.radsat_qa_path, transform, height, width)
    valid = inside & qa_valid_mask(dn, pixel_qa, radsat_qa)
    result = np.full((height, width), np.nan, dtype=np.float32)
    result[valid] = (dn[valid].astype(np.float64) * scene.multiplier + scene.offset - 273.15).astype(np.float32)
    return result


def build_composite(scenes: list[Scene], boundary: Polygon | MultiPolygon) -> tuple[np.ndarray, np.ndarray, object, np.ndarray, list[str]]:
    """Take the pixelwise median of valid March-May scene temperatures.

    Output LST is °C float32, count is number of valid observations per pixel,
    and missing LST stays NaN. Scenes with zero accepted municipal pixels are
    omitted. No valid scene coverage raises ValueError.
    """
    transform, height, width, inside = target_grid(boundary)
    used_ids = []
    composite = np.full((height, width), np.nan, dtype=np.float32)
    count = np.zeros((height, width), dtype=np.uint16)
    # Keep scene layers on temporary disk, then compute an exact median in row
    # chunks. This avoids holding all city-wide scenes in RAM at once.
    with tempfile.TemporaryDirectory(prefix="greenpulse_landsat_") as temporary:
        paths = []
        for scene in scenes:
            layer = scene_lst_c(scene, transform, height, width, inside)
            if np.isfinite(layer[inside]).any():
                layer_path = Path(temporary) / f"scene_{len(paths):03d}.npy"
                np.save(layer_path, layer)
                paths.append(layer_path)
                used_ids.append(scene.product_id)
            del layer
        if not paths:
            raise ValueError("All supplied March-May scenes have zero valid PMC/PCMC LST pixels")
        layers = [np.load(path, mmap_mode="r") for path in paths]
        for start in range(0, height, 256):
            stop = min(start + 256, height)
            stack = np.stack([layer[start:stop] for layer in layers])
            count[start:stop] = np.count_nonzero(np.isfinite(stack), axis=0).astype(np.uint16)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning, message="All-NaN slice encountered")
                composite[start:stop] = np.nanmedian(stack, axis=0).astype(np.float32)
        del layers
    composite[~inside] = np.nan
    count[~inside] = 0
    return composite, count, transform, inside, used_ids


def summarize_lst(composite: np.ndarray, inside: np.ndarray) -> dict[str, float | int]:
    """Report real in-boundary LST min/max/mean and no-data percentage.

    Temperatures are °C and no-data percentage is [0, 100] of municipal grid
    cells. No finite in-boundary temperature raises ValueError.
    """
    values = composite[inside]
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        raise ValueError("No valid LST values exist inside PMC/PCMC")
    return {
        "municipal_grid_cells": int(values.size),
        "valid_grid_cells": int(valid.size),
        "nodata_percent": float(100.0 * (values.size - valid.size) / values.size),
        "min_lst_c": float(valid.min()),
        "max_lst_c": float(valid.max()),
        "mean_lst_c": float(valid.mean(dtype=np.float64)),
    }


def save_outputs(
    composite: np.ndarray,
    count: np.ndarray,
    transform: object,
    inside: np.ndarray,
    used_ids: list[str],
    scenes: list[Scene],
    year: int,
    output_path: Path,
) -> dict[str, float | int]:
    """Save measured GeoTIFF, valid-count GeoTIFF, QA JSON, and histogram.

    LST output is float32 °C with -9999 nodata. Count is uint16 scene count.
    Files are created only after at least one valid in-boundary LST pixel is
    confirmed; a missing scene/boundary cannot generate a raster.
    """
    summary = summarize_lst(composite, inside)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": composite.shape[0],
        "width": composite.shape[1],
        "count": 1,
        "crs": TARGET_CRS,
        "transform": transform,
        "compress": "DEFLATE",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(output_path, "w", **profile, dtype="float32", nodata=OUTPUT_NODATA) as dst:
        dst.write(np.where(np.isfinite(composite), composite, OUTPUT_NODATA).astype(np.float32), 1)
        dst.update_tags(
            units="deg C",
            source="USGS Landsat 8/9 Collection 2 Level-2 ST_B10",
            period=f"{year}-03-01/{year}-05-31",
            composite="pixelwise median of QA-accepted scenes",
            scene_ids=",".join(used_ids),
            note="LST is land surface temperature, not pedestrian air temperature",
        )
    count_path = output_path.with_name(output_path.stem + "_valid_count.tif")
    with rasterio.open(count_path, "w", **profile, dtype="uint16", nodata=0) as dst:
        dst.write(count, 1)
        dst.update_tags(units="valid scenes", note="Zero means no QA-accepted observation")
    report = {
        "data_type": "REAL USGS LANDSAT L2SP SURFACE TEMPERATURE",
        "period": f"{year}-03-01/{year}-05-31",
        "crs": TARGET_CRS,
        "resolution_m": PIXEL_SIZE_M,
        "composite": "pixelwise median of valid daytime scene LST",
        "qa_mask": "QA_PIXEL bits 0-5 and 7, QA_RADSAT bit 11, ST_B10 DN=0",
        "scene_calibration": [
            {
                "product_id": scene.product_id,
                "acquisition_date": scene.acquisition_date.isoformat(),
                "multiplier_from_mtl": scene.multiplier,
                "offset_from_mtl": scene.offset,
                "mtl_file": str(scene.metadata_path),
            }
            for scene in scenes if scene.product_id in used_ids
        ],
        "summary": summary,
    }
    report_path = output_path.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    histogram_path = output_path.with_name(output_path.stem + "_histogram.png")
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    ax.hist(composite[inside & np.isfinite(composite)], bins=35, color="#327a60", edgecolor="white")
    ax.set(xlabel="Land surface temperature (°C)", ylabel="30 m grid cells", title=f"PMC/PCMC Landsat LST — March–May {year}")
    ax.grid(axis="y", alpha=0.2)
    fig.savefig(histogram_path, dpi=160)
    plt.close(fig)
    return summary
