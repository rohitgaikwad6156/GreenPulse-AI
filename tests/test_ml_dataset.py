"""End-to-end assembly with explicitly ARTIFICIAL temporary test fixtures."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import rasterio
from affine import Affine
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform as transform_geometry

from backend.app.geospatial.landsat_lst import load_municipal_boundary, target_grid
from backend.app.geospatial.ml_dataset import build_ml_dataset, load_wards


def _write_raster(path, values, transform, period=None, shift_x=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    dtype = str(values.dtype)
    with rasterio.open(path, "w", driver="GTiff", count=1, height=values.shape[0],
                       width=values.shape[1], dtype=dtype, crs="EPSG:32643",
                       transform=Affine(transform.a, 0, transform.c + shift_x, 0, transform.e, transform.f),
                       nodata=-9999 if dtype == "float32" else 0) as dst:
        dst.write(values, 1)
        if period:
            dst.update_tags(period=period, source="ARTIFICIAL TEST FIXTURE")


def _fixture(root):
    inverse = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
    municipal_polys = [box(500000, 2050000, 500150, 2050300),
                       box(500150, 2050000, 500300, 2050300)]
    features = []
    wards = []
    for name, polygon in zip(("PMC", "PCMC"), municipal_polys):
        wgs = transform_geometry(inverse.transform, polygon)
        features.append({"type": "Feature", "properties": {"municipality": name},
                         "geometry": mapping(wgs)})
        wards.append({"type": "Feature", "properties": {"municipality": name,
                        "ward_id": "1", "ward_name": f"ARTIFICIAL {name} ward"}, "geometry": mapping(wgs)})
    boundary_dir = root / "data" / "boundaries"
    boundary_dir.mkdir(parents=True)
    boundary_path = boundary_dir / "pmc_pcmc.geojson"
    ward_path = boundary_dir / "pmc_pcmc_wards.geojson"
    boundary_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    ward_path.write_text(json.dumps({"type": "FeatureCollection", "features": wards}))
    transform, height, width, inside = target_grid(load_municipal_boundary(boundary_path))
    yy, xx = np.mgrid[:height, :width]
    period = "2025-03-01/2025-05-31"
    processed = root / "data" / "processed"
    morphology = root / "data" / "interim" / "morphology"
    lst = (30 + yy * 0.1 + xx * 0.2).astype(np.float32)
    ndvi = (0.1 + xx * 0.03).astype(np.float32)
    ndbi = (0.4 - xx * 0.02).astype(np.float32)
    lst[3, 3] = -9999
    ndvi[4, 4] = -9999
    for name, values in (("lst", lst), ("ndvi", ndvi), ("ndbi", ndbi)):
        _write_raster(processed / f"{name}_pune_30m.tif", values, transform, period)
        count = np.ones((height, width), dtype=np.uint16)
        count[values == -9999] = 0
        _write_raster(processed / f"{name}_pune_30m_valid_count.tif", count, transform)
    layers = {"tree_canopy_pct": (10 + xx * 1.5).astype(np.float32),
              "built_pct": (40 - xx * 1.2).astype(np.float32),
              "road_density": (5 + yy * 0.1).astype(np.float32),
              "distance_green_m": (20 + yy * 3).astype(np.float32),
              "population_density": (1000 + xx * 30 + yy * 20).astype(np.float32)}
    for name, values in layers.items():
        _write_raster(morphology / f"{name}_pune_30m.tif", values, transform)
    (morphology / "morphology_qc.json").write_text(json.dumps({
        "data_type": "REAL-SOURCE URBAN MORPHOLOGY FEATURES",
        "source_files": {name: "ARTIFICIAL TEST FIXTURE" for name in layers}}))
    return ward_path, transform, inside, morphology


class MlDatasetTests(unittest.TestCase):
    def test_documented_optional_albedo_is_included(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ward_path, transform, inside, _ = _fixture(root)
            albedo = root / "data" / "processed" / "albedo_pune_30m.tif"
            _write_raster(albedo, np.full(inside.shape, 0.2, dtype=np.float32),
                          transform, "2025-03-01/2025-05-31")
            output = root / "data" / "processed" / "greenpulse_ml_grid.parquet"
            report = build_ml_dataset(root, ward_path, output, root / "data" / "processed" / "metadata.json",
                                      albedo_path=albedo, csv_sample_rows=0)
            self.assertIn("albedo", pq.read_schema(output).names)
            self.assertEqual(report["row_count"], pq.read_metadata(output).num_rows)

    def test_complete_case_parquet_metadata_and_no_fabrication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ward_path, _, inside, _ = _fixture(root)
            output = root / "data" / "processed" / "greenpulse_ml_grid.parquet"
            metadata = root / "data" / "processed" / "metadata.json"
            report = build_ml_dataset(root, ward_path, output, metadata, csv_sample_rows=5, chunk_rows=4)
            self.assertGreater(report["row_count"], 0)
            self.assertLess(report["row_count"], int(inside.sum()))
            self.assertGreater(report["missing_cells_by_column_before_filter"]["lst_c"], 0)
            self.assertGreater(report["missing_cells_by_column_before_filter"]["ndvi"], 0)
            self.assertEqual(report["date_range"], "2025-03-01/2025-05-31")
            self.assertEqual(report["crs"], "EPSG:32643")
            self.assertEqual(report["raster_resolution_m"], 30)
            table = pq.read_table(output)
            self.assertEqual(table.num_rows, report["row_count"])
            self.assertNotIn("albedo", table.column_names)
            self.assertIn("ndvi_mean_5x5", table.column_names)
            self.assertEqual(len(set(table.column("grid_id").to_pylist())), table.num_rows)
            self.assertTrue(all(name.startswith(("PMC:", "PCMC:")) for name in table.column("ward_id").to_pylist()))
            self.assertTrue(metadata.is_file())
            self.assertTrue(output.with_name("greenpulse_ml_grid_sample.csv").is_file())
            self.assertTrue(output.with_name("greenpulse_ml_correlations.png").is_file())
            self.assertTrue(report["severe_pairwise_correlations_abs_r_ge_0_85"])

    def test_misaligned_source_is_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ward_path, transform, _, morphology = _fixture(root)
            path = morphology / "built_pct_pune_30m.tif"
            with rasterio.open(path) as source:
                values = source.read(1)
            _write_raster(path, values, transform, shift_x=30)
            output = root / "data" / "processed" / "greenpulse_ml_grid.parquet"
            with self.assertRaisesRegex(ValueError, "built_pct differs"):
                build_ml_dataset(root, ward_path, output, root / "data" / "processed" / "metadata.json")
            self.assertFalse(output.exists())

    def test_impossible_range_and_missing_ward_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ward_path, transform, _, morphology = _fixture(root)
            built = morphology / "built_pct_pune_30m.tif"
            with rasterio.open(built) as source:
                values = source.read(1)
            values[2, 2] = 105
            _write_raster(built, values, transform)
            output = root / "data" / "processed" / "greenpulse_ml_grid.parquet"
            with self.assertRaisesRegex(ValueError, "built_pct contains values outside"):
                build_ml_dataset(root, ward_path, output, root / "data" / "processed" / "metadata.json")
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "missing"):
                load_wards(root / "data" / "boundaries" / "absent.geojson")


if __name__ == "__main__":
    unittest.main()
