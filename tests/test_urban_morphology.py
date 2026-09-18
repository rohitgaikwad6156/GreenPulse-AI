"""Artificial TEST FIXTURES only; no real Pune feature values are asserted."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Geod, Transformer
from rasterio.transform import from_origin
from shapely.geometry import LineString, box, mapping
from shapely.ops import transform as transform_geometry

from backend.app.geospatial.urban_morphology import (
    building_fraction_grid, discover_worldcover_tiles, green_distance_grid,
    load_osm_geometries, road_density_grid, save_layers, worldcover_fractions,
    worldpop_density_grid,
)


def _raster(path, values, transform, crs="EPSG:32643"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", count=1, width=values.shape[1], height=values.shape[0],
                       dtype=values.dtype, transform=transform, crs=crs, nodata=0) as dst:
        dst.write(values, 1)


def _geojson(path, features):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def _feature(geometry, properties):
    return {"type": "Feature", "geometry": mapping(geometry), "properties": properties}


class UrbanMorphologyTests(unittest.TestCase):
    def test_worldcover_fractions_and_missing_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            transform = from_origin(500000, 2050030, 30, 30)
            source_transform = from_origin(500000, 2050030, 10, 10)
            path = Path(temp) / "ESA_WorldCover_10m_2021_v200_N18E073_Map.tif"
            classes = np.array([[10, 10, 50], [10, 50, 50], [30, 30, 0]], dtype=np.uint8)
            _raster(path, classes, source_transform)
            self.assertEqual(discover_worldcover_tiles(Path(temp)), [path])
            tree, built, count = worldcover_fractions([path], transform, 1, 1, np.array([[True]]))
            self.assertEqual(int(count[0, 0]), 8)
            self.assertAlmostEqual(float(tree[0, 0]), 37.5)
            self.assertAlmostEqual(float(built[0, 0]), 37.5)
            with self.assertRaisesRegex(ValueError, "valid PMC/PCMC coverage"):
                empty = Path(temp) / "empty.tif"
                _raster(empty, np.zeros((3, 3), dtype=np.uint8), source_transform)
                worldcover_fractions([empty], transform, 1, 1, np.array([[True]]))

    def test_osm_length_distance_buildings_and_tag_filter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transform = from_origin(500000, 2050060, 30, 30)
            inside = np.ones((2, 2), dtype=bool)
            inverse = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
            road = transform_geometry(inverse.transform, LineString([(500005, 2050045), (500055, 2050045)]))
            footpath = transform_geometry(inverse.transform, LineString([(500005, 2050015), (500055, 2050015)]))
            park = transform_geometry(inverse.transform, box(500000, 2050030, 500010, 2050040))
            building = transform_geometry(inverse.transform, box(500030, 2050030, 500045, 2050045))
            roads_path, green_path, buildings_path = (root / name for name in ("roads.geojson", "green.geojson", "buildings.geojson"))
            _geojson(roads_path, [_feature(road, {"highway": "residential"}), _feature(footpath, {"highway": "footway"})])
            _geojson(green_path, [_feature(park, {"leisure": "park"})])
            _geojson(buildings_path, [_feature(building, {"building": "yes"})])
            roads = load_osm_geometries(roads_path, "roads")
            green = load_osm_geometries(green_path, "green")
            buildings = load_osm_geometries(buildings_path, "buildings")
            self.assertEqual(len(roads), 1)
            density = road_density_grid(roads, transform, 2, 2, inside)
            self.assertAlmostEqual(float(density[0, 0]), 25 / 900 * 1000, places=3)
            self.assertAlmostEqual(float(density[0, 1]), 25 / 900 * 1000, places=3)
            self.assertEqual(float(density[1, 0]), 0)
            distance = green_distance_grid(green, transform, 2, 2, inside)
            self.assertAlmostEqual(float(distance[0, 0]), 5 * 2**0.5, places=3)
            self.assertAlmostEqual(float(distance[0, 1]), (35**2 + 5**2)**0.5, places=3)
            fraction = building_fraction_grid(buildings, transform, 2, 2, inside)
            self.assertAlmostEqual(float(fraction[0, 1]), 225 / 900, places=3)

    def test_grid_edge_road_is_not_double_counted(self):
        transform = from_origin(500000, 2050060, 30, 30)
        inside = np.ones((2, 2), dtype=bool)
        edge = LineString([(500030, 2050035), (500030, 2050055)])
        result = road_density_grid([edge, edge], transform, 2, 2, inside)
        self.assertAlmostEqual(float(result[0, 1]), 20 / 900 * 1000, places=3)
        self.assertEqual(float(result[0, 0]), 0)

    def test_worldpop_counts_use_source_pixel_area_and_align(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transform = from_origin(500000, 2050060, 30, 30)
            inside = np.ones((2, 2), dtype=bool)
            source = root / "worldpop_test_counts.tif"
            _raster(source, np.array([[10]], dtype=np.float32), from_origin(500000, 2050060, 60, 60))
            result = worldpop_density_grid(source, transform, 2, 2, inside, "counts")
            np.testing.assert_allclose(result, 10 / 0.0036, rtol=1e-5)
            layers = {"tree_canopy_pct": np.zeros((2, 2), dtype=np.float32),
                      "built_pct": np.zeros((2, 2), dtype=np.float32),
                      "road_density": np.zeros((2, 2), dtype=np.float32),
                      "distance_green_m": np.ones((2, 2), dtype=np.float32),
                      "population_density": result}
            output = root / "TEST_ONLY_OUTPUT"
            stats = save_layers(layers, transform, inside, output, {name: "ARTIFICIAL TEST FIXTURE" for name in layers})
            self.assertEqual(len(stats), 5)
            with rasterio.open(output / "population_density_pune_30m.tif") as raster:
                self.assertEqual(raster.transform, transform)
                self.assertEqual(raster.crs.to_string(), "EPSG:32643")
                self.assertEqual(raster.shape, (2, 2))
            self.assertTrue((output / "morphology_qc_maps.png").is_file())

    def test_worldpop_wgs84_count_area_is_geodesic(self):
        with tempfile.TemporaryDirectory() as temp:
            target = from_origin(500000, 2050060, 30, 30)
            inverse = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
            west, south = inverse.transform(500000, 2050000)
            east, north = inverse.transform(500060, 2050060)
            west, east = west - 0.001, east + 0.001
            south, north = south - 0.001, north + 0.001
            source_transform = from_origin(west, north, east - west, north - south)
            path = Path(temp) / "ARTIFICIAL_worldpop_counts.tif"
            _raster(path, np.array([[100]], dtype=np.float32), source_transform, "EPSG:4326")
            result = worldpop_density_grid(path, target, 2, 2, np.ones((2, 2), dtype=bool), "counts")
            area, _ = Geod(ellps="WGS84").polygon_area_perimeter(
                [west, east, east, west], [north, north, south, south])
            np.testing.assert_allclose(result, 100 / (abs(area) / 1_000_000), rtol=1e-4)


if __name__ == "__main__":
    unittest.main()
