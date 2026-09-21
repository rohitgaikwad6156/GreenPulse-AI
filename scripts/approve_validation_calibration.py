"""Record a human calibration decision without modifying production assumptions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.validation.workflow import ValidationEvidenceError, approve_calibration_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id")
    parser.add_argument("--decision", choices=("approve", "reject"), required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--rationale", required=True)
    args = parser.parse_args()
    report = ROOT / "data" / "validation" / "reports" / f"{args.dataset_id}.json"
    approval = ROOT / "data" / "validation" / "approvals" / f"{args.dataset_id}.json"
    try:
        record = approve_calibration_report(
            report, approval, approver=args.approver,
            decision=args.decision, rationale=args.rationale)
    except ValidationEvidenceError as exc:
        parser.exit(2, f"Calibration approval stopped: {exc}\n")
    print(f"Recorded {record['decision']} decision: {approval}")
    print("Production assumptions were not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
