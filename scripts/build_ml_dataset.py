"""Assemble the real GreenPulse 30 m ML table; no model training."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.geospatial.ml_dataset import build_ml_dataset  # noqa: E402


def main() -> int:
    """Validate aligned inputs and write Parquet plus provenance/QC outputs."""
    parser = argparse.ArgumentParser(description="Build GreenPulse real-data 30 m ML grid without training")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--wards", type=Path, default=ROOT / "data" / "boundaries" / "pmc_pcmc_wards.geojson")
    parser.add_argument("--albedo", type=Path, help="Optional documented, QA-masked 30 m albedo GeoTIFF")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "greenpulse_ml_grid.parquet")
    parser.add_argument("--metadata", type=Path, default=ROOT / "data" / "processed" / "metadata.json")
    parser.add_argument("--csv-sample-rows", type=int, default=200)
    args = parser.parse_args()
    try:
        report = build_ml_dataset(args.root, args.wards, args.output, args.metadata,
                                  args.albedo, args.csv_sample_rows)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"GreenPulse ML dataset build stopped: {exc}\n")
    print(f"Saved Parquet: {args.output}")
    print(f"Saved metadata: {args.metadata}")
    print(f"Complete 30 m cells: {report['row_count']}")
    print(f"Date range: {report['date_range']}")
    print(f"Severe pairwise feature correlations: {len(report['severe_pairwise_correlations_abs_r_ge_0_85'])}")
    print(f"Features with VIF > 5: {len(report['severe_vif_gt_5'])}")
    print(f"Correlation plot: {args.output.with_name('greenpulse_ml_correlations.png')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
