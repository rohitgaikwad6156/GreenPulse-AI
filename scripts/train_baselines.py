"""Evaluate three fixed LST baselines on saved spatial folds."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ml.baselines import evaluate_baselines  # noqa: E402


def main() -> int:
    """Train/evaluate baselines when real Step 12–13 artifacts exist."""
    parser = argparse.ArgumentParser(description="GreenPulse spatially validated baseline LST regression")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "processed" / "greenpulse_ml_grid.parquet")
    parser.add_argument("--cv-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--output", type=Path, default=ROOT / "models" / "baseline_metrics.json")
    parser.add_argument("--rf-trees", type=int, default=100)
    parser.add_argument("--rf-jobs", type=int, default=2)
    args = parser.parse_args()
    try:
        report = evaluate_baselines(args.dataset, args.cv_dir, args.output, args.rf_trees, args.rf_jobs)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Baseline evaluation stopped: {exc}\n")
    print("Held-out 5 km spatial CV metrics, mean ± sample standard deviation across five folds:")
    for name, model in report["models"].items():
        summary = model["summary"]
        print(f"{name}: MAE {summary['mae_c']['mean']:.3f} ± {summary['mae_c']['std']:.3f} °C; "
              f"RMSE {summary['rmse_c']['mean']:.3f} ± {summary['rmse_c']['std']:.3f} °C; "
              f"R² {summary['r2']['mean']:.3f} ± {summary['r2']['std']:.3f}")
    print(f"Metrics JSON: {args.output}")
    print(f"Comparison plot: {args.output.with_name('baseline_comparison.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
