"""Evidence-gate tests use only explicitly labelled artificial fixtures."""

import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backend.app.optimizer.location_catalog import (
    CatalogEvidenceError, actions_for_location, list_planning_locations,
    load_location_catalog,
)
from backend.app.optimizer.milp_optimizer import optimize_location_catalog


def write_fixture(root: Path) -> tuple[Path, dict]:
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    sources = []
    for source_id, evidence_type in (
        ("ARTIFICIAL-COST", "audited_user_input"),
        ("ARTIFICIAL-CAPACITY", "verified_spatial_capacity"),
        ("ARTIFICIAL-MODEL", "validated_model"),
    ):
        relative = f"evidence/{source_id}.txt"
        payload = f"ARTIFICIAL / SYNTHETIC TEST FIXTURE: {source_id}\n".encode()
        (root / relative).write_bytes(payload)
        sources.append({
            "source_id": source_id, "organization": "Artificial test organization",
            "title": "Artificial test evidence", "url_or_identifier": "test://fixture",
            "license": "TEST ONLY", "access_date": "2026-01-01",
            "valid_until": "2027-12-31", "evidence_type": evidence_type,
            "checksum_sha256": hashlib.sha256(payload).hexdigest(), "local_path": relative,
        })
    model_hash = sources[2]["checksum_sha256"]
    action = {
        "availability": "available", "location_id": "ARTIFICIAL-AREA",
        "intervention_id": "street_trees", "name": "Artificial trees",
        "unit_type": "tree", "block_size": 1, "capital_cost_inr": 100,
        "annual_maintenance_inr": 10, "ground_area_required_m2": 5,
        "roof_area_required_m2": 0, "maximum_feasible_units": 2,
        "modeled_marginal_cooling_c": 0.2, "green_cover_gain_m2": 5,
        "co_benefit_score_0_5": 2, "horizon": "Artificial test horizon",
        "uncertainty": {"status": "uncalibrated_proxy", "description": "Artificial test uncertainty"},
        "source_ids": ["ARTIFICIAL-COST", "ARTIFICIAL-CAPACITY", "ARTIFICIAL-MODEL"],
        "field_source_ids": {
            "capital_cost": ["ARTIFICIAL-COST"],
            "annual_maintenance": ["ARTIFICIAL-COST"],
            "block_and_area": ["ARTIFICIAL-CAPACITY"],
            "maximum_feasible_units": ["ARTIFICIAL-CAPACITY"],
            "modeled_marginal_cooling": ["ARTIFICIAL-MODEL"],
            "green_cover_gain": ["ARTIFICIAL-CAPACITY"],
            "co_benefit": ["ARTIFICIAL-COST"],
            "horizon": ["ARTIFICIAL-MODEL"],
            "uncertainty": ["ARTIFICIAL-MODEL"]
        },
        "evidence_status": "audited", "model_dataset_version": "ARTIFICIAL-MODEL-V1",
        "model_checksum_sha256": model_hash,
    }
    document = {
        "schema_version": "1.0", "catalog_version": "ARTIFICIAL-CATALOG-V1",
        "generated_at": "2026-01-02T00:00:00+00:00",
        "model_dataset_version": "ARTIFICIAL-MODEL-V1",
        "model_checksum_sha256": model_hash, "sources": sources,
        "locations": [{
            "location_id": "ARTIFICIAL-AREA", "name": "Artificial planning area",
            "crs": "EPSG:32643", "capacity_source_ids": ["ARTIFICIAL-CAPACITY"],
            "capacity": {"status": "verified_spatial_inputs", "eligible_ground_m2": 10,
                         "eligible_roof_m2": 0},
            "actions": [action, {"availability": "unavailable", "intervention_id": "cool_roofs",
                                  "unavailable_reason": "No artificial roof capacity"}],
        }], "blockers": [],
    }
    catalog = root / "catalog.json"
    catalog.write_text(json.dumps(document), encoding="utf-8")
    return catalog, document


class LocationInterventionCatalogTests(unittest.TestCase):
    def test_complete_catalog_lists_location_and_solver_uses_verified_capacity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog, _ = write_fixture(root)
            result = list_planning_locations(catalog, project_root=root)
            self.assertEqual(result["locations"][0]["location_id"], "ARTIFICIAL-AREA")
            plan = optimize_location_catalog(
                catalog, location_id="ARTIFICIAL-AREA", budget_inr=1000,
                maintenance_cap_inr_per_year=1000, project_root=root)
            self.assertEqual(plan["selected_actions"][0]["quantity"], 2)
            self.assertEqual(plan["verified_capacity"]["eligible_ground_m2"], 10)
            self.assertIn("overlap", plan["interaction_warning"])
            self.assertEqual(plan["catalog_version"], "ARTIFICIAL-CATALOG-V1")

    def test_mixed_location_and_stale_model_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog, document = write_fixture(root)
            for field, value, message in (
                ("location_id", "OTHER-AREA", "mixed-location"),
                ("model_dataset_version", "STALE", "stale or mismatched"),
            ):
                changed = copy.deepcopy(document)
                changed["locations"][0]["actions"][0][field] = value
                catalog.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(CatalogEvidenceError, message):
                    load_location_catalog(catalog, project_root=root, today=date(2026, 9, 21))

    def test_expired_or_tampered_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog, document = write_fixture(root)
            changed = copy.deepcopy(document)
            changed["sources"][0]["valid_until"] = "2025-12-31"
            catalog.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(CatalogEvidenceError, "expired"):
                load_location_catalog(catalog, project_root=root, today=date(2026, 9, 21))
            catalog, _ = write_fixture(root)
            (root / "evidence" / "ARTIFICIAL-COST.txt").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(CatalogEvidenceError, "checksum"):
                actions_for_location(catalog, "ARTIFICIAL-AREA", project_root=root)

    def test_missing_cost_or_capacity_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog, document = write_fixture(root)
            for source_ids, mapped_source, mapped_fields, message in (
                (["ARTIFICIAL-CAPACITY", "ARTIFICIAL-MODEL"], "ARTIFICIAL-CAPACITY",
                 ("capital_cost", "annual_maintenance"), "cost evidence"),
                (["ARTIFICIAL-COST", "ARTIFICIAL-MODEL"], "ARTIFICIAL-MODEL",
                 ("block_and_area", "maximum_feasible_units"), "spatial-capacity"),
            ):
                changed = copy.deepcopy(document)
                changed["locations"][0]["actions"][0]["source_ids"] = source_ids
                for key, identifiers in changed["locations"][0]["actions"][0]["field_source_ids"].items():
                    changed["locations"][0]["actions"][0]["field_source_ids"][key] = [
                        item for item in identifiers if item in source_ids]
                    if not changed["locations"][0]["actions"][0]["field_source_ids"][key]:
                        changed["locations"][0]["actions"][0]["field_source_ids"][key] = [mapped_source]
                for key in mapped_fields:
                    changed["locations"][0]["actions"][0]["field_source_ids"][key] = [mapped_source]
                catalog.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaisesRegex(CatalogEvidenceError, message):
                    load_location_catalog(catalog, project_root=root, today=date(2026, 9, 21))


if __name__ == "__main__":
    unittest.main()
