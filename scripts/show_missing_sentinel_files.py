"""Print a live checklist for manual Sentinel-2 SAFE placement; never download."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_sentinel_sources import (  # noqa: E402
    BANDS,
    SOURCE,
    backend_band_matches,
    band_candidates,
    load_selected_items,
    product_fields,
)


def checklist_lines(source: Path = SOURCE) -> list[str]:
    lines: list[str] = []
    for item in load_selected_items():
        product_id, acquisition_date, tile, errors = product_fields(item)
        safe = source / f"{product_id}.SAFE"
        lines += [f"Product: {product_id}", f"SAFE: {safe} ({'present' if safe.is_dir() else 'missing'})"]
        if errors:
            lines.extend(f"Discovery mismatch: {error}" for error in errors)
        metadata = safe / "MTD_MSIL2A.xml"
        lines.append(f"[{'x' if metadata.is_file() else ' '}] MTD_MSIL2A.xml")
        granule_root = safe / "GRANULE"
        granules = sorted(path for path in granule_root.iterdir() if path.is_dir()) if granule_root.is_dir() else []
        if not granules:
            for label, (band, resolution) in BANDS.items():
                lines.append(f"[ ] {label} - GRANULE/<original-granule-id>/IMG_DATA/R{resolution}m/*_{band}_{resolution}m.jp2")
        else:
            for granule in granules:
                for label, (band, resolution) in BANDS.items():
                    matches = band_candidates(granule, acquisition_date, tile.removeprefix("MGRS-"), band, resolution)
                    backend_matches = backend_band_matches(granule, band, resolution)
                    lines.append(f"[{'x' if len(matches) == len(backend_matches) == 1 else ' '}] {label} - GRANULE/{granule.name}/IMG_DATA/R{resolution}m/*_{band}_{resolution}m.jp2")
        lines.append("")
    return lines


def main() -> int:
    print("\n".join(checklist_lines()).rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
