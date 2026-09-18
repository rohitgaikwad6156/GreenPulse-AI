"""Validated grid feature calculations for GreenPulse AI.

Coordinates and geometries supplied to distance calculations must already be
in the same metre-based projected CRS, such as EPSG:32643. These functions
calculate features only; they do not load satellite data or train a model.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon


EPSILON = 1e-8


def _validated_band_pair(first: object, second: object) -> tuple[np.ndarray, np.ndarray, bool]:
    """Validate two reflectance bands in [0, 1]; permit NaN as missing data.

    Units: unitless reflectance fractions. Both inputs must have identical
    shapes, or both must be scalars. Negative, >1, infinite, nonnumeric, and
    mismatched inputs raise ValueError. The Boolean return marks scalar input.
    """
    try:
        a = np.asarray(first, dtype=np.float64)
        b = np.asarray(second, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Band values must be numeric reflectance fractions") from exc
    if a.shape != b.shape:
        raise ValueError("Band inputs must have identical shapes")
    if np.isinf(a).any() or np.isinf(b).any():
        raise ValueError("Band inputs cannot contain infinity")
    if ((a < 0) | (a > 1)).any() or ((b < 0) | (b > 1)).any():
        raise ValueError("Band reflectance must be between 0 and 1")
    return a, b, a.ndim == 0


def ndvi(nir: object, red: object) -> float | np.ndarray:
    """Compute Sentinel-2 NDVI = (B8 - B4) / (B8 + B4 + 1e-8).

    Units: unitless. Valid output: [-1, 1]. Inputs are scalar or same-shaped
    arrays of reflectance fractions in [0, 1]. NaN propagates. A pair of zero
    bands is undefined and returns NaN. Invalid inputs raise ValueError.
    """
    nir_values, red_values, scalar = _validated_band_pair(nir, red)
    denominator = nir_values + red_values
    result = np.where(denominator == 0, np.nan, (nir_values - red_values) / (denominator + EPSILON))
    return float(result) if scalar else result


def ndbi(swir: object, nir: object) -> float | np.ndarray:
    """Compute Sentinel-2 NDBI = (B11 - B8) / (B11 + B8 + 1e-8).

    Units: unitless. Valid output: [-1, 1]. Inputs are scalar or same-shaped
    arrays of reflectance fractions in [0, 1]. NaN propagates. A pair of zero
    bands is undefined and returns NaN. Invalid inputs raise ValueError.
    """
    swir_values, nir_values, scalar = _validated_band_pair(swir, nir)
    denominator = swir_values + nir_values
    result = np.where(denominator == 0, np.nan, (swir_values - nir_values) / (denominator + EPSILON))
    return float(result) if scalar else result


def _area_percentage(covered_area_m2: float, grid_cell_area_m2: float) -> float:
    """Return 100 times covered area / cell area, in percent [0, 100].

    Both areas are square metres. Nonfinite or negative covered area, nonfinite
    or nonpositive cell area, and coverage greater than cell area raise
    ValueError. Boundary contact without area may be represented by zero.
    """
    try:
        covered = float(covered_area_m2)
        cell = float(grid_cell_area_m2)
    except (TypeError, ValueError) as exc:
        raise ValueError("Areas must be numeric square-metre values") from exc
    if not math.isfinite(covered) or not math.isfinite(cell):
        raise ValueError("Areas must be finite")
    if covered < 0 or cell <= 0 or covered > cell:
        raise ValueError("Require 0 <= covered area <= positive cell area")
    return 100.0 * covered / cell


def tree_canopy_percentage(tree_canopy_area_m2: float, grid_cell_area_m2: float) -> float:
    """Calculate tree-canopy area as a percentage of one grid cell.

    Input units: m². Output unit and valid range: percent, [0, 100]. The area
    should be the canopy intersection with the cell, with overlap counted once.
    Invalid, nonfinite, or out-of-cell areas raise ValueError.
    """
    return _area_percentage(tree_canopy_area_m2, grid_cell_area_m2)


def built_percentage(built_area_m2: float, grid_cell_area_m2: float) -> float:
    """Calculate built-up area as a percentage of one grid cell.

    Input units: m². Output unit and valid range: percent, [0, 100]. The area
    should be the built-up intersection with the cell, with overlap counted
    once. Invalid, nonfinite, or out-of-cell areas raise ValueError.
    """
    return _area_percentage(built_area_m2, grid_cell_area_m2)


def road_density(road_lengths_m: Iterable[float], grid_cell_area_m2: float) -> float:
    """Return sum of road lengths divided by grid-cell area.

    Inputs: road centreline lengths in metres and area in m². Output: km/km²,
    valid range [0, infinity). An empty length collection gives zero only when
    the road inventory is known complete. Negative, nonfinite, nonnumeric, or
    missing lengths and nonpositive/nonfinite area raise ValueError. Clip roads
    to the chosen analysis area before passing their lengths.
    """
    try:
        area = float(grid_cell_area_m2)
        lengths = np.asarray(list(road_lengths_m), dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Provide numeric road lengths and cell area") from exc
    if not math.isfinite(area) or area <= 0:
        raise ValueError("Grid-cell area must be finite and positive")
    if lengths.ndim != 1 or not np.isfinite(lengths).all() or (lengths < 0).any():
        raise ValueError("Road lengths must be finite, nonnegative numbers")
    # (metres / m²) × 1000 = (kilometres / km²).
    return float(lengths.sum() / area * 1000.0)


def distance_to_green_space(
    point: Point, green_spaces: Iterable[Polygon | MultiPolygon]
) -> float:
    """Find the minimum planar distance from a point to a green-space polygon.

    Input coordinates must share a metre-based projected CRS. Output: metres,
    valid range [0, infinity); a point inside a polygon returns zero. An empty
    green-space collection returns NaN to signal unavailable coverage. Invalid
    or empty geometry, non-polygon green space, or nonfinite coordinates raise
    ValueError. This is geometric proximity, not a cooling-effect estimate.
    """
    if not isinstance(point, Point) or point.is_empty or not point.is_valid:
        raise ValueError("point must be a nonempty valid Shapely Point")
    if not all(math.isfinite(value) for value in point.bounds):
        raise ValueError("Point coordinates must be finite")
    try:
        spaces = list(green_spaces)
    except TypeError as exc:
        raise ValueError("green_spaces must be an iterable of polygons") from exc
    if not spaces:
        return math.nan
    for geometry in spaces:
        if not isinstance(geometry, (Polygon, MultiPolygon)) or geometry.is_empty or not geometry.is_valid:
            raise ValueError("Every green space must be a nonempty valid Polygon or MultiPolygon")
        if not all(math.isfinite(value) for value in geometry.bounds):
            raise ValueError("Green-space coordinates must be finite")
    return float(min(point.distance(geometry) for geometry in spaces))


def _focal_statistics(
    raster: object, window_size: int, min_valid: int
) -> tuple[np.ndarray, np.ndarray]:
    """Compute local mean and population variance for a square cell window.

    Input and mean units match the numeric raster; variance has squared units.
    NaN denotes missing cells, including out-of-raster padding. The valid
    count must reach min_valid or both outputs are NaN. Infinite, nonnumeric,
    non-2D, empty, even/nonpositive window, or invalid min_valid inputs raise
    ValueError. Variance uses n, not n-1, in the denominator.
    """
    try:
        values = np.asarray(raster, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Raster must contain numeric values or NaN") from exc
    if values.ndim != 2 or 0 in values.shape or np.isinf(values).any():
        raise ValueError("Raster must be a nonempty 2D array without infinity")
    if isinstance(window_size, bool) or not isinstance(window_size, int) or window_size < 1 or window_size % 2 == 0:
        raise ValueError("window_size must be a positive odd integer")
    if isinstance(min_valid, bool) or not isinstance(min_valid, int) or not 1 <= min_valid <= window_size**2:
        raise ValueError("min_valid must be between 1 and window_size squared")

    radius = window_size // 2
    padded = np.pad(values, radius, mode="constant", constant_values=np.nan)
    height, width = values.shape
    counts = np.zeros_like(values, dtype=np.int32)
    totals = np.zeros_like(values)

    for row_offset in range(window_size):
        for col_offset in range(window_size):
            shifted = padded[row_offset : row_offset + height, col_offset : col_offset + width]
            valid = ~np.isnan(shifted)
            counts += valid
            totals += np.where(valid, shifted, 0.0)

    means = np.full_like(values, np.nan)
    np.divide(totals, counts, out=means, where=counts >= min_valid)
    squared_deviations = np.zeros_like(values)
    for row_offset in range(window_size):
        for col_offset in range(window_size):
            shifted = padded[row_offset : row_offset + height, col_offset : col_offset + width]
            valid = ~np.isnan(shifted)
            squared_deviations += np.where(valid, (shifted - means) ** 2, 0.0)

    variances = np.full_like(values, np.nan)
    np.divide(squared_deviations, counts, out=variances, where=counts >= min_valid)
    return means, variances


def focal_mean(raster: object, window_size: int, min_valid: int = 1) -> np.ndarray:
    """Calculate the mean of valid cells in each centred square window.

    Output shape and units match the 2D input raster. Valid numeric output is
    finite; positions with too few valid cells are NaN. Edges use only cells
    inside the raster. NaN input cells are ignored. Invalid raster, window
    size, or min_valid raises ValueError. For Step 5 context features, use
    (window_size=3, min_valid=5) or (window_size=5, min_valid=13).
    """
    return _focal_statistics(raster, window_size, min_valid)[0]


def focal_variance(raster: object, window_size: int, min_valid: int = 1) -> np.ndarray:
    """Calculate population variance of valid cells in each square window.

    Output shape matches the 2D input. Units are input units squared; valid
    range is [0, infinity). The denominator is the number of valid cells n.
    Edges exclude out-of-raster cells and NaN cells are ignored. Too few valid
    cells produce NaN. Invalid raster, window size, or min_valid raises
    ValueError.
    """
    return _focal_statistics(raster, window_size, min_valid)[1]
