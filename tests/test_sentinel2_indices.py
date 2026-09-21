"""Tests use tiny artificial fixtures in temporary directories, never Pune data."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import mapping, box
from pyproj import Transformer

from backend.app.geospatial.landsat_lst import target_grid
from backend.app.geospatial.sentinel2_indices import (
    _aggregate_20m,
    boa_reflectance,
    build_composites,
    discover_granules,
    index_from_reflectance,
    read_boa_calibration,
    save_outputs,
    summarize_index,
    validate_reference,
)


def _write_raster(path, values, transform, crs="EPSG:32643", driver="GTiff"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver=driver, height=values.shape[0], width=values.shape[1],
                       count=1, dtype=values.dtype, crs=crs, transform=transform, nodata=0) as dst:
        dst.write(values, 1)


class Sentinel2IndicesTests(unittest.TestCase):
    def test_20m_to_30m_uses_area_overlap(self):
        source = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.float32)
        result = _aggregate_20m(source, from_origin(0, 40, 20, 20),
                                from_origin(0, 40, 30, 30), 1, 1)
        # Overlap areas are 400, 200, 200, and 100 m², respectively.
        self.assertAlmostEqual(float(result[0, 0]), 1.0 / 3.0, places=5)

    def test_calibration_requires_baseline_offsets(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "MTD_MSIL2A.xml"
            path.write_text("<root><PROCESSING_BASELINE>04.00</PROCESSING_BASELINE>"
                            "<BOA_QUANTIFICATION_VALUE>10000</BOA_QUANTIFICATION_VALUE>"
                            "<BOA_ADD_OFFSET band_id='3'>-1000</BOA_ADD_OFFSET>"
                            "<BOA_ADD_OFFSET band_id='7'>-1000</BOA_ADD_OFFSET>"
                            "<BOA_ADD_OFFSET band_id='11'>-1000</BOA_ADD_OFFSET></root>")
            self.assertEqual(read_boa_calibration(path), (10000.0, {"B04": -1000.0, "B08": -1000.0, "B11": -1000.0}))
            path.write_text(path.read_text().replace("<BOA_ADD_OFFSET band_id='11'>-1000</BOA_ADD_OFFSET>", ""))
            with self.assertRaisesRegex(ValueError, "Missing BOA_ADD_OFFSET"):
                read_boa_calibration(path)

    def test_reflectance_and_index_mask(self):
        dn = np.array([[5000, 0, 15000]], dtype=np.uint16)
        result = boa_reflectance(dn, -1000, 10000)
        self.assertAlmostEqual(float(result[0, 0]), 0.4)
        self.assertTrue(np.isnan(result[0, 1]))
        self.assertTrue(np.isnan(result[0, 2]))
        a = np.array([[0.6, 0.6, 0.0]], dtype=np.float32)
        b = np.array([[0.2, 0.2, 0.0]], dtype=np.float32)
        index = index_from_reflectance(a, b, np.array([[True, False, True]]))
        self.assertAlmostEqual(float(index[0, 0]), 0.5, places=6)
        self.assertTrue(np.isnan(index[0, 1]))
        self.assertTrue(np.isnan(index[0, 2]))
        with self.assertRaises(ValueError):
            index_from_reflectance(np.array([[1.2]]), np.array([[0.1]]), np.array([[True]]))

    def test_end_to_end_artificial_safe_and_exact_lst_grid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Artificial 90 m square near Pune coordinates, explicitly a TEST FIXTURE.
            region = box(500000, 2050000, 500090, 2050090)
            inverse = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
            from shapely.ops import transform as geom_transform
            lonlat = geom_transform(inverse.transform, region)
            mid = (lonlat.bounds[0] + lonlat.bounds[2]) / 2
            west = box(lonlat.bounds[0], lonlat.bounds[1], mid, lonlat.bounds[3])
            east = box(mid, lonlat.bounds[1], lonlat.bounds[2], lonlat.bounds[3])
            boundary_path = root / "boundary.geojson"
            boundary_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
                {"type": "Feature", "properties": {"municipality": "PMC"}, "geometry": mapping(west)},
                {"type": "Feature", "properties": {"municipality": "PCMC"}, "geometry": mapping(east)},
            ]}))
            from backend.app.geospatial.landsat_lst import load_municipal_boundary
            transform, height, width, inside = target_grid(load_municipal_boundary(boundary_path))
            lst_path = root / "lst_pune_30m.tif"
            _write_raster(lst_path, np.ones((height, width), dtype=np.float32), transform)
            with rasterio.open(lst_path, "r+") as lst:
                lst.update_tags(period="2025-03-01/2025-05-31")
            self.assertEqual(validate_reference(lst_path, boundary_path)[:3], (transform, height, width))
            self.assertEqual(validate_reference(lst_path, boundary_path, 2025)[:3], (transform, height, width))
            with self.assertRaisesRegex(ValueError, "period must be"):
                validate_reference(lst_path, boundary_path, 2024)
            safe = root / "raw" / "S2A_MSIL2A_20250415T050000_N0511_R001_T43QFA_20250415T100000.SAFE"
            metadata = safe / "MTD_MSIL2A.xml"
            metadata.parent.mkdir(parents=True)
            metadata.write_text("<root><PROCESSING_BASELINE>05.11</PROCESSING_BASELINE>"
                                "<BOA_QUANTIFICATION_VALUE>10000</BOA_QUANTIFICATION_VALUE>"
                                "<BOA_ADD_OFFSET band_id='3'>-1000</BOA_ADD_OFFSET>"
                                "<BOA_ADD_OFFSET band_id='7'>-1000</BOA_ADD_OFFSET>"
                                "<BOA_ADD_OFFSET band_id='11'>-1000</BOA_ADD_OFFSET></root>")
            granule = safe / "GRANULE" / "ARTIFICIAL_TEST_GRANULE" / "IMG_DATA"
            shape10 = (height * 3, width * 3)
            shape20 = (int(np.ceil(height * 1.5)), int(np.ceil(width * 1.5)))
            t10 = from_origin(transform.c, transform.f, 10, 10)
            t20 = from_origin(transform.c, transform.f, 20, 20)
            for band, value in (("B04", 3000), ("B08", 7000)):
                _write_raster(granule / "R10m" / f"TEST_{band}_10m.jp2", np.full(shape10, value, dtype=np.uint16), t10, driver="JP2OpenJPEG")
            _write_raster(granule / "R20m" / "TEST_B11_20m.jp2",
                          np.full(shape20, 5000, dtype=np.uint16), t20, driver="JP2OpenJPEG")
            # Real L2A SCL products may be uint8; the fixture exercises that production dtype.
            _write_raster(granule / "R20m" / "TEST_SCL_20m.jp2",
                          np.full(shape20, 5, dtype=np.uint8), t20, driver="JP2OpenJPEG")
            found = discover_granules(root / "raw", 2025)
            self.assertEqual(len(found), 1)
            ndvi, ndbi, nv, nb, used = build_composites(found, transform, height, width, inside)
            self.assertAlmostEqual(float(np.nanmedian(ndvi)), 0.5, delta=0.03)
            self.assertAlmostEqual(float(np.nanmedian(ndbi)), -0.2, delta=0.03)
            self.assertEqual(int(nv.max()), 1)
            self.assertEqual(int(nb.max()), 1)
            output = root / "TEST_ONLY_OUTPUT"
            stats = save_outputs(ndvi, ndbi, nv, nb, transform, inside, found, used, 2025, output)
            for name in ("ndvi", "ndbi"):
                with rasterio.open(output / f"{name}_pune_30m.tif") as source:
                    self.assertEqual(source.crs.to_string(), "EPSG:32643")
                    self.assertEqual(source.transform, transform)
                    self.assertEqual((source.height, source.width), (height, width))
                    self.assertGreaterEqual(stats[name]["min"], -1)
                    self.assertLessEqual(stats[name]["max"], 1)
            self.assertTrue((output / "sentinel2_indices_pune_30m_maps.png").is_file())
            self.assertTrue((output / "sentinel2_indices_pune_30m_histograms.png").is_file())

    def test_no_fabricated_empty_stats(self):
        with self.assertRaisesRegex(ValueError, "No valid index"):
            summarize_index(np.array([[np.nan]], dtype=np.float32), np.array([[True]]))


if __name__ == "__main__":
    unittest.main()
