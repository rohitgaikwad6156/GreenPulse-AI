"""Import verified air-temperature, humidity, and AQI point observations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.research.sensors import SensorEvidenceError, import_sensor_observations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data" / "research" / "sensors")
    args = parser.parse_args()
    try:
        destination = import_sensor_observations(args.manifest, args.observations, args.output_root)
    except SensorEvidenceError as exc:
        parser.exit(2, f"Point-sensor import stopped: {exc}\n")
    print(f"Imported verified point observations: {destination}")
    print("No raster interpolation or LST-model update was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
