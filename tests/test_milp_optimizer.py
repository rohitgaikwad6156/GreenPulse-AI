"""MILP tests use ARTIFICIAL / SYNTHETIC planning fixtures only."""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app.main import ClimatePlanRequest, climate_action_plan
from backend.app.optimizer.milp_optimizer import (
    OptimizerDataUnavailableError, optimize_actions, optimize_catalog,
)


ROOT = Path(__file__).resolve().parents[1]


def artificial_actions():
    return [
        {"catalog_label": "ARTIFICIAL / SYNTHETIC TEST FIXTURE", "location": "ARTIFICIAL TEST AREA", "intervention_id": "tree",
         "name": "Test tree", "unit_type": "tree", "block_size": 1,
         "capital_cost_inr": 100, "annual_maintenance_inr": 10,
         "ground_area_required_m2": 5, "roof_area_required_m2": 0,
         "predicted_cooling_benefit_c": 0.2, "green_cover_gain_m2": 5,
         "co_benefit_score_0_5": 4, "maximum_feasible_units": 3},
        {"catalog_label": "ARTIFICIAL / SYNTHETIC TEST FIXTURE", "location": "ARTIFICIAL TEST AREA", "intervention_id": "roof",
         "name": "Test roof", "unit_type": "m2", "block_size": 50,
         "capital_cost_inr": 150, "annual_maintenance_inr": 5,
         "ground_area_required_m2": 0, "roof_area_required_m2": 50,
         "predicted_cooling_benefit_c": 0.3, "green_cover_gain_m2": 0,
         "co_benefit_score_0_5": 2, "maximum_feasible_units": 2},
    ]


class MilpOptimizerTests(unittest.TestCase):
    def test_optimum_obeys_every_constraint_and_integer_capacity(self):
        plan = optimize_actions(
            artificial_actions(), budget_inr=250, maintenance_cap_inr_per_year=15,
            available_ground_m2=10, available_roof_m2=50, location="ARTIFICIAL TEST AREA")
        counts = {action["intervention_id"]: action["quantity"] for action in plan["selected_actions"]}
        self.assertEqual(counts, {"tree": 1, "roof": 1})
        self.assertTrue(all(isinstance(q, int) and q >= 0 for q in counts.values()))
        self.assertLessEqual(plan["capital_cost_inr"], 250)
        self.assertLessEqual(plan["annual_maintenance_inr"], 15)
        self.assertLessEqual(plan["ground_used_m2"], 10)
        self.assertLessEqual(plan["roof_used_m2"], 50)
        self.assertEqual(plan["unused_budget_inr"], 0)
        self.assertAlmostEqual(plan["objective_value"], 2.2866666666666666)
        self.assertAlmostEqual(plan["modeled_cooling_estimate_c"], 0.5)
        self.assertEqual(plan["interpretation"],
                         "Optimal under the modeled objective, assumptions and constraints.")

    def test_lakh_conversion_and_empty_portfolio(self):
        plan = optimize_actions(
            artificial_actions(), budget_inr=1_000_000, maintenance_cap_inr_per_year=0,
            available_ground_m2=0, available_roof_m2=0, location="ARTIFICIAL TEST AREA")
        self.assertEqual(plan["selected_actions"], [])
        self.assertEqual(plan["unused_budget_inr"], 1_000_000)

    def test_policy_priorities_and_portfolio_detail(self):
        actions = artificial_actions()
        actions[0]["time_horizon"] = "ARTIFICIAL TEST HORIZON"
        limits = dict(budget_inr=150, maintenance_cap_inr_per_year=15,
                      available_ground_m2=10, available_roof_m2=50,
                      location="ARTIFICIAL TEST AREA")
        cooling = optimize_actions(actions, **limits, priority_weights={
            "cooling": 1, "green_cover": 0, "co_benefit": 0})
        greening = optimize_actions(actions, **limits, priority_weights={
            "cooling": 0, "green_cover": 1, "co_benefit": 0})
        self.assertEqual(cooling["selected_actions"][0]["intervention_id"], "roof")
        self.assertEqual(greening["selected_actions"][0]["intervention_id"], "tree")
        self.assertEqual(greening["selected_actions"][0]["green_cover_gain_m2"], 5)
        self.assertEqual(greening["selected_actions"][0]["time_horizon"], "ARTIFICIAL TEST HORIZON")

    def test_catalog_with_missing_cooling_or_capacity_is_unavailable(self):
        path = ROOT / "data" / "processed" / "interventions.csv"
        with self.assertRaisesRegex(OptimizerDataUnavailableError, "predicted_cooling_benefit_c"):
            optimize_catalog(path, budget_inr=1_000_000,
                             maintenance_cap_inr_per_year=100_000,
                             available_ground_m2=1000, available_roof_m2=1000,
                             location="Pune/PCMC pending verified ward")
        actions = artificial_actions()
        actions[0]["maximum_feasible_units"] = ""
        with self.assertRaisesRegex(OptimizerDataUnavailableError, "maximum_feasible_units"):
            optimize_actions(actions, budget_inr=1000, maintenance_cap_inr_per_year=1000,
                             available_ground_m2=100, available_roof_m2=100,
                             location="ARTIFICIAL TEST AREA")

    def test_bad_values_and_config_are_rejected(self):
        actions = artificial_actions()
        actions[0]["maximum_feasible_units"] = 0.37
        with self.assertRaisesRegex(ValueError, "integer"):
            optimize_actions(actions, budget_inr=1000, maintenance_cap_inr_per_year=1000,
                             available_ground_m2=100, available_roof_m2=100,
                             location="ARTIFICIAL TEST AREA")
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "objective.json"
            config.write_text(json.dumps({"weights": {"cooling": 1, "green_cover": 0.5,
                                                    "co_benefit": 0.2},
                                          "normalization": {"cooling_reference_method":
                                              "maximum_positive_per_block_in_candidate_catalog",
                                              "green_reference_method":
                                              "maximum_positive_per_block_in_candidate_catalog",
                                              "co_benefit_reference": 0}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "positive"):
                optimize_actions(artificial_actions(), budget_inr=1000,
                                 maintenance_cap_inr_per_year=1000,
                                 available_ground_m2=100, available_roof_m2=100,
                                 location="ARTIFICIAL TEST AREA", config_path=config)

    def test_location_must_match_candidate_actions(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            optimize_actions(artificial_actions(), budget_inr=1000,
                             maintenance_cap_inr_per_year=1000,
                             available_ground_m2=100, available_roof_m2=100,
                             location="DIFFERENT ARTIFICIAL AREA")

    def test_api_reports_unavailable_catalog_instead_of_fabricated_plan(self):
        request = ClimatePlanRequest(
            location_id="PMC/PCMC ward pending verification", budget_inr=1_000_000,
            maintenance_cap_inr_per_year=100_000)
        with self.assertRaises(HTTPException) as context:
            climate_action_plan(request)
        self.assertEqual(context.exception.status_code, 503)
        self.assertIn("No evidence-complete", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
