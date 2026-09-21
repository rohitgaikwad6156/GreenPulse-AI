"""Validate the versioned, location-specific optimizer evidence catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.optimizer.location_catalog import CatalogEvidenceError, list_planning_locations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path,
                        default=ROOT / "data" / "interventions" / "location_catalog.json")
    args = parser.parse_args()
    try:
        report = list_planning_locations(args.catalog, project_root=ROOT)
    except CatalogEvidenceError as exc:
        parser.exit(2, f"Intervention catalog invalid: {exc}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["total"] == 0:
        print("No evidence-complete planning location is available.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
