"""Idempotently acquire publicly accessible GreenPulse 2025 source data.

Only primary/official product endpoints are used.  Sentinel-2 downloads need
Copernicus Data Space credentials; catalogue discovery does not.  The broad
AOI is a download/search envelope, never a municipal-boundary substitute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shapely.geometry import LineString, Polygon, mapping, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

YEAR = 2025
SEASON = "2025-03-01/2025-05-31"
# Search/download envelope only: includes PMC, PCMC, and an exterior reference area.
AOI_BBOX = [73.65, 18.35, 74.15, 18.85]
MAX_SCENE_CLOUD = 10.0
LANDSAT_STAC = "https://landsatlook.usgs.gov/stac-server"
SENTINEL_STAC = "https://stac.dataspace.copernicus.eu/v1"
CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PCMC_WFS = (
    "https://smartgisda.pcmcindia.gov.in/geoserver/citylayers4/wfs?"
    "service=WFS&version=2.0.0&request=GetFeature&typeNames=citylayers4:boundary&"
    "outputFormat=application/json&srsName=EPSG:4326"
)
WORLDCOVER_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_N18E072_Map.tif"
)
WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2024B/2025/IND/"
    "v1/100m/unconstrained/ind_pop_2025_UC_100m_R2024B_v1.tif"
)
OVERPASS_URLS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
SENTINEL_DATES = {"2025-03-14", "2025-04-13", "2025-05-10"}
SENTINEL_TILES = {"MGRS-43QCA", "MGRS-43QDA"}


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    # PCMC's current server requires legacy secure renegotiation. Certificate
    # verification remains enabled; this does not disable TLS verification.
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        context.options |= ssl.OP_LEGACY_SERVER_CONNECT
    else:
        context.options |= 0x4
    return context


SSL_CONTEXT = _ssl_context()


def _request_json(url: str, payload: dict | None = None, headers: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
        return json.load(response)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _download(url: str, destination: Path, *, headers: dict | None = None) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        _validate_download(destination)
        return {"path": destination.relative_to(ROOT).as_posix(), "url": url,
                "bytes": destination.stat().st_size, "checksum": _sha256(destination), "reused": True}
    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.is_file() and temporary.stat().st_size > 0:
        head_request = urllib.request.Request(url, method="HEAD", headers=headers or {})
        with urllib.request.urlopen(head_request, timeout=120, context=SSL_CONTEXT) as response:
            remote_size = int(response.headers.get("Content-Length", "0"))
        if remote_size and temporary.stat().st_size == remote_size:
            _validate_download(temporary, destination.name)
            temporary.replace(destination)
            return {"path": destination.relative_to(ROOT).as_posix(), "url": url,
                    "bytes": destination.stat().st_size, "checksum": _sha256(destination), "reused": False}
    request_headers = dict(headers or {})
    existing = temporary.stat().st_size if temporary.is_file() else 0
    if existing:
        request_headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=180, context=SSL_CONTEXT) as response:
            resumed = existing > 0 and response.status == 206
            mode = "ab" if resumed else "wb"
            expected_total = None
            content_range = response.headers.get("Content-Range")
            if content_range and "/" in content_range:
                expected_total = int(content_range.rsplit("/", 1)[1])
            elif response.headers.get("Content-Length"):
                expected_total = (existing if resumed else 0) + int(response.headers["Content-Length"])
            with temporary.open(mode) as stream:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    stream.write(block)
        if temporary.stat().st_size == 0:
            raise ValueError(f"empty response from {url}")
        if expected_total is not None and temporary.stat().st_size != expected_total:
            raise ValueError(f"incomplete response from {url}: {temporary.stat().st_size}/{expected_total} bytes")
        _validate_download(temporary, destination.name)
        temporary.replace(destination)
    except Exception:
        # Keep a non-empty partial for an idempotent byte-range retry.
        if temporary.exists() and temporary.stat().st_size == 0:
            temporary.unlink()
        raise
    return {"path": destination.relative_to(ROOT).as_posix(), "url": url,
            "bytes": destination.stat().st_size, "checksum": _sha256(destination), "reused": False}


def _validate_download(path: Path, intended_name: str | None = None) -> None:
    """Reject login/error pages and obviously malformed product files."""
    name = intended_name or path.name
    with path.open("rb") as stream:
        head = stream.read(512).lstrip()
    lowered = head.lower()
    if lowered.startswith((b"<!doctype html", b"<html")) or b"<title>login" in lowered:
        raise ValueError(f"authentication page returned instead of source file: {name}")
    if name.lower().endswith((".tif", ".tiff")) and head[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        raise ValueError(f"response is not a GeoTIFF: {name}")
    if name.lower().endswith("_mtl.txt") and b"GROUP = LANDSAT_METADATA_FILE" not in head:
        raise ValueError(f"response is not Landsat MTL metadata: {name}")


def cleanup_invalid_partials() -> dict:
    """Remove only known-invalid HTML payloads and empty .part files."""
    removed: list[str] = []
    roots = [ROOT / "data" / "raw" / "landsat", ROOT / "data" / "raw" / "worldpop"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            head = path.read_bytes()[:512].lstrip().lower()
            invalid_html = head.startswith((b"<!doctype html", b"<html"))
            empty_partial = path.suffix == ".part" and path.stat().st_size == 0
            if invalid_html or empty_partial:
                removed.append(path.relative_to(ROOT).as_posix())
                path.unlink()
    for root in roots:
        if root.exists():
            for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
                if not any(directory.iterdir()):
                    directory.rmdir()
    return {"removed": removed}


def _landsat_items() -> list[dict]:
    result = _request_json(f"{LANDSAT_STAC}/search", {
        "collections": ["landsat-c2l2-st"], "bbox": AOI_BBOX,
        "datetime": "2025-03-01T00:00:00Z/2025-05-31T23:59:59Z", "limit": 100,
    })
    return sorted(
        [item for item in result["features"]
         if "_T1_ST" in item["id"] and float(item["properties"]["eo:cloud_cover"]) <= MAX_SCENE_CLOUD],
        key=lambda item: item["properties"]["datetime"],
    )


def landsat_discovery() -> dict:
    items = []
    for item in _landsat_items():
        items.append({
            "product_id": item["id"].removesuffix("_ST"), "stac_item": item["id"],
            "acquisition_datetime": item["properties"]["datetime"],
            "scene_cloud_cover_percent": item["properties"]["eo:cloud_cover"],
            "wrs_path": item["properties"].get("landsat:wrs_path"),
            "wrs_row": item["properties"].get("landsat:wrs_row"),
            "stac_url": next(link["href"] for link in item["links"] if link["rel"] == "self"),
            "asset_urls": {name: item["assets"][name]["href"]
                           for name in ("MTL.txt", "lwir11", "qa_pixel", "qa_radsat")},
        })
    return {
        "source_organization": "U.S. Geological Survey EROS", "catalogue": LANDSAT_STAC,
        "collection": "landsat-c2l2-st", "license": "Public domain; no restrictions on Landsat product use",
        "date_range": SEASON, "search_bbox_not_a_boundary": AOI_BBOX,
        "selection": "Collection 2 L2SP Tier 1; scene cloud cover <= 10%; all matching scenes; pixel QA still required",
        "qa_files": "QA_PIXEL rejects bits 0-5 and 7; QA_RADSAT rejects terrain occlusion bit 11 in the existing pipeline",
        "items": items,
    }


def acquire_landsat() -> dict:
    records = []
    for item in _landsat_items():
        product_id = item["id"].removesuffix("_ST")
        folder = ROOT / "data" / "raw" / "landsat" / product_id
        assets = item["assets"]
        files = []
        for asset_name in ("MTL.txt", "lwir11", "qa_pixel", "qa_radsat"):
            url = assets[asset_name]["href"]
            try:
                files.append(_download(url, folder / Path(urllib.parse.urlparse(url).path).name))
            except ValueError as exc:
                raise RuntimeError(
                    "USGS redirected the Landsat asset request to authentication. "
                    "Download the exact products in data/provenance/discovery_2025.json "
                    "with EarthExplorer/M2M, or configure AWS requester-pays credentials."
                ) from exc
        records.append({
            "product_id": product_id,
            "stac_item": item["id"],
            "acquisition_datetime": item["properties"]["datetime"],
            "scene_cloud_cover_percent": item["properties"]["eo:cloud_cover"],
            "wrs_path": item["properties"].get("landsat:wrs_path"),
            "wrs_row": item["properties"].get("landsat:wrs_row"),
            "files": files,
        })
    return {
        "source_organization": "U.S. Geological Survey EROS",
        "catalogue": LANDSAT_STAC,
        "collection": "landsat-c2l2-st",
        "license": "Public domain; no restrictions on Landsat product use",
        "date_range": SEASON,
        "search_bbox_not_a_boundary": AOI_BBOX,
        "selection": "Collection 2 L2SP Tier 1; scene cloud cover <= 10%; all matching scenes; pixel QA still required",
        "qa_files": "QA_PIXEL rejects bits 0-5 and 7; QA_RADSAT rejects terrain occlusion bit 11 in the existing pipeline",
        "items": records,
    }


def _sentinel_items() -> list[dict]:
    result = _request_json(f"{SENTINEL_STAC}/search", {
        "collections": ["sentinel-2-l2a"], "bbox": AOI_BBOX,
        "datetime": "2025-03-01T00:00:00Z/2025-05-31T23:59:59Z", "limit": 100,
        "query": {"eo:cloud_cover": {"lte": MAX_SCENE_CLOUD}},
        "sortby": [{"field": "properties.datetime", "direction": "asc"}],
    })
    selected = []
    for item in result["features"]:
        day = item["properties"]["datetime"][:10]
        tile = item["properties"].get("grid:code")
        if day in SENTINEL_DATES and tile in SENTINEL_TILES:
            selected.append(item)
    return sorted(selected, key=lambda item: (item["properties"]["datetime"], item["id"]))


def _cdse_token() -> str:
    username, password = os.getenv("CDSE_USERNAME"), os.getenv("CDSE_PASSWORD")
    if not username or not password:
        raise ValueError("Set CDSE_USERNAME and CDSE_PASSWORD for a free Copernicus Data Space account")
    data = urllib.parse.urlencode({
        "client_id": "cdse-public", "grant_type": "password",
        "username": username, "password": password,
    }).encode("utf-8")
    request = urllib.request.Request(CDSE_TOKEN_URL, data=data,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
        return json.load(response)["access_token"]


def sentinel_discovery() -> dict:
    records = []
    for item in _sentinel_items():
        records.append({
            "product_id": item["id"], "acquisition_datetime": item["properties"]["datetime"],
            "scene_cloud_cover_percent": item["properties"]["eo:cloud_cover"],
            "mgrs_tile": item["properties"].get("grid:code"),
            "stac_url": next(link["href"] for link in item["links"] if link["rel"] == "self"),
        })
    return {
        "source_organization": "European Union Copernicus Programme / ESA",
        "catalogue": SENTINEL_STAC,
        "collection": "sentinel-2-l2a",
        "license": "Copernicus Sentinel Data Legal Notice; free, full and open access",
        "date_range": SEASON,
        "search_bbox_not_a_boundary": AOI_BBOX,
        "selection": "One <=10% cloud date per month spanning March-May, both intersecting MGRS tiles; SCL pixel masking still required",
        "scl_qa": "Existing pipeline accepts SCL classes 4 vegetation and 5 bare/built land only",
        "items": records,
    }


def acquire_sentinel() -> dict:
    token = _cdse_token()
    result = sentinel_discovery()
    by_id = {item["id"]: item for item in _sentinel_items()}
    for record in result["items"]:
        item = by_id[record["product_id"]]
        folder = ROOT / "data" / "raw" / "sentinel2" / f"{item['id']}.SAFE"
        files = []
        for asset_name in ("product_metadata", "B04_10m", "B08_10m", "B11_20m", "SCL_20m"):
            asset = item["assets"][asset_name]
            s3_path = asset["href"].split(f"{item['id']}.SAFE/", 1)[-1]
            destination = folder / s3_path
            url = asset["alternate"]["https"]["href"]
            files.append(_download(url, destination, headers={"Authorization": f"Bearer {token}"}))
        record["files"] = files
    return result


def acquire_pcmc_boundary() -> dict:
    destination = ROOT / "data" / "boundaries" / "source" / "pcmc_boundary_official.geojson"
    file_record = _download(PCMC_WFS, destination)
    document = json.loads(destination.read_text(encoding="utf-8"))
    if document.get("type") != "FeatureCollection" or len(document.get("features", [])) != 1:
        raise ValueError("Unexpected PCMC boundary WFS response")
    geometry = shape(document["features"][0]["geometry"])
    if geometry.is_empty or not geometry.is_valid or not geometry.bounds[0] < geometry.bounds[2]:
        raise ValueError("PCMC WFS boundary geometry is invalid")
    return {
        "source_organization": "Pimpri Chinchwad Municipal Corporation",
        "source_url": PCMC_WFS,
        "service": "Official PCMC Smart GIS WFS citylayers4:boundary",
        "license": "No redistribution license is stated by the WFS; retain for verification and obtain written terms before redistribution",
        "crs": document.get("crs"), "feature_count": 1, "geometry_type": geometry.geom_type,
        "bounds": list(geometry.bounds), "file": file_record,
        "status": "official municipal outline staging source; not a ward boundary and not yet combined with PMC",
    }


def _overpass(query: str) -> dict:
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors = []
    for url in OVERPASS_URLS:
        request = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "GreenPulse-AI/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("all Overpass endpoints failed: " + "; ".join(errors))


def _way_geometry(element: dict, polygon: bool):
    coords = [(point["lon"], point["lat"]) for point in element.get("geometry", [])]
    if polygon:
        if len(coords) < 4:
            return None
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        candidate = Polygon(coords)
    else:
        if len(coords) < 2:
            return None
        candidate = LineString(coords)
    return candidate if candidate.is_valid and not candidate.is_empty else None


def _relation_polygon(element: dict):
    outers, inners = [], []
    for member in element.get("members", []):
        geometry = _way_geometry(member, True)
        if geometry is not None:
            (inners if member.get("role") == "inner" else outers).append(geometry)
    if not outers:
        return None
    result = unary_union(outers)
    if inners:
        result = result.difference(unary_union(inners))
    return result if result.is_valid and not result.is_empty else None


def _osm_geojson(document: dict, kind: str) -> dict:
    features = []
    for element in document.get("elements", []):
        if element["type"] == "way":
            geometry = _way_geometry(element, kind != "roads")
        elif element["type"] == "relation" and kind != "roads":
            geometry = _relation_polygon(element)
        else:
            continue
        if geometry is None:
            continue
        properties = dict(element.get("tags", {}))
        properties.update({"osm_type": element["type"], "osm_id": element["id"],
                           "osm_version": element.get("version"), "osm_timestamp": element.get("timestamp")})
        features.append({"type": "Feature", "properties": properties, "geometry": mapping(geometry)})
    return {"type": "FeatureCollection", "features": features}


def acquire_osm(kinds: tuple[str, ...] = ("roads", "green_spaces", "buildings")) -> dict:
    south, west, north, east = AOI_BBOX[1], AOI_BBOX[0], AOI_BBOX[3], AOI_BBOX[2]
    mid_y, mid_x = (south + north) / 2, (west + east) / 2
    boxes = [(south, west, mid_y, mid_x), (south, mid_x, mid_y, east),
             (mid_y, west, north, mid_x), (mid_y, mid_x, north, east)]
    selectors = {
        "roads": 'way["highway"]{bbox};',
        "green_spaces": '(nwr["leisure"~"^(park|garden)$"]{bbox};nwr["landuse"~"^(forest|grass|recreation_ground)$"]{bbox};nwr["natural"~"^(wood|grassland)$"]{bbox};);',
        "buildings": 'nwr["building"]{bbox};',
    }
    records = []
    for kind in kinds:
        selector = selectors[kind]
        elements, timestamps, queries = {}, [], []
        for tile in boxes:
            bbox = f"({tile[0]},{tile[1]},{tile[2]},{tile[3]})"
            query = f"[out:json][timeout:300];{selector.format(bbox=bbox)}out meta geom;"
            raw_tile = _overpass(query)
            queries.append(query)
            timestamps.append(raw_tile.get("osm3s", {}).get("timestamp_osm_base"))
            for element in raw_tile.get("elements", []):
                elements[(element["type"], element["id"])] = element
            time.sleep(1)
        raw = {"elements": list(elements.values())}
        geojson = _osm_geojson(raw, kind)
        if not geojson["features"]:
            raise ValueError(f"OSM {kind} query returned no usable geometry")
        destination = ROOT / "data" / "raw" / "osm" / f"{kind}.geojson"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".geojson.part")
        temporary.write_text(json.dumps(geojson, separators=(",", ":")), encoding="utf-8")
        temporary.replace(destination)
        records.append({"kind": kind, "queries": queries, "osm_base_timestamps": timestamps,
                        "features": len(geojson["features"]), "path": destination.relative_to(ROOT).as_posix(),
                        "checksum": _sha256(destination)})
        time.sleep(2)
    return {
        "source_organization": "OpenStreetMap contributors",
        "source_url": list(OVERPASS_URLS), "license": "ODbL 1.0; attribution required",
        "search_bbox_not_a_boundary": AOI_BBOX, "records": records,
    }


def verify_existing_osm(kind: str) -> dict:
    destination = ROOT / "data" / "raw" / "osm" / f"{kind}.geojson"
    document = json.loads(destination.read_text(encoding="utf-8"))
    geometries = _osm_geojson({"elements": []}, kind)  # documents expected output shape
    if document.get("type") != geometries["type"] or not document.get("features"):
        raise ValueError(f"existing OSM {kind} is not a non-empty FeatureCollection")
    if kind == "roads" and any("highway" not in (feature.get("properties") or {}) for feature in document["features"]):
        raise ValueError("existing OSM roads contain a feature without a highway tag")
    timestamps = sorted({(f.get("properties") or {}).get("osm_timestamp") for f in document["features"]
                         if (f.get("properties") or {}).get("osm_timestamp")})
    query = '[out:json][timeout:300];way["highway"](18.35,73.65,18.85,74.15);out meta geom;' if kind == "roads" else None
    return {"source_organization": "OpenStreetMap contributors", "source_url": list(OVERPASS_URLS),
            "license": "ODbL 1.0; attribution required", "search_bbox_not_a_boundary": AOI_BBOX,
            "record": {"kind": kind, "query": query, "feature_count": len(document["features"]),
                       "oldest_object_timestamp": timestamps[0] if timestamps else None,
                       "newest_object_timestamp": timestamps[-1] if timestamps else None,
                       "path": destination.relative_to(ROOT).as_posix(), "checksum": _sha256(destination)}}


def acquire_public() -> dict:
    return {
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "pcmc_boundary_staging": acquire_pcmc_boundary(),
        "worldcover": {
            "source_organization": "ESA WorldCover Consortium", "source_url": WORLDCOVER_URL,
            "product": "ESA WorldCover 10m 2021 v200 N18E072", "license": "CC BY 4.0",
            "file": _download(WORLDCOVER_URL, ROOT / "data" / "raw" / "worldcover" / Path(WORLDCOVER_URL).name),
        },
        "worldpop": {
            "source_organization": "WorldPop / University of Southampton", "source_url": WORLDPOP_URL,
            "product": "Global 2015-2030 R2024B 2025 India v1 100m unconstrained population counts",
            "license": "CC BY 4.0",
            "file": _download(WORLDPOP_URL, ROOT / "data" / "raw" / "worldpop" / "india_population_counts.tif"),
        },
        "osm": acquire_osm(),
    }


def _write_record(name: str, record: dict) -> Path:
    destination = ROOT / "data" / "provenance" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire official GreenPulse 2025 sources without demo substitutes")
    parser.add_argument("mode", choices=("discover", "public", "landsat", "sentinel",
                                         "worldcover", "worldpop", "osm", "osm-roads", "osm-green",
                                         "osm-buildings", "verify-osm-roads", "pcmc-boundary", "cleanup"))
    args = parser.parse_args()
    if args.mode == "discover":
        record = {"discovered_at_utc": datetime.now(timezone.utc).isoformat(),
                  "landsat": landsat_discovery(), "sentinel2": sentinel_discovery()}
        path = _write_record("discovery_2025.json", record)
    elif args.mode == "cleanup":
        path = _write_record("cleanup.json", cleanup_invalid_partials())
    elif args.mode == "landsat":
        path = _write_record("acquisition_landsat_2025.json", acquire_landsat())
    elif args.mode == "worldcover":
        path = _write_record("acquisition_worldcover.json", {
            "source_organization": "ESA WorldCover Consortium", "source_url": WORLDCOVER_URL,
            "product": "ESA WorldCover 10m 2021 v200 N18E072", "license": "CC BY 4.0",
            "file": _download(WORLDCOVER_URL, ROOT / "data" / "raw" / "worldcover" / Path(WORLDCOVER_URL).name),
        })
    elif args.mode == "worldpop":
        path = _write_record("acquisition_worldpop.json", {
            "source_organization": "WorldPop / University of Southampton", "source_url": WORLDPOP_URL,
            "product": "Global 2015-2030 R2024B 2025 India v1 100m unconstrained population counts",
            "license": "CC BY 4.0", "units": "people per pixel",
            "file": _download(WORLDPOP_URL, ROOT / "data" / "raw" / "worldpop" / "india_population_counts.tif"),
        })
    elif args.mode.startswith("osm"):
        selections = {"osm": ("roads", "green_spaces", "buildings"), "osm-roads": ("roads",),
                      "osm-green": ("green_spaces",), "osm-buildings": ("buildings",)}
        path = _write_record(f"acquisition_{args.mode.replace('-', '_')}.json", acquire_osm(selections[args.mode]))
    elif args.mode == "verify-osm-roads":
        path = _write_record("acquisition_osm_roads.json", verify_existing_osm("roads"))
    elif args.mode == "pcmc-boundary":
        path = _write_record("acquisition_pcmc_boundary.json", acquire_pcmc_boundary())
    elif args.mode == "public":
        path = _write_record("acquisition_public_2025.json", acquire_public())
    else:
        path = _write_record("acquisition_sentinel2_2025.json", acquire_sentinel())
    print(f"Wrote provenance: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
