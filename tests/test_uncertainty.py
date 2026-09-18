"""Uncertainty tests use ARTIFICIAL TEST FIXTURES, not Pune results."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from backend.app.ml.uncertainty import (
    UncertaintyUnavailableError, add_uncertainty_to_scenario,
    estimate_cooling_uncertainty, load_uncertainty_assumptions,
    spatial_cv_rmse_from_metadata,
)


class UncertaintyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_uncertainty_assumptions()

    def test_config_values_are_visible_and_labelled(self):
        self.assertEqual(self.config["intervention_cv"], {
            "cool_roof": 0.08, "tree_canopy": 0.20,
            "green_roof": 0.15, "cool_pavement": 0.10})
        self.assertEqual(self.config["normal_multiplier_for_approx_90_percent"], 1.645)
        self.assertIn("NOT EMPIRICALLY CALIBRATED", self.config["label"])

    def test_exact_formula_for_artificial_tree_fixture(self):
        # ARTIFICIAL TEST FIXTURE: these are arithmetic checks, not Pune measurements.
        result = estimate_cooling_uncertainty(1.5, 0.4, ("tree_canopy",), self.config)
        self.assertAlmostEqual(result["sigma_param_c"], 0.3)
        self.assertAlmostEqual(result["sigma_total_c"], 0.5)
        self.assertAlmostEqual(result["lower_bound_c"], 1.5 - 1.645 * 0.5)
        self.assertAlmostEqual(result["upper_bound_c"], 1.5 + 1.645 * 0.5)
        self.assertEqual(result["confidence_category"], "Medium")
        self.assertIn("canopy cover has been established", result["prediction_horizon"])

    def test_zero_clamp_and_confidence_threshold_edges(self):
        result = estimate_cooling_uncertainty(0.0, 0.4, ("cool_roof",), self.config)
        self.assertEqual(result["lower_bound_c"], 0.0)
        self.assertAlmostEqual(result["upper_bound_c"], 1.645 * 0.4)
        for sigma, expected in ((0.2999, "High"), (0.3, "Medium"),
                                (0.6, "Medium"), (0.6001, "Low")):
            self.assertEqual(estimate_cooling_uncertainty(
                0, sigma, ("cool_roof",), self.config)["confidence_category"], expected)

    def test_combined_cv_uses_documented_quadrature(self):
        result = estimate_cooling_uncertainty(2.0, 0.4,
                                              ("tree_canopy", "cool_roof"), self.config)
        expected_cv = math.hypot(0.20, 0.08)
        self.assertAlmostEqual(result["assumptions"]["effective_intervention_cv"], expected_cv)
        self.assertAlmostEqual(result["sigma_param_c"], 2 * expected_cv)
        self.assertIn("no calendar-year claim", result["prediction_horizon"])
        self.assertEqual(result["assumptions"]["combined_cv_rule"],
                         "root_sum_squares_of_selected_cvs")

    def test_invalid_values_and_config_stop(self):
        for cooling, rmse, interventions in ((-1, 0.5, ("tree_canopy",)),
                                              (float("nan"), 0.5, ("tree_canopy",)),
                                              (1, -0.5, ("tree_canopy",)),
                                              (1, 0.5, ("unknown",)),
                                              (1, 0.5, ("tree_canopy", "tree_canopy"))):
            with self.assertRaises(ValueError):
                estimate_cooling_uncertainty(cooling, rmse, interventions, self.config)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "uncertainty.json"
            path.write_text(json.dumps({**self.config, "intervention_cv": {"tree_canopy": -0.2}}))
            with self.assertRaises(UncertaintyUnavailableError):
                load_uncertainty_assumptions(path)

    def test_saved_spatial_rmse_and_dataset_version_required(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model_metadata.json"
            metadata = {
                "target": "lst_c", "objective": "reg:squarederror",
                "dataset_version": "sha256:ARTIFICIAL-TEST-FIXTURE",
                "outer_folds": 5, "spatial_validation_method": "Saved 5 km spatial block CV",
                "spatial_cv_metrics": {"rmse_c": {"mean": 0.4, "std": 0.1}},
            }
            path.write_text(json.dumps(metadata))
            self.assertEqual(spatial_cv_rmse_from_metadata(path)[0], 0.4)
            scenario = {"cooling_magnitude_c": 1.5,
                        "model_dataset_version": "sha256:ARTIFICIAL-TEST-FIXTURE"}
            result = add_uncertainty_to_scenario(scenario, path, ("tree_canopy",))
            self.assertIn("uncertainty", result)
            self.assertNotIn("uncertainty", scenario)
            self.assertEqual(result["uncertainty"]["sigma_model_c"], 0.4)
            with self.assertRaisesRegex(UncertaintyUnavailableError, "different"):
                add_uncertainty_to_scenario({**scenario, "model_dataset_version": "sha256:OTHER"},
                                            path, ("tree_canopy",))
            metadata["spatial_cv_metrics"] = {}
            path.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(UncertaintyUnavailableError, "spatial-CV RMSE"):
                add_uncertainty_to_scenario(scenario, path, ("tree_canopy",))


if __name__ == "__main__":
    unittest.main()
