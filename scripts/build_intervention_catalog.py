"""Generate the explicitly labelled demo-cost intervention catalog CSV."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.optimizer.catalog import build_intervention_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GreenPulse intervention catalog with demo costs")
    parser.add_argument("--assumptions", type=Path,
                        default=ROOT / "data" / "demo" / "intervention_catalog_assumptions.json")
    parser.add_argument("--uncertainty-config", type=Path,
                        default=ROOT / "backend" / "app" / "ml" / "uncertainty_assumptions.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data" / "processed" / "interventions.csv")
    args = parser.parse_args()
    try:
        rows = build_intervention_catalog(args.assumptions, args.uncertainty_config, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Intervention catalog stopped: {exc}\n")
    print("DEMO / SYNTHETIC DATA — DEMO COST ASSUMPTIONS")
    print(f"Saved {len(rows)} discrete intervention types: {args.output}")
    print("Cooling benefits and site-specific maximum units remain unestimated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
