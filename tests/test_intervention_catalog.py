"""Catalog tests use DEMO / SYNTHETIC planning assumptions only."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.optimizer.catalog import CATALOG_COLUMNS, build_intervention_catalog


ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS = ROOT / "data" / "demo" / "intervention_catalog_assumptions.json"
UNCERTAINTY = ROOT / "backend" / "app" / "ml" / "uncertainty_assumptions.json"


class InterventionCatalogTests(unittest.TestCase):
    def test_six_discrete_actions_and_explicit_missing_predictions(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "interventions.csv"
            rows = build_intervention_catalog(ASSUMPTIONS, UNCERTAINTY, output)
            self.assertEqual(len(rows), 6)
            self.assertTrue(output.is_file())
            with output.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames), CATALOG_COLUMNS)
                saved = list(reader)
            self.assertEqual([row["name"] for row in saved], [
                "Street Trees", "Cool Roofs", "Green Roofs", "Shade Structures",
                "Green Corridors", "Reflective Pavements"])
            self.assertEqual([int(row["block_size"]) for row in saved], [1, 50, 25, 1, 25, 50])
            self.assertTrue(all("DEMO COST ASSUMPTIONS" in row["catalog_label"] for row in saved))
            self.assertTrue(all("DEMO COST ASSUMPTIONS" in row["cost_status"] for row in saved))
            self.assertTrue(all(row["predicted_cooling_benefit_c"] == "" for row in saved))
            self.assertTrue(all(row["maximum_feasible_units"] == "" for row in saved))
            self.assertTrue(all(row["maximum_feasible_units_rule"].startswith("floor(") for row in saved))
            self.assertTrue(all(float(row["capital_cost_inr"]) > 0 for row in saved))
            self.assertTrue(all(row["source_reference"] for row in saved))
            self.assertEqual(float(saved[0]["uncertainty_cv"]), 0.2)
            self.assertEqual(float(saved[1]["uncertainty_cv"]), 0.08)
            self.assertEqual(saved[3]["uncertainty_cv"], "")

    def test_costs_are_configurable_but_remain_demo_labelled(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config_path = directory / "assumptions.json"
            document = json.loads(ASSUMPTIONS.read_text(encoding="utf-8"))
            document["interventions"][0]["capital_cost_inr"] = 12000
            config_path.write_text(json.dumps(document), encoding="utf-8")
            output = directory / "catalog.csv"
            rows = build_intervention_catalog(config_path, UNCERTAINTY, output)
            self.assertEqual(rows[0]["capital_cost_inr"], 12000)
            self.assertIn("DEMO", rows[0]["catalog_label"])

    def test_unlabelled_costs_or_fabricated_benefit_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            config_path = directory / "assumptions.json"
            output = directory / "catalog.csv"
            document = json.loads(ASSUMPTIONS.read_text(encoding="utf-8"))
            document["catalog_label"] = "VERIFIED PUNE COSTS"
            config_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DEMO COST ASSUMPTIONS"):
                build_intervention_catalog(config_path, UNCERTAINTY, output)
            self.assertFalse(output.exists())
            document = json.loads(ASSUMPTIONS.read_text(encoding="utf-8"))
            document["interventions"][0]["predicted_cooling_benefit_c"] = 1.2
            config_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fabricated cooling"):
                build_intervention_catalog(config_path, UNCERTAINTY, output)
            self.assertFalse(output.exists())
            document = json.loads(ASSUMPTIONS.read_text(encoding="utf-8"))
            document["interventions"][1]["block_size"] = 0.37
            config_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "discrete block"):
                build_intervention_catalog(config_path, UNCERTAINTY, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
