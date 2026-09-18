"""Unit tests for synthetic-independent geospatial feature formulas."""

import math
import unittest

import numpy as np
from shapely.geometry import Point, Polygon

from backend.app.geospatial.features import (
    built_percentage,
    distance_to_green_space,
    focal_mean,
    focal_variance,
    ndbi,
    ndvi,
    road_density,
    tree_canopy_percentage,
)


class SpectralIndexTests(unittest.TestCase):
    """Check band formulas, missing pixels, and invalid reflectance."""

    def test_ndvi_uses_b8_nir_and_b4_red(self) -> None:
        """NDVI follows the specified epsilon formula."""
        self.assertAlmostEqual(ndvi(0.6, 0.2), 0.4 / (0.8 + 1e-8))

    def test_ndbi_uses_b11_swir_and_b8_nir(self) -> None:
        """NDBI follows the specified epsilon formula."""
        self.assertAlmostEqual(ndbi(0.5, 0.2), 0.3 / (0.7 + 1e-8))

    def test_arrays_preserve_missing_values(self) -> None:
        """Missing and zero-zero pixels become NaN without losing valid pixels."""
        actual = ndvi(np.array([0.6, np.nan, 0.0]), np.array([0.2, 0.2, 0.0]))
        self.assertAlmostEqual(actual[0], 0.4 / (0.8 + 1e-8))
        self.assertTrue(np.isnan(actual[1]))
        self.assertTrue(np.isnan(actual[2]))
        self.assertTrue(math.isnan(ndbi(0.0, 0.0)))

    def test_invalid_bands_are_rejected(self) -> None:
        """Out-of-range, infinite, and shape-mismatched bands are invalid."""
        for first, second in [(-0.1, 0.2), (1.1, 0.2), (math.inf, 0.2), ([0.2], [0.1, 0.3])]:
            with self.subTest(first=first, second=second), self.assertRaises(ValueError):
                ndvi(first, second)


class AreaAndRoadTests(unittest.TestCase):
    """Check fractions and metre-to-kilometre road-density conversion."""

    def test_percentages(self) -> None:
        """A 30 m cell has 900 m² and supports 0–100 percent coverage."""
        self.assertEqual(tree_canopy_percentage(225, 900), 25)
        self.assertEqual(built_percentage(450, 900), 50)
        self.assertEqual(tree_canopy_percentage(0, 900), 0)
        self.assertEqual(built_percentage(900, 900), 100)

    def test_invalid_areas(self) -> None:
        """Negative, excessive, zero-cell, and missing areas are rejected."""
        for covered, cell in [(-1, 900), (901, 900), (1, 0), (math.nan, 900)]:
            with self.subTest(covered=covered, cell=cell), self.assertRaises(ValueError):
                tree_canopy_percentage(covered, cell)

    def test_road_density_units(self) -> None:
        """Thirty metres of road in a 900 m² cell is 33.333 km/km²."""
        self.assertAlmostEqual(road_density([12, 18], 900), 30 / 900 * 1000)
        self.assertEqual(road_density([], 900), 0)

    def test_invalid_road_inputs(self) -> None:
        """Bad lengths and areas cannot create a density."""
        for lengths, area in [([-1], 900), ([math.nan], 900), ([5], 0), ([5], math.inf)]:
            with self.subTest(lengths=lengths, area=area), self.assertRaises(ValueError):
                road_density(lengths, area)


class GreenDistanceTests(unittest.TestCase):
    """Check projected planar distance to polygon geometry."""

    def test_nearest_polygon_and_inside_point(self) -> None:
        """Distance is zero inside green space and reaches the nearest edge."""
        near = Polygon([(10, 0), (20, 0), (20, 10), (10, 10)])
        far = Polygon([(100, 0), (110, 0), (110, 10), (100, 10)])
        self.assertEqual(distance_to_green_space(Point(0, 5), [far, near]), 10)
        self.assertEqual(distance_to_green_space(Point(15, 5), [near]), 0)

    def test_empty_inventory_is_missing(self) -> None:
        """No mapped green spaces yield missing distance, not infinity."""
        self.assertTrue(math.isnan(distance_to_green_space(Point(0, 0), [])))

    def test_invalid_geometry_is_rejected(self) -> None:
        """A non-polygon candidate is not a valid green-space boundary."""
        with self.assertRaises(ValueError):
            distance_to_green_space(Point(0, 0), [Point(1, 1)])


class FocalTests(unittest.TestCase):
    """Check centred raster windows, missing cells, and population variance."""

    def test_mean_centre_and_edge(self) -> None:
        """A full 3×3 window averages nine cells; a corner averages four."""
        raster = np.arange(1, 10, dtype=float).reshape(3, 3)
        result = focal_mean(raster, 3)
        self.assertEqual(result[1, 1], 5)
        self.assertEqual(result[0, 0], 3)

    def test_population_variance(self) -> None:
        """Values 1–9 have population variance 20/3 at the centre."""
        raster = np.arange(1, 10, dtype=float).reshape(3, 3)
        self.assertAlmostEqual(focal_variance(raster, 3)[1, 1], 20 / 3)

    def test_missing_values_and_valid_count(self) -> None:
        """NaN cells are skipped and insufficient coverage remains NaN."""
        raster = np.array([[1.0, np.nan, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
        self.assertAlmostEqual(focal_mean(raster, 3, min_valid=5)[1, 1], 43 / 8)
        self.assertTrue(math.isnan(focal_mean(raster, 3, min_valid=5)[0, 0]))
        self.assertTrue(math.isnan(focal_variance(raster, 3, min_valid=5)[0, 0]))

    def test_invalid_windows_and_rasters(self) -> None:
        """Reject even windows, impossible coverage, infinities, and 1D input."""
        raster = np.ones((3, 3))
        for values, size, minimum in [
            (raster, 2, 1),
            (raster, 3, 10),
            (np.array([[math.inf]]), 3, 1),
            (np.array([1, 2, 3]), 3, 1),
        ]:
            with self.subTest(size=size, minimum=minimum), self.assertRaises(ValueError):
                focal_mean(values, size, minimum)


if __name__ == "__main__":
    unittest.main()
