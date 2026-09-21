"""Validate the authoritative GreenPulse real-data manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.data_intake.manifest import validate_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate GreenPulse source files, metadata, dates, CRS, checksums, and provenance")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "source_manifest.json")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    parser.add_argument("--allow-synthetic", action="store_true", help="tests only: permit explicitly labelled synthetic fixtures")
    args = parser.parse_args()
    report = validate_manifest(args.manifest, args.root, allow_synthetic=args.allow_synthetic)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print("PASS: data intake manifest is ready for processing" if report.ok else "FAIL: data intake manifest is not ready")
        if report.verified_sources:
            print("Verified: " + ", ".join(report.verified_sources))
        for item in report.errors:
            print(f"ERROR: {item}")
        for item in report.warnings:
            print(f"WARNING: {item}")
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
