# Grower Web Map Guide

## Purpose

Build a **Field Atlas** view directly from canonical runtime field boundaries.
This workflow is for grower-level field review and sharing, not for soil,
weather, or crop-model analysis. It reads existing boundary data and does not
redownload or rebuild field polygons.

## Workflow

1. Confirm the runtime is installed and current.
2. Run the generator from the runtime source copy.
3. Open the per-grower map or the combined map in a browser.
4. Run the structural checks below, then `./scripts/validate.sh` from the repo.

### Install or refresh the runtime

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh --no-install-deps
```

The installer copies `src/` into `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`.
Run the generator from that copy, not from the checkout.

### Generate maps

```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py --all-growers --combined
```

Flags:

- `--grower SLUG` — render one grower; repeat for multiple growers.
- `--all-growers` — render every grower with boundary data (default when
  `--grower` is omitted).
- `--combined` — write the combined map (default).
- `--no-combined` — write only per-grower maps.
- `--no-embed-figures` — link dossier figures instead of embedding them.
- `--figure-max-width PX` — maximum embedded figure width (default `1600`).
- `--figure-quality N` — embedded WebP quality, 1–100 (default `88`).

`--all-growers` and `--grower` are mutually exclusive. Embedded figures require
Pillow; the generator errors with a clear message if it is missing and
`--no-embed-figures` was not passed.

## Output contract

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/
├── growers_field_map.html
├── growers_field_map.json
└── <grower>/reports/<grower>_field_map.html
```

The combined manifest records the generation time, default grower, grower and
field counts, `figure_count`, `figures_embedded`, `combined_bytes`, and each
standalone map path.

Generated HTML, JSON manifests, and runtime data stay outside Git.

## Map behavior

### Standalone grower map

- Opens fitted to every field for that grower.
- Field list is grouped by farm.
- Clicking a field list row flies to its bounds and opens the field dossier.
- Clicking a field polygon opens the compact popup; **Open field dossier**
  switches to the drawer.
- `Fit all` resets to the current grower.

### Combined map

- Grower pills switch between `il-grower`, `ia-grower`, `ar-grower`, and
  **ALL**.
- Default view is `il-grower` when present, otherwise the first discovered
  grower.
- **ALL** lists every field across growers and fits the world view. Clicking a
  field zooms in without leaving the all-growers view.
- The sidebar links to the selected grower's standalone map.
- Standalone maps link back to the combined atlas.
- Links resolve against the file's own folder. Nested runtime output uses
  `../../growers_field_map.html`; a flat folder containing all four HTML files
  uses the sibling `growers_field_map.html` and `<grower>_field_map.html`.

### Hash links

- Combined: `#grower=<slug>&field=<field_id>`
- Standalone: `#field=<field_id>`
- All growers: `#grower=all&field=<field_id>`
- Open dossier tab: append `&tab=<overview|ndvi|soil|terrain|report>`

Field clicks update the hash with `history.replaceState`. A manual hash change
or shared link restores the grower, field, and dossier tab.

### Field dossier

The dossier is a right-side drawer on wide screens and a bottom sheet on mobile.
It always has five tabs:

- **Overview** — field record, at-a-glance chips, and source-table links.
- **NDVI** — corn/soybean means and peak scenes, NDVI figures, summary JSON.
- **Soil** — source label, dominant soil, drainage, texture, water, chemistry,
  soil figures, and `ssurgo_summary.csv`.
- **Terrain** — elevation range, derived product count, terrain previews, and
  `dem_terrain_summary.json`. Copy calls the layers advisory proxies.
- **Report** — field poster preview, full-resolution PNG link, and farm report
  link with a visible size warning.

Figures open in a full-screen `<dialog>` viewer with previous/next, 1×–4× zoom,
keyboard arrows, and an **Open original** link. All figure previews are embedded
so the dossier survives copying the HTML file.

### Portable copies and runtime-only links

- Figures are embedded as base64 WebP (max width 1600 px, quality 88).
- The original PNG, CSV/JSON summaries, and farm report remain relative links
  into the runtime tree.
- A copied map is detected by its folder and filename. It still shows embedded
  figures but replaces runtime-only links with an explanatory note.
- When all four maps are copied into one folder, cross-links use sibling
  filenames.

## Visual language

The map deliberately avoids the yellow-on-satellite look of the generic
interactive web-map example:

- warm paper sidebar with subtle radial washes;
- serif display headings and small-caps labels;
- olive, amber, clay, sage, umber, and wheat field fills;
- cream paper popups with a field-record grid;
- a warm-paper dossier drawer with pill tabs, chips, and figure cards;
- custom pill basemap toggle instead of Leaflet's layer control;
- selected fields use a dark ink outline and stronger fill.

The design is self-contained CSS and vanilla JavaScript. Leaflet 1.9.4 loads
from unpkg. Basemap tiles load from Esri.

## Data handling

- Reads `grower.json`, `farm.json`, boundary GeoJSON, `field-inventory.csv`,
  and optional per-field `field.json` metadata.
- Resolves missing `field_slug` values from the inventory CSV.
- Prefers an explicit current crop from `fields/<field_slug>/field.json`
  (`crop_name`, `current_crop`, or `crop`) over the boundary properties. This
  is the correction path when imported or model-derived crop labels are
  missing or wrong.
- Supports `Polygon` and `MultiPolygon` geometries.
- Drops features with no `field_id` or unsupported geometry.
- Sorts growers, farms, and fields deterministically.
- Embeds only slim properties and geometry, not full source GeoJSON.
- Embeds compressed WebP previews of dossier figures; full-resolution PNGs stay
  on disk.
- Parses dossier stats from `soil/ssurgo_summary.csv`,
  `derived/summaries/ndvi_card_summary.json`, and
  `derived/tables/dem_terrain_summary.json`; missing files become empty tabs.
- Labels INTA-sourced AR soil as INTA while the files keep `ssurgo_*` names.
- Escapes `</` in the embedded JSON so field text cannot close the script tag.

With the current sample data the combined map is about 12 MB (153 embedded
figures); a standalone map is 3–5 MB. `--no-embed-figures` keeps a map under
100 KB. Basemap tiles are never embedded.

## Checks

After generation:

```bash
python3 - <<'PY'
import base64
import io
import json
import re
from pathlib import Path
from PIL import Image

root = Path.home() / "my-farm-advisor-runtime/data-pipeline/growers"


def payload(path):
    text = path.read_text(encoding="utf-8")
    match = re.search(r"const DATA = (\{.*?\});\n", text, re.S)
    return text, json.loads(match.group(1).replace("<\\/", "</"))


for name in ("il-grower", "ia-grower", "ar-grower"):
    path = root / name / "reports" / f"{name}_field_map.html"
    text, data = payload(path)
    fields = [f for farm in data["growers"][0]["farms"] for f in farm["fields"]]
    figures = [fig for f in fields for fig in f["figures"]]
    assert len(fields) == 3
    assert len(figures) == 51
    assert all(fig["src"].startswith("data:image/webp;base64,") for fig in figures)
    assert "World_Imagery" in text
    assert 'params.set("tab"' in text
    print(path.name, len(figures), "embedded figures", path.stat().st_size, "bytes")

combined = root / "growers_field_map.html"
text, data = payload(combined)
fields = [f for g in data["growers"] for farm in g["farms"] for f in farm["fields"]]
figures = [fig for f in fields for fig in f["figures"]]
assert len(fields) == 9
assert len(figures) == 153
assert data["defaultGrower"] == "il-grower"
image = Image.open(io.BytesIO(base64.b64decode(figures[0]["src"].split(",", 1)[1])))
assert image.format == "WEBP"
manifest = json.loads((root / "growers_field_map.json").read_text())
assert manifest["figure_count"] == 153
assert manifest["figures_embedded"] is True
print(combined.name, len(figures), "embedded figures", manifest["combined_bytes"], "bytes")
PY
```

Then run from the repository root:

```bash
./scripts/validate.sh
```

There is no headless browser in the standard environment. Structural checks
plus opening the map manually are the expected verification path.

## Troubleshooting

- **`DATA_PIPELINE_DATA_ROOT is required`** — export an absolute runtime path
  before running the generator.
- **No growers found** — confirm the runtime has
  `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`.
- **Missing `field_slug`** — add or refresh
  `manifests/field-inventory.csv`; the generator falls back to `field_id`.
- **Crop shows as `Unknown`** — add `crop_name` to
  `fields/<field_slug>/field.json` and regenerate. Field metadata overrides the
  boundary label.
- **Blank basemap** — the HTML loaded but tiles did not. Check the network and
  the Esri attribution in the browser console.
- **`Pillow is required for embedded figures`** — install pipeline
  requirements, or rerun with `--no-embed-figures`.
- **Dossier tab is empty** — the corresponding derived figures or summary files
  are missing in the field folder. Re-run the reporting pipeline for that field;
  partial fields render with the data they have.
- **Copied map shows "available only in the runtime atlas"** — expected: a
  copied HTML keeps embedded figures but not links to PNGs, CSVs, JSON, or the
  farm report. Open the map in its runtime folder for full links.
- **Farm report link is missing** — the farm HTML report has not been generated
  yet. It is runtime-only and may be 61–74 MB, so the map warns before opening.
- **Stale code in the runtime** — rerun `install.sh --force-refresh` before
  regenerating.
- **Grower/combined link points at the wrong folder** — regenerate the maps
  from the current generator. Links automatically use sibling filenames when
  the maps are copied into one folder, and nested paths in the runtime layout.
