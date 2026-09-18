"""Train GreenPulse's main XGBoost LST model with nested spatial CV."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ml.xgboost_lst import train_xgboost_lst  # noqa: E402


def main() -> int:
    """Tune on spatial blocks, evaluate outer folds, persist final model."""
    parser = argparse.ArgumentParser(description="GreenPulse XGBoost LST regression with nested spatial CV")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "processed" / "greenpulse_ml_grid.parquet")
    parser.add_argument("--cv-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--baseline-metrics", type=Path, default=ROOT / "models" / "baseline_metrics.json")
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "xgboost_lst.joblib")
    parser.add_argument("--metadata", type=Path, default=ROOT / "models" / "model_metadata.json")
    parser.add_argument("--trials", type=int, default=8, help="Optuna trials for each outer fold and final full-data tuning")
    parser.add_argument("--inner-folds", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    try:
        report = train_xgboost_lst(args.dataset, args.cv_dir, args.baseline_metrics,
                                   args.model, args.metadata, args.trials,
                                   args.inner_folds, args.jobs)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"XGBoost LST training stopped: {exc}\n")
    print("XGBoost held-out spatial CV, mean ± sample standard deviation across five outer folds:")
    for metric, units in (("mae_c", "°C"), ("rmse_c", "°C"), ("r2", "")):
        scores = report["spatial_cv_metrics"][metric]
        print(f"{metric.upper()}: {scores['mean']:.3f} ± {scores['std']:.3f} {units}".rstrip())
    print(f"Final model: {args.model}")
    print(f"Model metadata: {args.metadata}")
    print(f"Baseline comparison plot: {args.model.with_name('xgboost_baseline_comparison.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
