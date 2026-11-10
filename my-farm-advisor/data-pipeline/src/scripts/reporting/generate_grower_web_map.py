#!/usr/bin/env python3
"""Generate standalone "Field Atlas" web maps for grower field boundaries.

Creates one interactive HTML map per grower plus an optional combined map that
switches between growers and fields. The maps embed only slim field geometry
and metadata; basemap tiles stream from Esri at view time.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import (  # noqa: E402
    GROWERS_ROOT,
    farm_boundary_path,
    farm_report_asset_path,
    grower_dir,
    grower_report_path,
    growers_overview_path,
)

FIELD_COLORS = (
    "#6f7d3f",  # olive
    "#c28b2c",  # amber
    "#a9553a",  # clay
    "#8a9a5b",  # sage
    "#7c6a4f",  # umber
    "#b78a5a",  # wheat
)
COMBINED_FILENAME = "growers_field_map.html"
MANIFEST_FILENAME = "growers_field_map.json"
ACRES_PER_HECTARE = 2.471053814671653
DEFAULT_FIGURE_MAX_WIDTH = 1600
DEFAULT_FIGURE_QUALITY = 88

# Per-field report figures surfaced in the Field Atlas dossier. Paths are
# relative to the field directory; missing files are skipped at generation
# time so partial pipelines degrade gracefully.
FIGURE_SPECS: tuple[dict[str, str], ...] = (
    {
        "group": "ndvi",
        "key": "ndvi_cumulative",
        "label": "Cumulative NDVI by crop and year",
        "caption": "Best-available seasonal scenes grouped by dominant crop year, with 5th-95th percentile envelopes.",
        "path": "derived/features/ndvi_current_season_cumulative.png",
    },
    {
        "group": "ndvi",
        "key": "ndvi_corn",
        "label": "Corn average NDVI",
        "caption": "Crop-conditional mean NDVI for years this field grew corn.",
        "path": "derived/features/ndvi_corn.png",
    },
    {
        "group": "ndvi",
        "key": "ndvi_soybean",
        "label": "Soybean average NDVI",
        "caption": "Crop-conditional mean NDVI for years this field grew soybeans.",
        "path": "derived/features/ndvi_soybean.png",
    },
    {
        "group": "ndvi",
        "key": "ndvi_corn_peak",
        "label": "Corn 95th percentile peak NDVI",
        "caption": "Peak canopy vigor within the corn growing-season window.",
        "path": "derived/features/ndvi_corn_peak_95.png",
    },
    {
        "group": "ndvi",
        "key": "ndvi_soybean_peak",
        "label": "Soybean 95th percentile peak NDVI",
        "caption": "Peak canopy vigor within the soybean growing-season window.",
        "path": "derived/features/ndvi_soybean_peak_95.png",
    },
    {
        "group": "soil",
        "key": "soil_horizon",
        "label": "Soil horizon detail",
        "caption": "Dominant map units, horizon table, and interpolated depth profiles.",
        "path": "derived/features/soil_horizon_table.png",
    },
    {
        "group": "soil",
        "key": "soil_properties",
        "label": "Soil property summary",
        "caption": "Field-level soil texture, water, and complexity rollups.",
        "path": "derived/summaries/soil_properties.png",
    },
    {
        "group": "soil",
        "key": "soil_texture_triangle",
        "label": "USDA soil texture triangle",
        "caption": "One point per soil component, sized by relative abundance.",
        "path": "derived/features/soil_texture_triangle.png",
    },
    {
        "group": "soil",
        "key": "soil_weighted_map",
        "label": "Area-weighted soil properties",
        "caption": "Component-weighted spatial patterns for key soil properties.",
        "path": "derived/features/soil_weighted_property_map.png",
    },
    {
        "group": "soil",
        "key": "soil_component_map",
        "label": "Soil component map",
        "caption": "Map units and component composition across the field.",
        "path": "derived/features/soil_component_map.png",
    },
    {
        "group": "terrain",
        "key": "hillshade",
        "label": "Hillshade",
        "caption": "Shaded relief from the conditioned DEM.",
        "path": "derived/terrain/previews/hillshade.png",
    },
    {
        "group": "terrain",
        "key": "slope_degrees",
        "label": "Slope (degrees)",
        "caption": "Terrain gradient in degrees.",
        "path": "derived/terrain/previews/slope_degrees.png",
    },
    {
        "group": "terrain",
        "key": "topographic_wetness_index",
        "label": "Topographic wetness index",
        "caption": "Advisory proxy for water accumulation, not engineered drainage design.",
        "path": "derived/terrain/previews/topographic_wetness_index.png",
    },
    {
        "group": "terrain",
        "key": "erosion_proxy",
        "label": "Erosion proxy",
        "caption": "Advisory slope/flow proxy, not a soil-loss model.",
        "path": "derived/terrain/previews/erosion_proxy.png",
    },
    {
        "group": "terrain",
        "key": "depression_depth",
        "label": "Depression depth",
        "caption": "Advisory ponding-depression depth, not a drainage design.",
        "path": "derived/terrain/previews/depression_depth.png",
    },
    {
        "group": "terrain",
        "key": "relative_elevation",
        "label": "Relative elevation",
        "caption": "Elevation relative to the field low point.",
        "path": "derived/terrain/previews/relative_elevation.png",
    },
    {
        "group": "report",
        "key": "field_report",
        "label": "Full field report poster",
        "caption": "One-page field intelligence poster. Preview shown; open the full-resolution PNG for detail.",
        "path": "derived/reports/field_report.png",
    },
)

DOWNLOAD_SPECS: tuple[dict[str, str], ...] = (
    {
        "group": "soil",
        "label": "Soil summary (CSV)",
        "path": "soil/ssurgo_summary.csv",
    },
    {
        "group": "ndvi",
        "label": "NDVI summary (JSON)",
        "path": "derived/summaries/ndvi_card_summary.json",
    },
    {
        "group": "terrain",
        "label": "Terrain summary (JSON)",
        "path": "derived/tables/dem_terrain_summary.json",
    },
)

SOIL_STAT_KEYS = (
    "dominant_soil",
    "drainage_class",
    "erosion_risk",
    "ph_constraint",
    "soil_source",
    "n_components",
    "n_horizons",
    "avg_om_pct",
    "avg_ph",
    "total_aws_inches",
    "avg_cec",
    "avg_clay_pct",
    "avg_sand_pct",
)
SOIL_STAT_NUMERIC = {
    "n_components",
    "n_horizons",
    "avg_om_pct",
    "avg_ph",
    "total_aws_inches",
    "avg_cec",
    "avg_clay_pct",
    "avg_sand_pct",
}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return payload


def _natural_key(value: str) -> list[tuple[int, Any]]:
    """Sort strings so field-2 precedes field-10."""
    parts: list[tuple[int, Any]] = []
    buffer = ""
    number = ""
    for char in str(value):
        if char.isdigit():
            if buffer:
                parts.append((1, buffer.lower()))
                buffer = ""
            number += char
        else:
            if number:
                parts.append((0, int(number)))
                number = ""
            buffer += char
    if number:
        parts.append((0, int(number)))
    if buffer:
        parts.append((1, buffer.lower()))
    return parts


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field_crop_override(farm_root: Path, field_slug: str) -> str:
    """Read an explicit current-crop label from canonical field metadata."""
    metadata_path = farm_root / "fields" / field_slug / "field.json"
    if not metadata_path.is_file():
        return ""
    try:
        metadata = _read_json(metadata_path)
    except (OSError, ValueError) as exc:
        print(
            f"warn  {metadata_path}: cannot read field metadata ({exc})",
            file=sys.stderr,
        )
        return ""
    return _first_text(
        metadata.get("crop_name"),
        metadata.get("current_crop"),
        metadata.get("crop"),
    )


def _field_inventory(path: Path) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not path.is_file():
        return lookup
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            field_id = (row.get("field_id") or "").strip()
            field_slug = (row.get("field_slug") or "").strip()
            if field_id and field_slug:
                lookup[field_id] = field_slug
    return lookup


def _valid_geometry(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if value.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    if not value.get("coordinates"):
        return None
    return value


def _round_number(value: Any, digits: int = 2) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return round(number, digits)


def _soil_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            row = next(csv.DictReader(handle), None)
    except (OSError, ValueError, csv.Error):
        return {}
    if not row:
        return {}
    stats: dict[str, Any] = {}
    for key in SOIL_STAT_KEYS:
        value = row.get(key)
        if value is None or str(value).strip() == "":
            continue
        if key in SOIL_STAT_NUMERIC:
            rounded = _round_number(value)
            if rounded is not None:
                stats[key] = rounded
        else:
            stats[key] = str(value).strip()
    return stats


def _ndvi_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = _read_json(path)
    except (OSError, ValueError):
        return {}
    cards = payload.get("cards")
    if not isinstance(cards, dict):
        return {}
    stats: dict[str, Any] = {}
    for key in ("corn", "soybean", "corn_peak_95", "soybean_peak_95"):
        card = cards.get(key)
        if not isinstance(card, dict) or card.get("status") != "available":
            continue
        years = card.get("years")
        stats[key] = {
            "years": [int(year) for year in years if isinstance(year, int)]
            if isinstance(years, list)
            else [],
            "year_count": card.get("year_count"),
            "scene_count": card.get("scene_count"),
            "mean_ndvi": _round_number(card.get("mean_ndvi"), 3),
        }
    return stats


def _terrain_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = _read_json(path)
    except (OSError, ValueError):
        return {}
    elevation = payload.get("elevation_range_m")
    if not isinstance(elevation, dict):
        elevation = {}
    products = payload.get("products")
    return {
        "min_m": _round_number(elevation.get("min"), 1),
        "max_m": _round_number(elevation.get("max"), 1),
        "range_m": _round_number(elevation.get("range"), 1),
        "product_count": len(products) if isinstance(products, list) else None,
        "advisory": payload.get("advisory_label"),
        "conditioning_status": payload.get("conditioning_status"),
    }


def _pillow_available() -> bool:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _encode_figure(path: Path, max_width: int, quality: int) -> str:
    """Encode a report figure as a portable data URI.

    Figures are resized to a readable web width and converted to WebP so the
    generated map can be copied as a single portable HTML file without
    ballooning to the size of the source PNGs. Original PNGs stay linked for
    full-resolution inspection.
    """
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "Pillow is required to embed Field Atlas figures; "
            "install it or run with --no-embed-figures"
        ) from exc

    with Image.open(path) as image:
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
        if max_width > 0 and image.width > max_width:
            height = max(1, round(image.height * max_width / image.width))
            image = image.resize((max_width, height), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=quality, method=6)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/webp;base64,{encoded}"


def _figure_records(
    field_root: Path,
    *,
    embed_figures: bool,
    max_width: int,
    quality: int,
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    for spec in FIGURE_SPECS:
        path = field_root / spec["path"]
        if not path.is_file():
            continue
        record: dict[str, Any] = {
            "group": spec["group"],
            "key": spec["key"],
            "label": spec["label"],
            "caption": spec["caption"],
            "file": path.relative_to(field_root).as_posix(),
            "bytes": path.stat().st_size,
            "src": "",
        }
        if embed_figures:
            record["src"] = _encode_figure(path, max_width, quality)
        figures.append(record)
    return figures


def _download_records(field_root: Path) -> list[dict[str, str]]:
    downloads: list[dict[str, str]] = []
    for spec in DOWNLOAD_SPECS:
        path = field_root / spec["path"]
        if not path.is_file():
            continue
        downloads.append(
            {
                "group": spec["group"],
                "label": spec["label"],
                "file": path.relative_to(field_root).as_posix(),
            }
        )
    return downloads


def load_grower(
    grower_slug: str,
    *,
    embed_figures: bool = True,
    figure_max_width: int = DEFAULT_FIGURE_MAX_WIDTH,
    figure_quality: int = DEFAULT_FIGURE_QUALITY,
) -> dict[str, Any] | None:
    """Load one grower and all usable field boundaries below it."""
    root = grower_dir(grower_slug)
    grower_meta: dict[str, Any] = {}
    grower_meta_path = root / "grower.json"
    if grower_meta_path.is_file():
        try:
            grower_meta = _read_json(grower_meta_path)
        except (OSError, ValueError) as exc:
            print(f"warn  {grower_slug}: cannot read grower.json ({exc})", file=sys.stderr)

    farms_root = root / "farms"
    if not farms_root.is_dir():
        return None

    farms: list[dict[str, Any]] = []
    color_index = 0

    for farm_root in sorted(
        (child for child in farms_root.iterdir() if child.is_dir()),
        key=lambda path: _natural_key(path.name),
    ):
        farm_slug = farm_root.name
        boundary_path = farm_boundary_path(grower_slug, farm_slug)
        if not boundary_path.is_file():
            continue

        farm_meta: dict[str, Any] = {}
        farm_meta_path = farm_root / "farm.json"
        if farm_meta_path.is_file():
            try:
                farm_meta = _read_json(farm_meta_path)
            except (OSError, ValueError) as exc:
                print(
                    f"warn  {grower_slug}/{farm_slug}: cannot read farm.json ({exc})",
                    file=sys.stderr,
                )

        inventory = _field_inventory(farm_root / "manifests" / "field-inventory.csv")
        try:
            boundary = _read_json(boundary_path)
        except (OSError, ValueError) as exc:
            print(
                f"warn  {grower_slug}/{farm_slug}: cannot read field boundaries ({exc})",
                file=sys.stderr,
            )
            continue

        features = boundary.get("features")
        if not isinstance(features, list):
            continue

        farm_state = _first_text(farm_meta.get("state"))
        farm_country = _first_text(farm_meta.get("country"))
        fields: list[dict[str, Any]] = []

        for feature in features:
            if not isinstance(feature, dict):
                continue
            geometry = _valid_geometry(feature.get("geometry"))
            if geometry is None:
                continue
            properties = feature.get("properties")
            if not isinstance(properties, dict):
                properties = {}

            field_id = _first_text(properties.get("field_id"))
            if not field_id:
                continue
            field_slug = _first_text(
                properties.get("field_slug"),
                inventory.get(field_id),
                default=field_id,
            )

            area_acres = _as_float(properties.get("area_acres"))
            if area_acres is None:
                area_hectares = _as_float(properties.get("area_ha_est"))
                if area_hectares is not None:
                    area_acres = area_hectares * ACRES_PER_HECTARE

            crop_override = _field_crop_override(farm_root, field_slug)
            field_root = farm_root / "fields" / field_slug

            fields.append(
                {
                    "id": field_id,
                    "slug": field_slug,
                    "crop": crop_override
                    or _first_text(
                        properties.get("crop"),
                        properties.get("crop_name"),
                        default="Unknown",
                    ),
                    "area_acres": round(area_acres, 1) if area_acres is not None else None,
                    "state": _first_text(properties.get("state"), farm_state),
                    "county": _first_text(properties.get("county")),
                    "country": _first_text(properties.get("country"), farm_country),
                    "source": _first_text(properties.get("source")),
                    "geometry": geometry,
                    "asset_dir": f"farms/{farm_slug}/fields/{field_slug}",
                    "figures": _figure_records(
                        field_root,
                        embed_figures=embed_figures,
                        max_width=figure_max_width,
                        quality=figure_quality,
                    ),
                    "downloads": _download_records(field_root),
                    "stats": {
                        "soil": _soil_stats(field_root / "soil" / "ssurgo_summary.csv"),
                        "ndvi": _ndvi_stats(
                            field_root / "derived" / "summaries" / "ndvi_card_summary.json"
                        ),
                        "terrain": _terrain_stats(
                            field_root / "derived" / "tables" / "dem_terrain_summary.json"
                        ),
                    },
                }
            )

        fields.sort(key=lambda field: _natural_key(field["id"]))
        if not fields:
            continue

        for field in fields:
            field["color"] = FIELD_COLORS[color_index % len(FIELD_COLORS)]
            color_index += 1

        farm_report = farm_report_asset_path(grower_slug, farm_slug, "html")
        farm_report_link: dict[str, Any] | None = None
        if farm_report.is_file():
            farm_report_link = {
                "file": farm_report.relative_to(root).as_posix(),
                "bytes": farm_report.stat().st_size,
            }

        farms.append(
            {
                "slug": _first_text(farm_meta.get("farm_slug"), default=farm_slug),
                "display_name": _first_text(farm_meta.get("display_name"), default=farm_slug),
                "state": farm_state,
                "country": farm_country,
                "farm_report": farm_report_link,
                "fields": fields,
            }
        )

    if not farms:
        return None

    field_count = sum(len(farm["fields"]) for farm in farms)
    return {
        "slug": grower_slug,
        "display_name": _first_text(grower_meta.get("display_name"), default=grower_slug),
        "farms": farms,
        "field_count": field_count,
    }


def discover_growers() -> list[str]:
    if not GROWERS_ROOT.is_dir():
        return []
    found: list[str] = []
    for child in GROWERS_ROOT.iterdir():
        if not child.is_dir() or not (child / "grower.json").is_file():
            continue
        if any((child / "farms").glob("*/boundary/field_boundaries.geojson")):
            found.append(child.name)
    return sorted(found, key=_natural_key)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _single_payload(
    grower: dict[str, Any], combined_available: bool = True
) -> dict[str, Any]:
    return {
        "mode": "single",
        "defaultGrower": grower["slug"],
        "combinedAvailable": combined_available,
        "growers": [grower],
    }


def _combined_payload(growers: list[dict[str, Any]]) -> dict[str, Any]:
    slugs = {grower["slug"] for grower in growers}
    default = "il-grower" if "il-grower" in slugs else growers[0]["slug"]
    ordered = sorted(
        growers,
        key=lambda grower: (grower["slug"] != default, _natural_key(grower["slug"])),
    )
    return {
        "mode": "combined",
        "defaultGrower": default,
        "growers": ordered,
    }


def _doc_title(payload: dict[str, Any]) -> str:
    if payload["mode"] == "single":
        grower = payload["growers"][0]
        return f"{grower['display_name']} — Field Atlas"
    return "Grower Field Atlas"


def render_html(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return _TEMPLATE.replace("__DOC_TITLE__", html.escape(_doc_title(payload))).replace(
        "__PAYLOAD_JSON__", payload_json
    )


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__DOC_TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<style>
:root {
  --paper: #f5eddc;
  --paper-2: #fbf6ea;
  --paper-3: #e9dcc2;
  --ink: #302b21;
  --ink-soft: #5d5443;
  --muted: #857962;
  --line: rgba(48, 43, 33, .16);
  --line-strong: rgba(48, 43, 33, .28);
  --clay: #a9553a;
  --shadow: 0 18px 40px rgba(48, 43, 33, .14);
}
html, body { margin: 0; height: 100%; }
body {
  color: var(--ink);
  background: var(--paper);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
button, a { -webkit-tap-highlight-color: transparent; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--clay); outline-offset: 2px; }
#app { display: flex; height: 100vh; overflow: hidden; }
.atlas-panel {
  z-index: 800;
  display: flex;
  flex: 0 0 390px;
  flex-direction: column;
  width: 390px;
  border-right: 1px solid var(--line-strong);
  background:
    radial-gradient(circle at 10% 0%, rgba(194, 139, 44, .10), transparent 32%),
    radial-gradient(circle at 100% 100%, rgba(111, 125, 63, .10), transparent 38%),
    var(--paper);
  box-shadow: var(--shadow);
}
.brand { padding: 30px 28px 22px; border-bottom: 1px solid var(--line); }
.eyebrow {
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .2em;
  text-transform: uppercase;
}
.brand h1 {
  margin: 0;
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 38px;
  font-weight: 500;
  letter-spacing: -.02em;
  line-height: 1;
}
.lede {
  max-width: 30ch;
  margin: 12px 0 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.55;
}
.grower-switcher {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  padding: 16px 28px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 250, 240, .35);
}
.grower-switcher[hidden] { display: none; }
.pill {
  padding: 7px 13px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: transparent;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  line-height: 1;
  text-transform: uppercase;
  cursor: pointer;
  transition: background .16s ease, border-color .16s ease, color .16s ease;
}
.pill:hover { border-color: var(--ink); color: var(--ink); }
.pill.is-active { border-color: var(--ink); background: var(--ink); color: var(--paper-2); }
.panel-meta { padding: 22px 28px 16px; }
.panel-meta h2 {
  margin: 0;
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 24px;
  font-weight: 500;
  line-height: 1.1;
}
.active-subtitle { margin: 7px 0 0; color: var(--muted); font-size: 12px; line-height: 1.5; }
.standalone-link {
  display: inline-block;
  margin-top: 12px;
  padding-bottom: 2px;
  border-bottom: 1px solid rgba(169, 85, 58, .35);
  color: var(--clay);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .04em;
  text-decoration: none;
}
.standalone-link:hover { border-color: var(--clay); }
.standalone-link[hidden] { display: none; }
.field-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 20px 24px;
  scrollbar-color: var(--paper-3) transparent;
  scrollbar-width: thin;
}
.grower-heading {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin: 22px 8px 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line-strong);
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.farm-group { margin-top: 16px; }
.farm-group-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin: 0 8px 6px;
  color: var(--muted);
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 13px;
  font-style: italic;
}
.farm-group-head span:last-child {
  color: var(--muted);
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-size: 9px;
  font-style: normal;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.field-row {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 10px 9px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--ink);
  text-align: left;
  cursor: pointer;
  transition: background .14s ease, border-color .14s ease;
}
.field-row:hover { border-color: var(--line); background: rgba(255, 250, 240, .72); }
.field-row.is-active {
  border-color: var(--line-strong);
  background: var(--paper-2);
  box-shadow: 0 3px 12px rgba(48, 43, 33, .06);
}
.swatch {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--swatch);
  box-shadow: 0 0 0 3px rgba(48, 43, 33, .08);
}
.field-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.field-name {
  overflow: hidden;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .01em;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.field-detail {
  overflow: hidden;
  color: var(--muted);
  font-size: 10px;
  letter-spacing: .04em;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}
.field-arrow { color: var(--muted); font-size: 14px; opacity: .55; transition: .14s ease; }
.field-row:hover .field-arrow, .field-row.is-active .field-arrow { opacity: 1; transform: translateX(1px); }
.panel-footer {
  padding: 16px 28px 20px;
  border-top: 1px solid var(--line);
  background: rgba(255, 250, 240, .3);
}
.panel-footer p { margin: 0; color: var(--muted); font-size: 10px; line-height: 1.55; }
.map-shell { position: relative; flex: 1; min-width: 0; background: #dce1d2; }
#map { position: absolute; inset: 0; }
.map-tools {
  position: absolute;
  top: 18px;
  right: 18px;
  z-index: 650;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.basemap-toggle {
  display: flex;
  padding: 4px;
  border: 1px solid rgba(48, 43, 33, .2);
  border-radius: 999px;
  background: rgba(245, 237, 220, .94);
  box-shadow: 0 6px 18px rgba(48, 43, 33, .18);
  backdrop-filter: blur(6px);
}
.basemap-toggle button {
  padding: 8px 13px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  line-height: 1;
  text-transform: uppercase;
  cursor: pointer;
}
.basemap-toggle button.is-active { background: var(--ink); color: var(--paper-2); }
.tool-button {
  padding: 10px 15px;
  border: 1px solid rgba(48, 43, 33, .2);
  border-radius: 999px;
  background: rgba(245, 237, 220, .94);
  color: var(--ink);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  line-height: 1;
  text-transform: uppercase;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(48, 43, 33, .18);
  backdrop-filter: blur(6px);
}
.tool-button:hover { background: var(--paper-2); }
.map-caption {
  position: absolute;
  bottom: 18px;
  left: 18px;
  z-index: 650;
  max-width: calc(100% - 90px);
  padding: 9px 13px;
  border: 1px solid rgba(48, 43, 33, .16);
  border-radius: 8px;
  background: rgba(245, 237, 220, .92);
  color: var(--ink-soft);
  font-size: 10px;
  letter-spacing: .08em;
  text-transform: uppercase;
  box-shadow: 0 6px 18px rgba(48, 43, 33, .12);
  backdrop-filter: blur(6px);
}
.map-error {
  display: grid;
  place-items: center;
  height: 100%;
  padding: 30px;
  color: var(--ink-soft);
  font-size: 14px;
  line-height: 1.6;
  text-align: center;
}
.leaflet-popup-content-wrapper {
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: var(--paper-2);
  box-shadow: 0 18px 40px rgba(48, 43, 33, .24);
}
.leaflet-popup-tip { border: 1px solid var(--line-strong); background: var(--paper-2); }
.leaflet-popup-content { width: 320px !important; margin: 18px 20px 16px; }
.popup-kicker {
  margin: 0 0 5px;
  color: var(--clay);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .18em;
  text-transform: uppercase;
}
.atlas-popup-content h3 {
  margin: 0 0 12px;
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 22px;
  font-weight: 500;
  line-height: 1;
}
.atlas-popup-content dl {
  display: grid;
  gap: 7px;
  margin: 0;
  font-size: 11px;
  line-height: 1.35;
}
.atlas-popup-content dl > div {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  align-items: baseline;
  gap: 10px;
}
.atlas-popup-content dt {
  color: var(--muted);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .1em;
  text-transform: uppercase;
}
.atlas-popup-content dd { margin: 0; overflow-wrap: break-word; }
.leaflet-control-attribution {
  background: rgba(245, 237, 220, .82) !important;
  color: var(--ink-soft) !important;
  font-size: 9px !important;
}
.leaflet-control-attribution a { color: var(--clay) !important; }
.leaflet-bar a { border-bottom-color: var(--line); background: var(--paper-2); color: var(--ink); }
.leaflet-bar a:hover { background: #fff; }
.popup-actions { margin-top: 14px; }
.popup-open {
  width: 100%;
  padding: 10px 13px;
  border: 1px solid var(--ink);
  border-radius: 999px;
  background: var(--ink);
  color: var(--paper-2);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .12em;
  line-height: 1;
  text-transform: uppercase;
  cursor: pointer;
}
.popup-open:hover { background: #1f2418; }
.dossier-backdrop {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: rgba(48, 43, 33, .30);
  opacity: 0;
  pointer-events: none;
  transition: opacity .2s ease;
  backdrop-filter: blur(2px);
}
#app.dossier-open .dossier-backdrop { opacity: 1; pointer-events: auto; }
.dossier {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 910;
  display: flex;
  flex-direction: column;
  width: min(560px, 94vw);
  border-left: 1px solid var(--line-strong);
  background:
    radial-gradient(circle at 100% 0%, rgba(194, 139, 44, .10), transparent 34%),
    var(--paper);
  box-shadow: -24px 0 60px rgba(48, 43, 33, .22);
  transform: translateX(104%);
  visibility: hidden;
  transition: transform .24s ease, visibility .24s ease;
}
#app.dossier-open .dossier { transform: translateX(0); visibility: visible; }
.dossier-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 26px 18px;
  border-bottom: 1px solid var(--line);
}
.dossier-kicker {
  margin: 0 0 6px;
  color: var(--clay);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .18em;
  text-transform: uppercase;
}
.dossier-head h2 {
  margin: 0;
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  font-size: 30px;
  font-weight: 500;
  letter-spacing: -.02em;
  line-height: 1;
}
.dossier-sub { margin: 8px 0 0; color: var(--muted); font-size: 11px; line-height: 1.5; }
.dossier-close {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  background: transparent;
  color: var(--ink-soft);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}
.dossier-close:hover { border-color: var(--ink); color: var(--ink); }
.dossier-tabs {
  display: flex;
  gap: 5px;
  overflow-x: auto;
  padding: 11px 22px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 250, 240, .42);
  scrollbar-width: none;
}
.dossier-tabs::-webkit-scrollbar { display: none; }
.dossier-tab {
  flex: 0 0 auto;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .1em;
  line-height: 1;
  text-transform: uppercase;
  cursor: pointer;
}
.dossier-tab:hover { color: var(--ink); }
.dossier-tab.is-active { border-color: var(--ink); background: var(--ink); color: var(--paper-2); }
.dossier-body { flex: 1; overflow-y: auto; padding: 20px 26px 30px; scrollbar-width: thin; }
.dossier-section + .dossier-section { margin-top: 22px; }
.dossier-section h3 {
  margin: 0 0 10px;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.dossier-record {
  display: grid;
  gap: 7px;
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
}
.dossier-record > div { display: grid; grid-template-columns: 84px minmax(0, 1fr); gap: 10px; }
.dossier-record dt { color: var(--muted); font-size: 9px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.dossier-record dd { margin: 0; overflow-wrap: break-word; }
.chip-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.chip {
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper-2);
}
.chip dt { color: var(--muted); font-size: 8px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.chip dd { margin: 3px 0 0; font-size: 14px; font-weight: 700; line-height: 1.2; overflow-wrap: break-word; }
.chip dd small { color: var(--muted); font-size: 10px; font-weight: 600; }
.figure-grid { display: grid; gap: 12px; }
.figure-grid.is-terrain { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.figure-card {
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow: hidden;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--paper-2);
  color: var(--ink);
  text-align: left;
  cursor: zoom-in;
  transition: border-color .14s ease, box-shadow .14s ease;
}
.figure-card:hover { border-color: var(--line-strong); box-shadow: 0 6px 18px rgba(48, 43, 33, .10); }
.figure-card img { display: block; width: 100%; height: auto; background: #fff; }
.figure-copy { padding: 8px 10px 10px; }
.figure-label { display: block; font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.figure-caption { display: block; margin-top: 3px; color: var(--muted); font-size: 10px; letter-spacing: 0; line-height: 1.45; text-transform: none; }
.figure-missing { padding: 18px; border: 1px dashed var(--line-strong); border-radius: 8px; color: var(--muted); font-size: 11px; line-height: 1.5; }
.link-list { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.link-list a {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: rgba(255, 250, 240, .4);
  color: var(--clay);
  font-size: 11px;
  font-weight: 700;
  text-decoration: none;
}
.link-list a:hover { border-color: var(--clay); }
.link-list span { color: var(--muted); font-size: 9px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
.report-card {
  padding: 14px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: var(--paper-2);
}
.report-card h3 { margin: 0 0 6px; font-family: Georgia, serif; font-size: 18px; font-weight: 500; letter-spacing: 0; text-transform: none; }
.report-card p { margin: 0 0 10px; color: var(--muted); font-size: 11px; line-height: 1.55; }
.report-card a { color: var(--clay); font-weight: 700; text-decoration: none; border-bottom: 1px solid rgba(169, 85, 58, .35); }
.report-card .warn { color: var(--clay); font-weight: 700; }
.dossier-note { margin: 12px 0 0; color: var(--muted); font-size: 10px; line-height: 1.55; }
.empty-state { padding: 22px; border: 1px dashed var(--line-strong); border-radius: 10px; color: var(--muted); font-size: 12px; line-height: 1.6; }
.viewer {
  width: min(96vw, 1400px);
  height: 92vh;
  max-width: none;
  max-height: none;
  padding: 0;
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  background: var(--paper);
  color: var(--ink);
}
.viewer::backdrop { background: rgba(20, 18, 14, .84); backdrop-filter: blur(3px); }
.viewer-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--paper);
}
.viewer-caption { flex: 1; min-width: 0; overflow: hidden; font-size: 11px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.viewer-button {
  flex: 0 0 auto;
  padding: 7px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: transparent;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .08em;
  line-height: 1;
  text-transform: uppercase;
  cursor: pointer;
}
.viewer-button:hover { border-color: var(--ink); color: var(--ink); }
.viewer-button[disabled] { opacity: .35; cursor: default; }
.viewer-stage {
  display: grid;
  place-items: center;
  height: calc(100% - 56px);
  overflow: auto;
  padding: 14px;
  background: #232019;
}
.viewer-image { display: block; max-width: 100%; max-height: 100%; width: auto; height: auto; }
.viewer-stage.is-zoomed { place-items: start; }
.viewer-stage.is-zoomed .viewer-image { max-width: none; max-height: none; }
@media (max-width: 860px) {
  html, body { height: auto; }
  #app { display: block; height: auto; overflow: visible; }
  .atlas-panel {
    width: auto;
    max-height: 56vh;
    border-right: 0;
    border-bottom: 1px solid var(--line-strong);
  }
  .brand { padding: 22px 20px 16px; }
  .brand h1 { font-size: 30px; }
  .grower-switcher, .panel-meta { padding-right: 20px; padding-left: 20px; }
  .field-list { padding-right: 12px; padding-left: 12px; }
  .panel-footer { padding: 12px 20px 16px; }
  .map-shell { height: 64vh; min-height: 420px; }
  .map-tools { top: 12px; right: 12px; }
  .map-caption { bottom: 12px; left: 12px; }
  .leaflet-popup-content { width: min(72vw, 320px) !important; }
  .dossier {
    top: auto;
    left: 0;
    right: 0;
    bottom: 0;
    width: auto;
    max-height: 84vh;
    border-top: 1px solid var(--line-strong);
    border-left: 0;
    border-radius: 16px 16px 0 0;
    transform: translateY(104%);
  }
  #app.dossier-open .dossier { transform: translateY(0); }
  .dossier-head { padding: 18px 20px 14px; }
  .dossier-head h2 { font-size: 24px; }
  .dossier-tabs { padding: 9px 16px; }
  .dossier-body { padding: 16px 20px 28px; }
  .figure-grid.is-terrain { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .viewer { width: 100vw; height: 100vh; border: 0; border-radius: 0; }
  .viewer-bar { flex-wrap: wrap; }
}
@media (prefers-reduced-motion: reduce) {
  .field-arrow, .field-row, .pill, .dossier, .dossier-backdrop { transition: none; }
}
</style>
</head>
<body>
<div id="app">
  <aside class="atlas-panel">
    <header class="brand">
      <p class="eyebrow">My Farm Advisor</p>
      <h1>Field Atlas</h1>
      <p class="lede">A quiet, satellite-first view of every field in the holding. Choose a field to inspect it up close.</p>
    </header>
    <nav class="grower-switcher" id="grower-switcher" aria-label="Growers" hidden></nav>
    <section class="panel-meta">
      <p class="eyebrow" id="meta-kicker">Selected holding</p>
      <h2 id="active-title">Loading fields…</h2>
      <p class="active-subtitle" id="active-subtitle"></p>
      <a class="standalone-link" id="standalone-link" href="#" hidden></a>
    </section>
    <section class="field-list" id="field-list" aria-label="Fields"></section>
    <footer class="panel-footer">
      <p>Click a field row to open its dossier. Basemap tiles stream from Esri.</p>
    </footer>
  </aside>
  <main class="map-shell">
    <div id="map" role="application" aria-label="Interactive field map"></div>
    <div class="map-tools">
      <div class="basemap-toggle" id="basemap-toggle" role="group" aria-label="Basemap">
        <button type="button" data-basemap="satellite" class="is-active" aria-pressed="true">Satellite</button>
        <button type="button" data-basemap="streets" aria-pressed="false">Streets</button>
      </div>
      <button type="button" class="tool-button" id="fit-all">Fit all</button>
    </div>
    <div class="map-caption" id="map-caption"></div>
  </main>
  <div class="dossier-backdrop" id="dossier-backdrop" hidden></div>
  <aside class="dossier" id="dossier" role="dialog" aria-modal="true"
    aria-labelledby="dossier-title" hidden>
    <header class="dossier-head">
      <div>
        <p class="dossier-kicker" id="dossier-kicker">Field dossier</p>
        <h2 id="dossier-title">Field</h2>
        <p class="dossier-sub" id="dossier-sub"></p>
      </div>
      <button type="button" class="dossier-close" id="dossier-close"
        aria-label="Close field dossier">&times;</button>
    </header>
    <div class="dossier-tabs" id="dossier-tabs" role="tablist" aria-label="Field dossier sections">
      <button type="button" class="dossier-tab" data-tab="overview" role="tab"
        aria-selected="false">Overview</button>
      <button type="button" class="dossier-tab" data-tab="ndvi" role="tab"
        aria-selected="false">NDVI</button>
      <button type="button" class="dossier-tab" data-tab="soil" role="tab"
        aria-selected="false">Soil</button>
      <button type="button" class="dossier-tab" data-tab="terrain" role="tab"
        aria-selected="false">Terrain</button>
      <button type="button" class="dossier-tab" data-tab="report" role="tab"
        aria-selected="false">Report</button>
    </div>
    <div class="dossier-body" id="dossier-body" role="tabpanel" tabindex="0"></div>
  </aside>
</div>
<dialog class="viewer" id="viewer" aria-labelledby="viewer-caption">
  <div class="viewer-bar">
    <button type="button" class="viewer-button" id="viewer-prev" aria-label="Previous figure">Prev</button>
    <p class="viewer-caption" id="viewer-caption">Figure</p>
    <button type="button" class="viewer-button" id="viewer-next" aria-label="Next figure">Next</button>
    <button type="button" class="viewer-button" id="viewer-zoom-out" aria-label="Zoom out">&minus;</button>
    <button type="button" class="viewer-button" id="viewer-zoom-in" aria-label="Zoom in">+</button>
    <a class="viewer-button" id="viewer-original" href="#" target="_blank" rel="noopener">Open original</a>
    <button type="button" class="viewer-button" id="viewer-close" aria-label="Close figure viewer">Close</button>
  </div>
  <div class="viewer-stage" id="viewer-stage">
    <img class="viewer-image" id="viewer-image" alt="">
  </div>
</dialog>
<noscript>This map requires JavaScript.</noscript>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(function () {
  "use strict";

  const DATA = __PAYLOAD_JSON__;
  const mapNode = document.getElementById("map");

  if (typeof L === "undefined") {
    mapNode.innerHTML = '<div class="map-error">Leaflet could not load. Check the network connection and reload the page.</div>';
    return;
  }

  const map = L.map(mapNode, {
    zoomControl: true,
    preferCanvas: true
  });
  map.setView([39.5, -96], 4);

  const basemaps = {
    satellite: L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        maxZoom: 19,
        attribution: "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
      }
    ),
    streets: L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
      {
        maxZoom: 19,
        attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"
      }
    )
  };

  const state = {
    activeGrower: null,
    activeFieldKey: null,
    basemap: "satellite",
    dossierOpen: false,
    activeTab: "overview",
    gallery: [],
    galleryIndex: 0,
    viewerZoom: 1
  };
  let internalHash = false;
  let lastDossierFocus = null;

  const growersBySlug = new Map();
  const fieldViews = [];
  const fieldsByKey = new Map();
  const layersByKey = new Map();
  const visibleLayer = L.layerGroup().addTo(map);
  const appNode = document.getElementById("app");
  const dossierNode = document.getElementById("dossier");
  const dossierBody = document.getElementById("dossier-body");
  const viewerNode = document.getElementById("viewer");
  const viewerImage = document.getElementById("viewer-image");
  const viewerStage = document.getElementById("viewer-stage");
  const viewerCaption = document.getElementById("viewer-caption");
  const viewerOriginal = document.getElementById("viewer-original");

  const ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return ESCAPES[char];
    });
  }

  function formatAcres(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return "—";
    }
    return number.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }

  function growerLabel(grower) {
    const short = String(grower.slug).replace(/-grower$/i, "").toUpperCase();
    return short || String(grower.slug).toUpperCase();
  }

  function fieldKey(grower, farm, field) {
    return grower.slug + "::" + farm.slug + "::" + field.id;
  }

  function isFlatCopy() {
    const path = window.location.pathname || "";
    const file = path.replace(/^.*\//, "");
    const dir = path.replace(/[^/]*$/, "");
    // Runtime output nests the combined map under growers/ and each grower map
    // under reports/. Anything else is treated as a copied, self-contained map.
    if (DATA.mode === "combined") {
      return !(/^growers_field_map\.html$/i.test(file) && /\/growers\/$/i.test(dir));
    }
    return !(/_field_map\.html$/i.test(file) && /\/reports\/$/i.test(dir));
  }

  function encodePath(path) {
    return String(path).split("/").map(encodeURIComponent).join("/");
  }

  function assetBase(view) {
    if (!view.field.asset_dir || isFlatCopy()) {
      return null;
    }
    if (DATA.mode === "combined") {
      return "./" + encodeURIComponent(view.grower.slug) + "/" +
        encodePath(view.field.asset_dir) + "/";
    }
    return "../../" + encodePath(view.field.asset_dir) + "/";
  }

  function figureSrc(view, figure) {
    if (figure.src) {
      return figure.src;
    }
    const base = assetBase(view);
    return base ? base + encodePath(figure.file) : "";
  }

  function figureOriginalUrl(view, file) {
    const base = assetBase(view);
    return base ? base + encodePath(file) : "";
  }

  function formatBytes(bytes) {
    const number = Number(bytes);
    if (!Number.isFinite(number) || number <= 0) {
      return "";
    }
    if (number >= 1000 * 1000) {
      return (number / (1000 * 1000)).toFixed(1) + " MB";
    }
    return Math.round(number / 1000) + " KB";
  }

  function popupHtml(view) {
    const grower = view.grower;
    const farm = view.farm;
    const field = view.field;
    const location = [field.county, field.state].filter(Boolean).join(", ");
    const rows = [
      ["Grower", grower.display_name],
      ["Farm", farm.display_name],
      ["Field", field.id],
      ["Crop", field.crop],
      ["Area", formatAcres(field.area_acres) + " ac"],
      ["Location", location || "—"],
      ["Source", field.source || "—"]
    ];
    return '<div class="atlas-popup-content">' +
      '<p class="popup-kicker">Field record</p>' +
      "<h3>" + esc(field.id) + "</h3>" +
      "<dl>" + rows.map(function (row) {
        return "<div><dt>" + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd></div>";
      }).join("") + "</dl>" +
      '<div class="popup-actions"><button type="button" class="popup-open" data-field-key="' +
      esc(view.key) + '">Open field dossier →</button></div>' +
      "</div>";
  }

  function formatNumber(value, digits) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return "";
    }
    return number.toFixed(digits == null ? 1 : digits);
  }

  function chip(label, value, sub) {
    if (value == null || value === "") {
      return "";
    }
    return '<div class="chip"><dt>' + esc(label) + "</dt><dd>" + esc(value) +
      (sub ? " <small>" + esc(sub) + "</small>" : "") + "</dd></div>";
  }

  function chipGrid(items) {
    const markup = items.filter(Boolean).join("");
    return markup ? '<div class="chip-grid">' + markup + "</div>" : "";
  }

  function soilSourceLabel(source) {
    const text = String(source || "").toLowerCase();
    if (/inta/.test(text)) {
      return "INTA Entre Ríos 1:100k";
    }
    if (/ssurgo/.test(text)) {
      return "USDA SSURGO";
    }
    return source || "";
  }

  function yearLabel(card) {
    if (!card || !card.years || !card.years.length) {
      return "";
    }
    return card.years.join(", ");
  }

  function figuresFor(view, group) {
    const figures = view.field.figures || [];
    return figures.filter(function (figure) {
      return figure.group === group;
    });
  }

  function figureGrid(view, figures, extraClass) {
    state.gallery = figures;
    if (!figures.length) {
      return '<div class="empty-state">No ' + esc(extraClass === "is-terrain" ? "terrain" : "figure") +
        " assets were generated for this field yet. Re-run the reporting pipeline to populate this tab.</div>";
    }
    return '<div class="figure-grid ' + esc(extraClass || "") + '">' +
      figures.map(function (figure, index) {
        const src = figureSrc(view, figure);
        const image = src
          ? '<img src="' + esc(src) + '" alt="' + esc(figure.label) + '" loading="lazy" decoding="async">'
          : '<div class="figure-missing">Figure file is available only in the runtime atlas.</div>';
        return '<button type="button" class="figure-card" data-gallery-index="' + index +
          '" aria-label="Open ' + esc(figure.label) + ' at full size">' +
          image +
          '<span class="figure-copy"><span class="figure-label">' + esc(figure.label) +
          '</span><span class="figure-caption">' + esc(figure.caption) + "</span></span></button>";
      }).join("") + "</div>";
  }

  function growerRelativeUrl(view, file) {
    if (isFlatCopy() || !file) {
      return "";
    }
    const prefix = DATA.mode === "combined"
      ? "./" + encodeURIComponent(view.grower.slug) + "/"
      : "../";
    return prefix + encodePath(file);
  }

  function downloadLinks(view, group) {
    const base = assetBase(view);
    const links = (view.field.downloads || []).filter(function (item) {
      return item.group === group;
    });
    if (!links.length) {
      return "";
    }
    if (!base) {
      return '<p class="dossier-note">Summary files live in the runtime atlas and are unavailable in a flat copy.</p>';
    }
    return '<ul class="link-list">' + links.map(function (item) {
      return '<li><a href="' + esc(base + encodePath(item.file)) + '" target="_blank" rel="noopener">' +
        esc(item.label) + "<span>Open file</span></a></li>";
    }).join("") + "</ul>";
  }

  function dossierRecord(view) {
    const field = view.field;
    const location = [field.county, field.state].filter(Boolean).join(", ");
    const rows = [
      ["Grower", view.grower.display_name],
      ["Farm", view.farm.display_name],
      ["Field", field.id],
      ["Crop", field.crop],
      ["Area", formatAcres(field.area_acres) + " ac"],
      ["Location", location || "—"],
      ["Source", field.source || "—"]
    ];
    return '<dl class="dossier-record">' + rows.map(function (row) {
      return "<div><dt>" + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd></div>";
    }).join("") + "</dl>";
  }

  function renderOverview(view) {
    const stats = view.field.stats || {};
    const soil = stats.soil || {};
    const ndvi = stats.ndvi || {};
    const terrain = stats.terrain || {};
    const corn = ndvi.corn || {};
    const soy = ndvi.soybean || {};
    const cornPeak = ndvi.corn_peak_95 || {};
    const soyPeak = ndvi.soybean_peak_95 || {};
    const terrainRange = terrain.range_m == null ? "" : formatNumber(terrain.range_m, 1) + " m";
    const chips = chipGrid([
      chip("Dominant soil", soil.dominant_soil),
      chip("Drainage", soil.drainage_class),
      chip("Organic matter", soil.avg_om_pct == null ? "" : formatNumber(soil.avg_om_pct, 1), "%"),
      chip("Soil pH", soil.avg_ph == null ? "" : formatNumber(soil.avg_ph, 1)),
      chip("Corn mean NDVI", corn.mean_ndvi == null ? "" : formatNumber(corn.mean_ndvi, 2), yearLabel(corn)),
      chip("Soybean mean NDVI", soy.mean_ndvi == null ? "" : formatNumber(soy.mean_ndvi, 2), yearLabel(soy)),
      chip("Corn peak NDVI", cornPeak.mean_ndvi == null ? "" : formatNumber(cornPeak.mean_ndvi, 2)),
      chip("Soybean peak NDVI", soyPeak.mean_ndvi == null ? "" : formatNumber(soyPeak.mean_ndvi, 2)),
      chip("Elevation range", terrainRange),
      chip("Terrain products", terrain.product_count == null ? "" : String(terrain.product_count))
    ]);
    const links = assetBase(view)
      ? downloadLinks(view, "soil") + downloadLinks(view, "ndvi") + downloadLinks(view, "terrain")
      : '<p class="dossier-note">Summary files live in the runtime atlas and are unavailable in a flat copy.</p>';
    return '<section class="dossier-section"><h3>Field record</h3>' + dossierRecord(view) + "</section>" +
      (chips ? '<section class="dossier-section"><h3>At a glance</h3>' + chips + "</section>" : "") +
      '<section class="dossier-section"><h3>Source tables</h3>' +
      (links || '<p class="dossier-note">No summary tables were generated for this field yet.</p>') +
      "</section>";
  }

  function renderNdvi(view) {
    const ndvi = (view.field.stats || {}).ndvi || {};
    const corn = ndvi.corn || {};
    const soy = ndvi.soybean || {};
    const cornPeak = ndvi.corn_peak_95 || {};
    const soyPeak = ndvi.soybean_peak_95 || {};
    const chips = chipGrid([
      chip("Corn years", yearLabel(corn)),
      chip("Corn mean NDVI", corn.mean_ndvi == null ? "" : formatNumber(corn.mean_ndvi, 3)),
      chip("Soybean years", yearLabel(soy)),
      chip("Soybean mean NDVI", soy.mean_ndvi == null ? "" : formatNumber(soy.mean_ndvi, 3)),
      chip("Corn peak scenes", cornPeak.scene_count == null ? "" : String(cornPeak.scene_count)),
      chip("Soybean peak scenes", soyPeak.scene_count == null ? "" : String(soyPeak.scene_count))
    ]);
    return '<section class="dossier-section"><h3>Seasonal signal</h3>' + chips + "</section>" +
      '<section class="dossier-section"><h3>NDVI figures</h3>' +
      figureGrid(view, figuresFor(view, "ndvi")) + "</section>" +
      '<section class="dossier-section"><h3>Source table</h3>' +
      (downloadLinks(view, "ndvi") || '<p class="dossier-note">NDVI summary JSON not available.</p>') +
      "</section>";
  }

  function renderSoil(view) {
    const soil = (view.field.stats || {}).soil || {};
    const chips = chipGrid([
      chip("Source", soilSourceLabel(soil.soil_source)),
      chip("Dominant soil", soil.dominant_soil),
      chip("Drainage", soil.drainage_class),
      chip("Erosion risk", soil.erosion_risk),
      chip("pH constraint", soil.ph_constraint),
      chip("Organic matter", soil.avg_om_pct == null ? "" : formatNumber(soil.avg_om_pct, 1), "%"),
      chip("Soil pH", soil.avg_ph == null ? "" : formatNumber(soil.avg_ph, 1)),
      chip("CEC", soil.avg_cec == null ? "" : formatNumber(soil.avg_cec, 1)),
      chip("Available water", soil.total_aws_inches == null ? "" : formatNumber(soil.total_aws_inches, 1), "in"),
      chip("Clay", soil.avg_clay_pct == null ? "" : formatNumber(soil.avg_clay_pct, 1), "%"),
      chip("Sand", soil.avg_sand_pct == null ? "" : formatNumber(soil.avg_sand_pct, 1), "%"),
      chip("Components / horizons", soil.n_components == null ? "" :
        String(soil.n_components) + " / " + String(soil.n_horizons == null ? "—" : soil.n_horizons))
    ]);
    return '<section class="dossier-section"><h3>Soil profile</h3>' + chips + "</section>" +
      '<section class="dossier-section"><h3>Soil figures</h3>' +
      figureGrid(view, figuresFor(view, "soil")) + "</section>" +
      '<section class="dossier-section"><h3>Source table</h3>' +
      (downloadLinks(view, "soil") || '<p class="dossier-note">Soil summary CSV not available.</p>') +
      "</section>" +
      '<p class="dossier-note">This field uses ' + esc(soilSourceLabel(soil.soil_source) || "the available soil survey") +
      ". Figure titles may retain the internal source filename convention.</p>";
  }

  function renderTerrain(view) {
    const terrain = (view.field.stats || {}).terrain || {};
    const chips = chipGrid([
      chip("Elevation range", terrain.range_m == null ? "" : formatNumber(terrain.range_m, 1), "m"),
      chip("Lowest point", terrain.min_m == null ? "" : formatNumber(terrain.min_m, 1), "m"),
      chip("Highest point", terrain.max_m == null ? "" : formatNumber(terrain.max_m, 1), "m"),
      chip("Derived products", terrain.product_count == null ? "" : String(terrain.product_count))
    ]);
    const figures = figuresFor(view, "terrain");
    return '<section class="dossier-section"><h3>Elevation</h3>' + chips + "</section>" +
      '<section class="dossier-section"><h3>Terrain figures</h3>' +
      figureGrid(view, figures, "is-terrain") + "</section>" +
      '<p class="dossier-note">Hydrology and erosion layers are advisory terrain proxies, not engineered drainage or soil-loss designs. ' +
      esc(terrain.advisory || "") + "</p>" +
      '<section class="dossier-section"><h3>Source table</h3>' +
      (downloadLinks(view, "terrain") || '<p class="dossier-note">Terrain summary JSON not available.</p>') +
      "</section>";
  }

  function renderReport(view) {
    const figures = figuresFor(view, "report");
    const farmReport = view.farm.farm_report;
    const farmUrl = farmReport ? growerRelativeUrl(view, farmReport.file) : "";
    const fieldFigure = figures.length ? figures[0] : null;
    const fieldUrl = fieldFigure ? figureOriginalUrl(view, fieldFigure.file) : "";
    let farmCard = "";
    if (farmReport) {
      const size = formatBytes(farmReport.bytes);
      farmCard = '<div class="report-card"><h3>Farm report</h3>' +
        '<p><span class="warn">Large file:</span> the farm-level HTML report bundles ' +
        "every field, soil, weather, and poster figure. Farm reports typically run " +
        "61–74 MB" + (size ? " (this one is " + esc(size) + ")" : "") +
        ", so open it only when you need the full farm view.</p>" +
        (farmUrl
          ? '<a href="' + esc(farmUrl) + '" target="_blank" rel="noopener">Open farm report ↗</a>'
          : '<p class="dossier-note">Farm report links are available only in the runtime atlas.</p>') +
        "</div>";
    }
    return '<section class="dossier-section"><h3>Field intelligence poster</h3>' +
      figureGrid(view, figures) +
      (fieldUrl
        ? '<p class="dossier-note"><a href="' + esc(fieldUrl) + '" target="_blank" rel="noopener">Open full-resolution field report PNG ↗</a></p>'
        : '<p class="dossier-note">Full-resolution links are available only in the runtime atlas.</p>') +
      "</section>" +
      (farmCard ? '<section class="dossier-section">' + farmCard + "</section>" : "");
  }

  function renderTab(view, tab) {
    if (tab === "ndvi") {
      return renderNdvi(view);
    }
    if (tab === "soil") {
      return renderSoil(view);
    }
    if (tab === "terrain") {
      return renderTerrain(view);
    }
    if (tab === "report") {
      return renderReport(view);
    }
    return renderOverview(view);
  }

  function renderDossier() {
    const view = state.activeFieldKey ? fieldsByKey.get(state.activeFieldKey) : null;
    if (!view) {
      return;
    }
    document.getElementById("dossier-title").textContent = view.field.id;
    document.getElementById("dossier-sub").textContent = [
      view.farm.display_name,
      view.field.crop,
      formatAcres(view.field.area_acres) + " ac",
      [view.field.county, view.field.state].filter(Boolean).join(", ")
    ].filter(Boolean).join(" · ");
    state.gallery = [];
    dossierBody.innerHTML = renderTab(view, state.activeTab);
    dossierBody.scrollTop = 0;
    document.querySelectorAll("#dossier-tabs .dossier-tab").forEach(function (button) {
      const active = button.dataset.tab === state.activeTab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
  }

  function openDossier(view, tab, options) {
    if (!view) {
      return;
    }
    const opts = Object.assign({ writeHash: true }, options || {});
    const alreadyOpen = state.dossierOpen;
    map.closePopup();
    state.dossierOpen = true;
    state.activeTab = tab || (alreadyOpen ? state.activeTab : "overview") || "overview";
    if (!alreadyOpen) {
      lastDossierFocus = document.activeElement;
    }
    appNode.classList.add("dossier-open");
    dossierNode.hidden = false;
    document.getElementById("dossier-backdrop").hidden = false;
    renderDossier();
    const activeTab = dossierNode.querySelector(".dossier-tab.is-active");
    if (activeTab) {
      activeTab.focus({ preventScroll: true });
    }
    if (opts.writeHash) {
      writeHash();
    }
  }

  function closeDossier(options) {
    const opts = Object.assign({ writeHash: true, restoreFocus: true }, options || {});
    if (!state.dossierOpen) {
      return;
    }
    state.dossierOpen = false;
    appNode.classList.remove("dossier-open");
    window.setTimeout(function () {
      if (!state.dossierOpen) {
        dossierNode.hidden = true;
        document.getElementById("dossier-backdrop").hidden = true;
      }
    }, 240);
    if (opts.restoreFocus && lastDossierFocus && typeof lastDossierFocus.focus === "function") {
      lastDossierFocus.focus({ preventScroll: true });
    }
    if (opts.writeHash) {
      writeHash();
    }
  }

  function setTab(tab, options) {
    if (!tab) {
      return;
    }
    state.activeTab = tab;
    renderDossier();
    const opts = Object.assign({ writeHash: true }, options || {});
    if (opts.writeHash) {
      writeHash();
    }
  }

  function applyViewerZoom() {
    if (state.viewerZoom <= 1) {
      viewerStage.classList.remove("is-zoomed");
      viewerImage.style.width = "";
      return;
    }
    viewerStage.classList.add("is-zoomed");
    viewerImage.style.width = (state.viewerZoom * 100) + "%";
  }

  function updateViewer() {
    const figure = state.gallery[state.galleryIndex];
    if (!figure) {
      return;
    }
    const view = state.activeFieldKey ? fieldsByKey.get(state.activeFieldKey) : null;
    const src = view ? figureSrc(view, figure) : "";
    viewerImage.src = src || "";
    viewerImage.alt = figure.label;
    viewerCaption.textContent = figure.label;
    const original = view ? figureOriginalUrl(view, figure.file) : "";
    if (original) {
      viewerOriginal.href = original;
      viewerOriginal.hidden = false;
    } else {
      viewerOriginal.hidden = true;
      viewerOriginal.href = "#";
    }
    document.getElementById("viewer-prev").disabled = state.galleryIndex <= 0;
    document.getElementById("viewer-next").disabled = state.galleryIndex >= state.gallery.length - 1;
    applyViewerZoom();
  }

  function openViewer(index) {
    if (!state.gallery.length) {
      return;
    }
    state.galleryIndex = Math.max(0, Math.min(index, state.gallery.length - 1));
    state.viewerZoom = 1;
    updateViewer();
    if (typeof viewerNode.showModal === "function") {
      viewerNode.showModal();
    } else {
      viewerNode.setAttribute("open", "");
    }
  }

  function setViewerZoom(next) {
    state.viewerZoom = Math.max(1, Math.min(4, next));
    applyViewerZoom();
  }

  function stepViewer(delta) {
    const next = state.galleryIndex + delta;
    if (next < 0 || next >= state.gallery.length) {
      return;
    }
    state.galleryIndex = next;
    state.viewerZoom = 1;
    updateViewer();
  }

  function closeViewer() {
    if (typeof viewerNode.close === "function") {
      viewerNode.close();
    } else {
      viewerNode.removeAttribute("open");
    }
    state.viewerZoom = 1;
    viewerStage.classList.remove("is-zoomed");
    viewerImage.style.width = "";
  }

  function applyBaseStyle(view) {
    view.layer.setStyle({
      color: view.field.color,
      weight: 1.7,
      opacity: 0.95,
      fillColor: view.field.color,
      fillOpacity: 0.36
    });
  }

  function applySelectedStyle(view) {
    view.layer.setStyle({
      color: "#1f2418",
      weight: 5,
      opacity: 1,
      fillColor: view.field.color,
      fillOpacity: 0.58
    });
    view.layer.bringToFront();
  }

  DATA.growers.forEach(function (grower) {
    growersBySlug.set(grower.slug, grower);
    grower.farms.forEach(function (farm) {
      farm.fields.forEach(function (field) {
        const key = fieldKey(grower, farm, field);
        const view = { key: key, grower: grower, farm: farm, field: field, layer: null };
        fieldViews.push(view);
        fieldsByKey.set(key, view);

        const layer = L.geoJSON(
          { type: "Feature", properties: {}, geometry: field.geometry },
          {
            style: {
              color: field.color,
              weight: 1.7,
              opacity: 0.95,
              fillColor: field.color,
              fillOpacity: 0.36
            }
          }
        );
        layer.bindPopup(popupHtml(view), { maxWidth: 380, autoPan: false });
        layer.on("click", function () {
          // Leaflet's own bindPopup click handler opens the popup first; do not
          // open it again here, because a second open re-renders its content.
          selectField(key, { zoom: true, writeHash: true, openPopup: false });
        });
        layer.on("mouseover", function () {
          if (state.activeFieldKey !== key) {
            layer.setStyle({ weight: 2.6, fillOpacity: 0.52 });
          }
        });
        layer.on("mouseout", function () {
          if (state.activeFieldKey !== key) {
            applyBaseStyle(view);
          }
        });
        view.layer = layer;
        layersByKey.set(key, layer);
      });
    });
  });

  function activeFieldsFor(growerSlug) {
    if (growerSlug === "all") {
      return fieldViews;
    }
    return fieldViews.filter(function (view) {
      return view.grower.slug === growerSlug;
    });
  }

  function currentGrower() {
    return growersBySlug.get(state.activeGrower);
  }

  function renderGrowerSwitcher() {
    const switcher = document.getElementById("grower-switcher");
    if (DATA.mode !== "combined") {
      switcher.hidden = true;
      return;
    }
    switcher.hidden = false;
    switcher.innerHTML = "";

    DATA.growers.forEach(function (grower) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "pill";
      button.dataset.grower = grower.slug;
      button.textContent = growerLabel(grower);
      button.title = grower.display_name;
      button.setAttribute("aria-label", "Show " + grower.display_name);
      switcher.appendChild(button);
    });

    const allButton = document.createElement("button");
    allButton.type = "button";
    allButton.className = "pill";
    allButton.dataset.grower = "all";
    allButton.textContent = "ALL";
    allButton.title = "All growers";
    allButton.setAttribute("aria-label", "Show all growers");
    switcher.appendChild(allButton);
  }

  function renderFieldList() {
    const container = document.getElementById("field-list");
    const groups = state.activeGrower === "all"
      ? DATA.growers
      : [currentGrower()].filter(Boolean);

    let markup = "";
    groups.forEach(function (grower) {
      if (state.activeGrower === "all") {
        markup += '<div class="grower-heading"><span>' + esc(grower.display_name) +
          "</span><span>" + grower.field_count + " fields</span></div>";
      }
      grower.farms.forEach(function (farm) {
        markup += '<div class="farm-group">' +
          '<div class="farm-group-head"><span>' + esc(farm.display_name) +
          "</span><span>" + farm.fields.length + " fields</span></div>";
        farm.fields.forEach(function (field) {
          const key = fieldKey(grower, farm, field);
          const active = key === state.activeFieldKey ? " is-active" : "";
          markup += '<button type="button" class="field-row' + active +
            '" data-field-key="' + esc(key) + '">' +
            '<span class="swatch" style="--swatch:' + esc(field.color) + '"></span>' +
            '<span class="field-copy">' +
            '<span class="field-name">' + esc(field.id) + "</span>" +
            '<span class="field-detail">' + esc(field.crop) + " · " +
            esc(formatAcres(field.area_acres)) + " ac</span>" +
            "</span>" +
            '<span class="field-arrow" aria-hidden="true">→</span>' +
            "</button>";
        });
        markup += "</div>";
      });
    });
    container.innerHTML = markup;
  }

  function updatePanel() {
    const title = document.getElementById("active-title");
    const subtitle = document.getElementById("active-subtitle");
    const kicker = document.getElementById("meta-kicker");
    const link = document.getElementById("standalone-link");

    const flat = isFlatCopy();

    if (state.activeGrower === "all") {
      title.textContent = "All growers";
      subtitle.textContent = fieldViews.length + " fields across " + DATA.growers.length + " growers";
      kicker.textContent = "Combined view";
      link.hidden = true;
    } else {
      const grower = currentGrower();
      if (!grower) {
        return;
      }
      title.textContent = grower.display_name;
      subtitle.textContent = grower.field_count + " fields · " +
        grower.farms.map(function (farm) { return farm.display_name; }).join(" · ");
      kicker.textContent = DATA.mode === "combined" ? "Selected grower" : "Grower";

      const selected = state.activeFieldKey ? fieldsByKey.get(state.activeFieldKey) : null;
      const fieldHash = selected ? "#field=" + encodeURIComponent(selected.field.id) : "";
      if (DATA.mode === "single" && DATA.combinedAvailable === false) {
        link.hidden = true;
      } else {
        link.hidden = false;
        if (DATA.mode === "combined") {
          link.textContent = "Open standalone grower map ↗";
          link.href = (flat
            ? "./" + encodeURIComponent(grower.slug) + "_field_map.html"
            : "./" + encodeURIComponent(grower.slug) + "/reports/" +
              encodeURIComponent(grower.slug) + "_field_map.html") + fieldHash;
        } else {
          link.textContent = "Open combined atlas ↗";
          link.href = (flat ? "./" : "../../") + "growers_field_map.html#grower=" +
            encodeURIComponent(grower.slug) + (selected ? "&field=" + encodeURIComponent(selected.field.id) : "");
        }
      }
    }

    if (DATA.mode === "combined") {
      document.querySelectorAll("#grower-switcher .pill").forEach(function (button) {
        const active = button.dataset.grower === state.activeGrower;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }
  }

  function updateCaption() {
    const activeFields = state.activeGrower ? activeFieldsFor(state.activeGrower) : [];
    const grower = currentGrower();
    const label = state.activeGrower === "all"
      ? "All growers"
      : (grower ? grower.display_name : "Field Atlas");
    const basemap = state.basemap === "satellite" ? "Esri World Imagery" : "Esri World Street Map";
    document.getElementById("map-caption").textContent =
      label + " · " + activeFields.length + " fields · " + basemap;
  }

  function fitCurrent(animate) {
    const views = activeFieldsFor(state.activeGrower);
    if (!views.length) {
      return;
    }
    const bounds = L.latLngBounds([]);
    views.forEach(function (view) {
      bounds.extend(view.layer.getBounds());
    });
    if (!bounds.isValid()) {
      return;
    }
    const options = {
      padding: [40, 40],
      maxZoom: state.activeGrower === "all" ? 5 : 14
    };
    if (animate) {
      map.flyToBounds(bounds, options);
    } else {
      map.fitBounds(bounds, options);
    }
  }

  function readHash() {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    return {
      grower: params.get("grower"),
      field: params.get("field"),
      tab: params.get("tab")
    };
  }

  function writeHash() {
    const params = new URLSearchParams();
    if (DATA.mode === "combined") {
      params.set("grower", state.activeGrower);
    }
    if (state.activeFieldKey) {
      const view = fieldsByKey.get(state.activeFieldKey);
      if (view) {
        params.set("field", view.field.id);
      }
    }
    if (state.dossierOpen && state.activeFieldKey) {
      params.set("tab", state.activeTab);
    }
    const query = params.toString();
    const base = window.location.href.split("#")[0];
    const next = query ? "#" + query : base;
    if (window.location.href === next) {
      return;
    }
    try {
      window.history.replaceState(null, "", next);
    } catch (error) {
      // file:// documents can reject History API URL changes.
      const fallback = query ? "#" + query : "";
      if (window.location.hash !== fallback) {
        internalHash = true;
        window.location.hash = fallback;
      }
    }
  }

  function setView(growerSlug, options) {
    const opts = Object.assign({ writeHash: true, fit: true, animate: false }, options || {});

    if (DATA.mode === "combined") {
      if (growerSlug !== "all" && !growersBySlug.has(growerSlug)) {
        return;
      }
    } else {
      growerSlug = DATA.growers[0].slug;
    }

    if (state.dossierOpen) {
      closeDossier({ writeHash: false, restoreFocus: false });
    }
    state.activeGrower = growerSlug;
    state.activeFieldKey = null;
    state.activeTab = "overview";
    visibleLayer.clearLayers();

    activeFieldsFor(growerSlug).forEach(function (view) {
      applyBaseStyle(view);
      visibleLayer.addLayer(view.layer);
    });

    renderFieldList();
    updatePanel();
    updateCaption();
    if (opts.fit) {
      fitCurrent(opts.animate);
    }
    if (opts.writeHash) {
      writeHash();
    }
  }

  function selectField(key, options) {
    const view = fieldsByKey.get(key);
    if (!view) {
      return;
    }
    const opts = Object.assign(
      { zoom: true, writeHash: true, openPopup: true, openDossier: false },
      options || {}
    );

    if (state.activeGrower !== "all" && view.grower.slug !== state.activeGrower) {
      setView(view.grower.slug, { writeHash: false, fit: false });
    }

    if (state.activeFieldKey && state.activeFieldKey !== key) {
      const previous = fieldsByKey.get(state.activeFieldKey);
      if (previous) {
        applyBaseStyle(previous);
      }
    }

    state.activeFieldKey = key;
    applySelectedStyle(view);
    if (!visibleLayer.hasLayer(view.layer)) {
      visibleLayer.addLayer(view.layer);
    }

    if (opts.zoom) {
      const wide = opts.openDossier && window.matchMedia("(min-width: 861px)").matches;
      map.flyToBounds(view.layer.getBounds(), {
        paddingTopLeft: [30, 30],
        paddingBottomRight: wide ? [600, 30] : [70, 70],
        maxZoom: 16,
        duration: 0.55
      });
    }
    if (opts.openPopup && !opts.openDossier) {
      view.layer.openPopup();
    } else if (opts.openDossier) {
      map.closePopup();
    }

    renderFieldList();
    updatePanel();
    if (opts.openDossier) {
      openDossier(view, state.activeTab, { writeHash: false });
    }
    if (opts.writeHash) {
      writeHash();
    }
  }

  function applyHash() {
    const parsed = readHash();
    let grower = DATA.mode === "combined"
      ? (parsed.grower || DATA.defaultGrower)
      : DATA.growers[0].slug;

    if (DATA.mode === "combined" && grower !== "all" && !growersBySlug.has(grower)) {
      grower = DATA.defaultGrower || DATA.growers[0].slug;
    }

    const validTabs = ["overview", "ndvi", "soil", "terrain", "report"];
    const activeTab = parsed.tab && validTabs.indexOf(parsed.tab) !== -1 ? parsed.tab : null;
    const fieldPool = grower === "all"
      ? fieldViews
      : fieldViews.filter(function (view) { return view.grower.slug === grower; });
    const target = parsed.field
      ? (fieldPool.find(function (view) { return view.field.id === parsed.field; }) ||
        fieldViews.find(function (view) { return view.field.id === parsed.field; }))
      : null;

    if (target) {
      if (grower !== "all") {
        grower = target.grower.slug;
      }
      setView(grower, { writeHash: false, fit: false });
      selectField(target.key, { zoom: true, writeHash: false, openPopup: !activeTab });
      if (activeTab) {
        openDossier(target, activeTab, { writeHash: false });
      } else if (state.dossierOpen) {
        closeDossier({ writeHash: false, restoreFocus: false });
      }
      return;
    }

    if (state.dossierOpen) {
      closeDossier({ writeHash: false, restoreFocus: false });
    }
    setView(grower, { writeHash: false, fit: true, animate: false });
  }

  function setBasemap(name) {
    if (name === state.basemap) {
      return;
    }
    const previous = basemaps[state.basemap];
    if (previous) {
      map.removeLayer(previous);
    }
    state.basemap = name;
    basemaps[name].addTo(map);
    basemaps[name].bringToBack();
    document.querySelectorAll("#basemap-toggle button").forEach(function (button) {
      const active = button.dataset.basemap === name;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    updateCaption();
  }

  renderGrowerSwitcher();
  basemaps.satellite.addTo(map);

  document.getElementById("grower-switcher").addEventListener("click", function (event) {
    const button = event.target.closest("button[data-grower]");
    if (!button) {
      return;
    }
    setView(button.dataset.grower, { writeHash: true, fit: true, animate: true });
  });

  document.getElementById("field-list").addEventListener("click", function (event) {
    const button = event.target.closest("button[data-field-key]");
    if (!button) {
      return;
    }
    selectField(button.dataset.fieldKey, {
      zoom: true,
      writeHash: true,
      openDossier: true
    });
  });

  // Leaflet popups recreate their DOM content after opening and stop click
  // propagation, so catch the dossier button in the document capture phase.
  document.addEventListener("click", function (event) {
    const button = event.target.closest ? event.target.closest(".popup-open") : null;
    if (!button) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const target = fieldsByKey.get(button.dataset.fieldKey);
    if (!target) {
      return;
    }
    map.closePopup();
    selectField(target.key, {
      zoom: true,
      writeHash: true,
      openDossier: true,
      openPopup: false
    });
  }, true);

  document.getElementById("dossier-close").addEventListener("click", function () {
    closeDossier();
  });
  document.getElementById("dossier-backdrop").addEventListener("click", function () {
    closeDossier();
  });
  document.getElementById("dossier-tabs").addEventListener("click", function (event) {
    const button = event.target.closest("button[data-tab]");
    if (button) {
      setTab(button.dataset.tab);
    }
  });
  document.getElementById("dossier-tabs").addEventListener("keydown", function (event) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") {
      return;
    }
    const tabs = Array.prototype.slice.call(
      document.querySelectorAll("#dossier-tabs .dossier-tab")
    );
    const index = tabs.indexOf(document.activeElement);
    if (index === -1) {
      return;
    }
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : tabs.length - 1;
    const next = tabs[(index + delta) % tabs.length];
    next.focus();
    setTab(next.dataset.tab);
  });
  dossierBody.addEventListener("click", function (event) {
    const card = event.target.closest("[data-gallery-index]");
    if (card) {
      openViewer(Number(card.dataset.galleryIndex));
    }
  });
  dossierNode.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      event.stopPropagation();
      closeDossier();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    const focusable = Array.prototype.filter.call(
      dossierNode.querySelectorAll(
        'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
      ),
      function (node) {
        return node.offsetParent !== null;
      }
    );
    if (!focusable.length) {
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  document.getElementById("viewer-close").addEventListener("click", closeViewer);
  document.getElementById("viewer-prev").addEventListener("click", function () {
    stepViewer(-1);
  });
  document.getElementById("viewer-next").addEventListener("click", function () {
    stepViewer(1);
  });
  document.getElementById("viewer-zoom-in").addEventListener("click", function () {
    setViewerZoom(state.viewerZoom + 0.5);
  });
  document.getElementById("viewer-zoom-out").addEventListener("click", function () {
    setViewerZoom(state.viewerZoom - 0.5);
  });
  viewerImage.addEventListener("click", function () {
    setViewerZoom(state.viewerZoom > 1 ? 1 : 2);
  });
  viewerNode.addEventListener("keydown", function (event) {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      stepViewer(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepViewer(-1);
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      setViewerZoom(state.viewerZoom + 0.5);
    } else if (event.key === "-") {
      event.preventDefault();
      setViewerZoom(state.viewerZoom - 0.5);
    }
  });
  viewerNode.addEventListener("click", function (event) {
    if (event.target === viewerNode) {
      closeViewer();
    }
  });
  viewerNode.addEventListener("close", function () {
    state.viewerZoom = 1;
    viewerStage.classList.remove("is-zoomed");
    viewerImage.style.width = "";
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && state.dossierOpen && !viewerNode.open) {
      closeDossier();
    }
  });

  document.getElementById("basemap-toggle").addEventListener("click", function (event) {
    const button = event.target.closest("button[data-basemap]");
    if (button) {
      setBasemap(button.dataset.basemap);
    }
  });

  document.getElementById("fit-all").addEventListener("click", function () {
    fitCurrent(true);
  });

  window.addEventListener("hashchange", function () {
    if (internalHash) {
      internalHash = false;
      return;
    }
    applyHash();
  });
  applyHash();
})();
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Field Atlas web maps for grower field boundaries."
    )
    parser.add_argument(
        "--grower",
        action="append",
        dest="growers",
        metavar="SLUG",
        help="Grower slug to render. Repeat for multiple growers. Defaults to all growers.",
    )
    parser.add_argument(
        "--all-growers",
        action="store_true",
        help="Render every grower with boundary data (the default when --grower is omitted).",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        default=True,
        help="Also write the combined growers map (default).",
    )
    parser.add_argument(
        "--no-combined",
        action="store_false",
        dest="combined",
        help="Skip the combined growers map.",
    )
    parser.add_argument(
        "--no-embed-figures",
        action="store_false",
        dest="embed_figures",
        help=(
            "Link report figures instead of embedding portable WebP previews. "
            "Keeps the HTML small but figures only resolve in the runtime layout."
        ),
    )
    parser.add_argument(
        "--figure-max-width",
        type=int,
        default=DEFAULT_FIGURE_MAX_WIDTH,
        metavar="PX",
        help=f"Maximum embedded figure width in pixels (default {DEFAULT_FIGURE_MAX_WIDTH}).",
    )
    parser.add_argument(
        "--figure-quality",
        type=int,
        default=DEFAULT_FIGURE_QUALITY,
        metavar="N",
        help=f"Embedded WebP quality, 1-100 (default {DEFAULT_FIGURE_QUALITY}).",
    )
    args = parser.parse_args(argv)

    if args.all_growers and args.growers:
        parser.error("--all-growers cannot be combined with --grower")
    if args.figure_max_width < 320:
        parser.error("--figure-max-width must be at least 320")
    if not 1 <= args.figure_quality <= 100:
        parser.error("--figure-quality must be between 1 and 100")
    if args.embed_figures and not _pillow_available():
        parser.error("Pillow is required for embedded figures; install it or pass --no-embed-figures")

    if args.all_growers or not args.growers:
        slugs = discover_growers()
    else:
        slugs = sorted(dict.fromkeys(args.growers), key=_natural_key)

    if not slugs:
        print(
            f"error: no growers with field boundaries under {GROWERS_ROOT}",
            file=sys.stderr,
        )
        return 1

    growers: list[dict[str, Any]] = []
    for slug in slugs:
        try:
            grower = load_grower(
                slug,
                embed_figures=args.embed_figures,
                figure_max_width=args.figure_max_width,
                figure_quality=args.figure_quality,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime boundary
            print(f"warn  {slug}: {exc}", file=sys.stderr)
            continue
        if grower is None:
            print(f"skip  {slug}: no usable field boundaries", file=sys.stderr)
            continue
        growers.append(grower)

    if not growers:
        print("error: no usable grower field boundaries found", file=sys.stderr)
        return 1

    for grower in growers:
        output_path = grower_report_path(
            grower["slug"], f"{grower['slug']}_field_map.html"
        )
        _write_text(
            output_path,
            render_html(_single_payload(grower, combined_available=args.combined)),
        )
        print(f"wrote {output_path} ({grower['field_count']} fields)")

    if args.combined:
        combined_path = growers_overview_path(COMBINED_FILENAME)
        combined_payload = _combined_payload(growers)
        _write_text(combined_path, render_html(combined_payload))

        figure_count = sum(
            len(field["figures"])
            for grower in growers
            for farm in grower["farms"]
            for field in farm["fields"]
        )
        manifest = {
            "generated_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "combined_html": COMBINED_FILENAME,
            "combined_bytes": combined_path.stat().st_size,
            "default_grower": combined_payload["defaultGrower"],
            "grower_count": len(growers),
            "field_count": sum(grower["field_count"] for grower in growers),
            "figure_count": figure_count,
            "figures_embedded": args.embed_figures,
            "growers": [
                {
                    "slug": grower["slug"],
                    "field_count": grower["field_count"],
                    "html": f"{grower['slug']}/reports/{grower['slug']}_field_map.html",
                }
                for grower in growers
            ],
        }
        manifest_path = growers_overview_path(MANIFEST_FILENAME)
        _write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")
        print(
            f"wrote {combined_path} "
            f"({manifest['grower_count']} growers, {manifest['field_count']} fields)"
        )
        print(f"wrote {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
