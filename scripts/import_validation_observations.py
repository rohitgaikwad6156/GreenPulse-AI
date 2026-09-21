"""Import provenance-complete intervention LST observations into GreenPulse."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.validation.workflow import ValidationEvidenceError, import_validation_dataset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True,
                        help="Verified CSV or Parquet grid containing grid_id, x, y")
    parser.add_argument("--output-root", type=Path,
                        default=ROOT / "data" / "validation" / "imported")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="Tests only: permit an explicitly labelled synthetic fixture")
    args = parser.parse_args()
    try:
        destination = import_validation_dataset(
            args.manifest, args.observations, args.grid, args.output_root,
            allow_synthetic=args.allow_synthetic)
    except ValidationEvidenceError as exc:
        parser.exit(2, f"Validation import stopped: {exc}\n")
    print(f"Imported validated observations: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
