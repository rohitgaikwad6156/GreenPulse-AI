"""Build a versioned DiD validation and calibration-proposal report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.validation.workflow import ValidationEvidenceError, analyze_validation_dataset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id")
    args = parser.parse_args()
    dataset = ROOT / "data" / "validation" / "imported" / args.dataset_id
    report = ROOT / "data" / "validation" / "reports" / f"{args.dataset_id}.json"
    try:
        result = analyze_validation_dataset(dataset, output_path=report)
    except ValidationEvidenceError as exc:
        parser.exit(2, f"Validation analysis stopped: {exc}\n")
    print(f"Validation status: {result['validation_status']}")
    print(f"Report: {report}")
    return 0 if result["validation_status"] == "READY_FOR_HUMAN_REVIEW" else 3


if __name__ == "__main__":
    raise SystemExit(main())
