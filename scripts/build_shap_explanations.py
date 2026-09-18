"""Create global and selected-cell TreeSHAP outputs from the real saved LST model."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ml.shap_explain import explain_saved_model  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain GreenPulse XGBoost LST predictions with TreeSHAP")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "processed" / "greenpulse_ml_grid.parquet")
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "xgboost_lst.joblib")
    parser.add_argument("--metadata", type=Path, default=ROOT / "models" / "model_metadata.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--grid-id", required=True, help="Existing real grid_id to explain")
    parser.add_argument("--sample-size", type=int, default=2000)
    args = parser.parse_args()
    try:
        global_report, local_report = explain_saved_model(
            args.dataset, args.model, args.metadata, args.grid_id, args.output_dir, args.sample_size)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"TreeSHAP stopped: {exc}\n")
    print(f"Global TreeSHAP sample: {global_report['sample_rows']} of {global_report['dataset_rows']} grid cells")
    print(f"Selected grid cell: {local_report['grid_id']}")
    print(f"Baseline LST: {local_report['baseline_lST']:.3f} °C")
    print(f"Predicted LST: {local_report['predicted_lst']:.3f} °C")
    print(f"Saved JSON and plots to: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
