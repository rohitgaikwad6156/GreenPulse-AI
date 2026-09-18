"""Validation tests use only the bundled DEMO / SYNTHETIC scenario."""

import copy
import math
import unittest

from backend.app.schemas.api import DidRequest
from backend.app.validation.did import calculate_did, load_demo_scenario


class ValidationDidTests(unittest.TestCase):
    def setUp(self):
        self.demo = load_demo_scenario()

    def test_demo_is_explicitly_labelled_and_arithmetic_is_consistent(self):
        self.assertEqual(self.demo["scenario_label"], "DEMO VALIDATION SCENARIO")
        self.assertIn("DEMO / SYNTHETIC DATA", self.demo["source_note"])
        report = calculate_did(DidRequest.model_validate(self.demo))
        self.assertEqual(report["label"], "DEMO VALIDATION SCENARIO")
        self.assertAlmostEqual(report["treated_change_c"], -2.75)
        self.assertAlmostEqual(report["control_change_c"], -0.5)
        self.assertAlmostEqual(report["difference_in_differences_c"], -2.25)
        self.assertAlmostEqual(report["realized_cooling_c"], 2.25)
        self.assertAlmostEqual(report["ndvi_changes"]["treated"], 0.09)
        self.assertAlmostEqual(report["ndvi_changes"]["control"], 0.01)
        self.assertAlmostEqual(report["performance"]["mae_c"], 0.4)
        self.assertAlmostEqual(report["performance"]["rmse_c"], math.sqrt(0.17))
        self.assertEqual(report["performance"]["count_treated_cells"], 2)
        self.assertAlmostEqual(
            sum(row["actual_control_adjusted_delta_lst_c"] for row in report["prediction_comparison"]) / 2,
            report["difference_in_differences_c"])

    def test_predictions_and_ndvi_are_optional_but_never_partially_filled(self):
        scenario = copy.deepcopy(self.demo)
        scenario["predictions"] = []
        for row in scenario["observations"]:
            row["ndvi"] = None
        report = calculate_did(DidRequest.model_validate(scenario))
        self.assertIsNone(report["performance"])
        self.assertIsNone(report["ndvi_changes"])
        self.assertEqual(report["prediction_comparison"], [])
        scenario["observations"][0]["ndvi"] = 0.12
        with self.assertRaisesRegex(ValueError, "every pre and post"):
            calculate_did(DidRequest.model_validate(scenario))

    def test_rejects_unpaired_or_mismatched_cells_and_predictions(self):
        scenario = copy.deepcopy(self.demo)
        scenario["predictions"].pop()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            calculate_did(DidRequest.model_validate(scenario))
        scenario = copy.deepcopy(self.demo)
        scenario["observations"].pop()
        with self.assertRaisesRegex(ValueError, "both pre and post"):
            calculate_did(DidRequest.model_validate(scenario))
        scenario = copy.deepcopy(self.demo)
        scenario["observations"][0]["group"] = "control"
        with self.assertRaisesRegex(ValueError, "both treated and control"):
            calculate_did(DidRequest.model_validate(scenario))


if __name__ == "__main__":
    unittest.main()
