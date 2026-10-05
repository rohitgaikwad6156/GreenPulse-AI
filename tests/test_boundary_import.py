"""Boundary importer tests use explicitly synthetic temporary polygons only."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.acquire_real_sources import _validate_download
from scripts.import_municipal_boundaries import import_boundaries
from scripts.import_municipal_outlines import import_outlines


def _geojson(offset: float, id_key="number", name_key="label"):
    return {"type": "FeatureCollection", "features": [{"type": "Feature",
        "properties": {id_key: "TEST-1", name_key: "SYNTHETIC TEST WARD"},
        "geometry": {"type": "Polygon", "coordinates": [[[73.7 + offset, 18.5],
        [73.71 + offset, 18.5], [73.71 + offset, 18.51], [73.7 + offset, 18.51],
        [73.7 + offset, 18.5]]]}}]}


class BoundaryImportTests(unittest.TestCase):
    def test_imports_municipal_outlines_without_ward_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pmc, pcmc, provenance = root / "pmc.geojson", root / "pcmc.geojson", root / "provenance.json"
            for path, offset in ((pmc, 0), (pcmc, .1)):
                document = _geojson(offset)
                document["features"][0]["properties"] = {}
                path.write_text(json.dumps(document), encoding="utf-8")
            provenance.write_text(json.dumps({name: {"source_organization": f"SYNTHETIC TEST {name}",
                "source_url": "https://example.invalid/test", "dataset_identifier": "TEST-ONLY",
                "license": "TEST-ONLY", "effective_date": "2025-01-01"} for name in ("PMC", "PCMC")}), encoding="utf-8")
            result = import_outlines(pmc, pcmc, provenance, output_dir=root / "out")
            features = json.loads(result["boundary"].read_text(encoding="utf-8"))["features"]
            self.assertEqual({f["properties"]["municipality"] for f in features}, {"PMC", "PCMC"})
            self.assertTrue(all("ward_id" not in f["properties"] for f in features))
            self.assertFalse((root / "out" / "pmc_pcmc_wards.geojson").exists())

    def test_imports_labelled_authority_inputs_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pmc, pcmc, provenance = root / "pmc.geojson", root / "pcmc.geojson", root / "provenance.json"
            pmc.write_text(json.dumps(_geojson(0)), encoding="utf-8")
            pcmc.write_text(json.dumps(_geojson(.1)), encoding="utf-8")
            provenance.write_text(json.dumps({name: {"source_organization": f"SYNTHETIC TEST {name}",
                "source_url": "https://example.invalid/test", "dataset_identifier": "TEST-ONLY",
                "license": "TEST-ONLY", "effective_date": "2025-01-01"} for name in ("PMC", "PCMC")}), encoding="utf-8")
            first = import_boundaries(pmc, pcmc, provenance, pmc_id="number", pmc_name="label",
                                      pcmc_id="number", pcmc_name="label", output_dir=root / "out")
            initial = first["wards"].read_bytes()
            second = import_boundaries(pmc, pcmc, provenance, pmc_id="number", pmc_name="label",
                                       pcmc_id="number", pcmc_name="label", output_dir=root / "out")
            self.assertEqual(initial, second["wards"].read_bytes())
            features = json.loads(initial)["features"]
            self.assertEqual({f["properties"]["municipality"] for f in features}, {"PMC", "PCMC"})

    def test_rejects_pdf_and_missing_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / "ward-map.pdf"
            pdf.write_bytes(b"%PDF SYNTHETIC TEST")
            geo = root / "pcmc.geojson"
            geo.write_text(json.dumps(_geojson(.1)), encoding="utf-8")
            provenance = root / "provenance.json"
            provenance.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provenance must contain"):
                import_boundaries(pdf, geo, provenance, pmc_id="number", pmc_name="label",
                                  pcmc_id="number", pcmc_name="label", output_dir=root / "out")
            complete = {name: {"source_organization": "SYNTHETIC TEST", "source_url": "https://example.invalid",
                "dataset_identifier": "TEST", "license": "TEST", "effective_date": "2025-01-01"}
                for name in ("PMC", "PCMC")}
            provenance.write_text(json.dumps(complete), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PDF/image"):
                import_boundaries(pdf, geo, provenance, pmc_id="number", pmc_name="label",
                                  pcmc_id="number", pcmc_name="label", output_dir=root / "out")

    def test_downloader_rejects_authentication_pages_and_non_tiffs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            html = root / "scene.TIF"
            html.write_text("<!doctype html><html><title>Login</title></html>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "authentication page"):
                _validate_download(html)
            bogus = root / "source.tif"
            bogus.write_bytes(b"SYNTHETIC TEST, NOT A TIFF")
            with self.assertRaisesRegex(ValueError, "not a GeoTIFF"):
                _validate_download(bogus)


if __name__ == "__main__":
    unittest.main()
