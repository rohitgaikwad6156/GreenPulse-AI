"""Controlled TEST FIXTURES for Landsat processing; no real climate values."""

import json
import math
import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Polygon, mapping

from backend.app.geospatial.landsat_lst import (
    Scene,
    build_composite,
    discover_scenes,
    load_municipal_boundary,
    parse_mtl,
    qa_valid_mask,
    save_outputs,
    summarize_lst,
    target_grid,
)


class MetadataTests(unittest.TestCase):
    """Test original-MTL parsing and acquisition-season selection."""

    def test_metadata_scale_offset_and_season(self) -> None:
        """Calibration is read from file; a June product is excluded."""
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            selected = "LC08_L2SP_147047_20250315_20250320_02_T1"
            excluded = "LC09_L2SP_147047_20250615_20250620_02_T1"
            for product_id, acquisition in ((selected, "2025-03-15"), (excluded, "2025-06-15")):
                metadata = folder / f"{product_id}_MTL.txt"
                metadata.write_text(
                    f'LANDSAT_PRODUCT_ID = "{product_id}"\n'
                    'COLLECTION_NUMBER = 02\n'
                    'PROCESSING_LEVEL = "L2SP"\n'
                    f'DATE_ACQUIRED = {acquisition}\n'
                    'TEMPERATURE_MULT_BAND_ST_B10 = 0.004\n'
                    'TEMPERATURE_ADD_BAND_ST_B10 = 140.0\n',
                    encoding="utf-8",
                )
                for suffix in ("ST_B10", "QA_PIXEL", "QA_RADSAT"):
                    (folder / f"{product_id}_{suffix}.TIF").touch()
            fields = parse_mtl(folder / f"{selected}_MTL.txt")
            self.assertEqual(fields["TEMPERATURE_MULT_BAND_ST_B10"], "0.004")
            scenes = discover_scenes(folder, 2025)
            self.assertEqual(len(scenes), 1)
            self.assertEqual(scenes[0].product_id, selected)
            self.assertEqual(scenes[0].multiplier, 0.004)
            self.assertEqual(scenes[0].offset, 140.0)

    def test_missing_calibration_rejected(self) -> None:
        """A metadata file without official ST calibration cannot be used."""
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            product_id = "LC08_L2SP_147047_20250315_20250320_02_T1"
            (folder / f"{product_id}_MTL.txt").write_text(
                f"LANDSAT_PRODUCT_ID = {product_id}\nCOLLECTION_NUMBER = 02\n"
                "PROCESSING_LEVEL = L2SP\nDATE_ACQUIRED = 2025-03-15\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "calibration"):
                discover_scenes(folder, 2025)


class QualityMaskTests(unittest.TestCase):
    """Test each required Landsat Collection 2 QA rejection bit."""

    def test_cloud_shadow_snow_water_and_fill(self) -> None:
        """Only the unflagged, nonfill, unobscured land pixel survives."""
        flags = [0] + [1 << bit for bit in (0, 1, 2, 3, 4, 5, 7)]
        dn = np.full(len(flags) + 2, 45000, dtype=np.uint16)
        dn[-2] = 0
        pixel_qa = np.array(flags + [0, 0], dtype=np.uint16)
        radsat = np.zeros_like(dn)
        radsat[-1] = 1 << 11
        valid = qa_valid_mask(dn, pixel_qa, radsat)
        self.assertEqual(valid.tolist(), [True] + [False] * (len(flags) + 1))

    def test_bad_shapes_rejected(self) -> None:
        """Misregistered QA arrays cannot silently mask a scene."""
        with self.assertRaises(ValueError):
            qa_valid_mask(np.zeros(2, dtype=np.uint16), np.zeros(1, dtype=np.uint16), np.zeros(2, dtype=np.uint16))


class BoundaryAndSummaryTests(unittest.TestCase):
    """Test explicit two-municipality clipping and no-data reporting."""

    def test_boundary_requires_both_municipalities(self) -> None:
        """An omitted PCMC polygon is rejected."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test_boundary.geojson"
            polygon = Polygon([(73.84, 18.54), (73.85, 18.54), (73.85, 18.55), (73.84, 18.55)])
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"municipality": "PMC"}, "geometry": mapping(polygon)}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "both PMC and PCMC"):
                load_municipal_boundary(path)

    def test_grid_and_summary_ignore_outside_pixels(self) -> None:
        """Summary denominator is the municipal area, not bounding-box cells."""
        boundary = Polygon([(375000, 2050020), (375090, 2050020), (375090, 2050110), (375000, 2050110)])
        transform, height, width, inside = target_grid(boundary)
        self.assertEqual((height, width), (3, 3))
        self.assertEqual(transform, from_origin(375000, 2050110, 30, 30))
        composite = np.full((height, width), np.nan, dtype=np.float32)
        composite[inside] = 30.0  # TEST FIXTURE, not a climate observation.
        composite[0, 0] = np.nan
        summary = summarize_lst(composite, inside)
        self.assertEqual(summary["valid_grid_cells"], int(inside.sum()) - 1)
        self.assertEqual(summary["nodata_percent"], 100 / inside.sum())
        self.assertEqual(summary["mean_lst_c"], 30.0)

    def test_projected_boundary_from_geojson(self) -> None:
        """Both municipality features are transformed from WGS84 to UTM."""
        to_wgs84 = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
        west = Polygon([(375000, 2050000), (375060, 2050000), (375060, 2050060), (375000, 2050060)])
        east = Polygon([(375060, 2050000), (375120, 2050000), (375120, 2050060), (375060, 2050060)])
        from shapely.ops import transform as transform_geometry

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test_boundary.geojson"
            features = []
            for name, polygon in (("PMC", west), ("PCMC", east)):
                features.append({"type": "Feature", "properties": {"municipality": name}, "geometry": mapping(transform_geometry(to_wgs84.transform, polygon))})
            path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
            projected = load_municipal_boundary(path)
            self.assertTrue(math.isclose(projected.area, 7200, rel_tol=1e-7))


class PipelineFixtureTests(unittest.TestCase):
    """Exercise GeoTIFF I/O with tiny TEST FIXTURES, never real climate data."""

    def test_two_scene_composite_and_geotiff(self) -> None:
        """MTL-derived scaling, cloud exclusion, median, and output metadata work."""
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            affine = from_origin(375000, 2050110, 30, 30)
            profile = {"driver": "GTiff", "height": 2, "width": 4, "count": 1, "dtype": "uint16", "crs": "EPSG:32643", "transform": affine, "nodata": 0}
            scenes = []
            for index, dn_value in enumerate((45000, 46000), start=1):
                product_id = f"TEST_FIXTURE_{index}"
                st_path = folder / f"{product_id}_ST_B10.tif"
                pixel_qa_path = folder / f"{product_id}_QA_PIXEL.tif"
                radsat_path = folder / f"{product_id}_QA_RADSAT.tif"
                for path, data in (
                    (st_path, np.full((2, 4), dn_value, dtype=np.uint16)),
                    (pixel_qa_path, np.zeros((2, 4), dtype=np.uint16)),
                    (radsat_path, np.zeros((2, 4), dtype=np.uint16)),
                ):
                    if index == 2 and path == pixel_qa_path:
                        data[0, 0] = 1 << 3
                    with rasterio.open(path, "w", **profile) as dst:
                        dst.write(data, 1)
                scenes.append(Scene(product_id, date(2025, 3, index), 0.00341802, 149.0, st_path, pixel_qa_path, radsat_path, folder / "TEST_MTL.txt"))
            boundary = Polygon([(375000, 2050050), (375120, 2050050), (375120, 2050110), (375000, 2050110)])
            composite, count, transform, inside, ids = build_composite(scenes, boundary)
            first_c = 45000 * 0.00341802 + 149.0 - 273.15
            second_c = 46000 * 0.00341802 + 149.0 - 273.15
            self.assertAlmostEqual(float(composite[0, 0]), first_c, places=4)
            self.assertAlmostEqual(float(composite[0, 1]), (first_c + second_c) / 2, places=4)
            self.assertEqual(count[0, 0], 1)
            self.assertEqual(count[0, 1], 2)
            output = folder / "test_fixture_lst.tif"
            summary = save_outputs(composite, count, transform, inside, ids, scenes, 2025, output)
            self.assertEqual(summary["nodata_percent"], 0)
            with rasterio.open(output) as dataset:
                self.assertEqual(dataset.crs.to_string(), "EPSG:32643")
                self.assertEqual(dataset.res, (30, 30))
                self.assertEqual(dataset.tags()["units"], "deg C")
            self.assertTrue(output.with_suffix(".json").is_file())
            self.assertTrue(output.with_name(output.stem + "_histogram.png").is_file())


if __name__ == "__main__":
    unittest.main()
