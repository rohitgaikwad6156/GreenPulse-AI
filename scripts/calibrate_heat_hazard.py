"""Calibrate Heat Hazard Score references only from documented observed LST."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ml.heat_hazard import derive_heat_hazard_references  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive observed-LST Heat Hazard Score references")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "processed" / "greenpulse_ml_grid.parquet")
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "xgboost_lst.joblib")
    parser.add_argument("--model-metadata", type=Path, default=ROOT / "models" / "model_metadata.json")
    parser.add_argument("--periurban", type=Path, default=ROOT / "data" / "processed" / "periurban_lst_reference.parquet")
    parser.add_argument("--periurban-provenance", type=Path,
                        default=ROOT / "data" / "processed" / "periurban_lst_reference_metadata.json")
    args = parser.parse_args()
    try:
        reference = derive_heat_hazard_references(
            args.dataset, args.model, args.model_metadata, args.periurban,
            args.periurban_provenance)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Heat Hazard Score calibration stopped: {exc}\n")
    print(f"Background observed LST (peri-urban median): {reference['background_lst_c']:.3f} °C")
    print(f"Hot observed LST reference (municipal 95th percentile): {reference['hot_reference_lst_c']:.3f} °C")
    print(f"Reference period: {reference['reference_date_range']}")
    print(f"Updated model metadata: {args.model_metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
