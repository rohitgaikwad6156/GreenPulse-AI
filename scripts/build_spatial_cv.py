"""Create real-data 5 km block folds and a QA map; train no model."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.ml.spatial_cv import build_cv_artifacts  # noqa: E402


def main() -> int:
    """Validate the ML table and write block-only fold infrastructure."""
    parser = argparse.ArgumentParser(description="Build 5-fold GreenPulse spatial block CV infrastructure")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "processed" / "greenpulse_ml_grid.parquet")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--block-size-m", type=float, default=5000)
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args()
    try:
        report = build_cv_artifacts(args.dataset, args.output_dir, args.block_size_m, args.folds)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Spatial CV build stopped: {exc}\n")
    print(f"Source rows: {report['row_count']}")
    print(f"Spatial blocks: {report['unique_blocks']}")
    for fold in report["fold_summary"]:
        print(f"Fold {fold['fold']}: {fold['validation_blocks']} held-out blocks, {fold['validation_rows']} validation rows")
    print(f"Block map: {args.output_dir / 'spatial_cv_folds.png'}")
    print(f"Block mapping: {args.output_dir / 'spatial_cv_blocks.parquet'}")
    print(f"QA metadata: {args.output_dir / 'spatial_cv_metadata.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
