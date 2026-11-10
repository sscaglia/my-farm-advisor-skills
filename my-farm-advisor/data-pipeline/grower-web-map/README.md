# Grower Web Map

Generate lightweight, standalone **Field Atlas** maps from the field boundaries
already stored in the data-pipeline runtime. Each grower gets its own HTML map,
and an optional combined map switches between growers and fields.

The maps use Esri World Imagery by default, with an Esri World Street Map
toggle. Field geometry and metadata are embedded in the HTML; satellite tiles
stream from the network at view time.

Each field also opens a **field dossier**: a drawer with Overview, NDVI, Soil,
Terrain, and Report tabs. Report figures (NDVI charts, soil tables, terrain
previews, and the field poster) are embedded as compressed WebP previews, so a
copied HTML file still shows its figures without the runtime folder. Full
resolution PNGs, summary CSVs/JSON, and the farm report stay linked for runtime
use.

## Outputs

For a runtime rooted at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`:

```text
growers/
├── growers_field_map.html
├── growers_field_map.json
├── il-grower/reports/il-grower_field_map.html
├── ia-grower/reports/ia-grower_field_map.html
└── ar-grower/reports/ar-grower_field_map.html
```

The combined map opens on `il-grower` when that grower is present. It includes
an **ALL** pill that lists every field and fits the world view. Standalone maps
link back to the combined atlas, and the combined map links to each standalone
map.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh --no-install-deps

cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py --all-growers --combined
```

Render only selected growers, with or without the combined map:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower il-grower --grower ia-grower

"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --all-growers --no-combined
```

Dossier figures are embedded by default and require Pillow (listed in
`requirements.txt`). Controls:

- `--no-embed-figures` — keep the HTML small and link figures instead. Figures
  then resolve only in the runtime folder layout.
- `--figure-max-width PX` — maximum embedded image width (default `1600`).
- `--figure-quality N` — WebP quality, 1–100 (default `88`).

With the current sample data the combined map is about 12 MB with 153 embedded
figures; a standalone map is roughly 3–5 MB. `--no-embed-figures` produces a
map under 100 KB. Embedded figures are previews, not the full-resolution report
PNGs.

Open the generated HTML in any modern browser. No server is required.

## Inputs

- `growers/<grower>/grower.json`
- `growers/<grower>/farms/<farm>/farm.json`
- `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`
- `growers/<grower>/farms/<farm>/manifests/field-inventory.csv` (optional
  `field_slug` lookup)
- `growers/<grower>/farms/<farm>/fields/<field_slug>/field.json` (optional
  current-crop override)
- Per-field dossier assets under
  `fields/<field_slug>/derived/`: `features/*.png`, `summaries/*.png` and
  `ndvi_card_summary.json`, `terrain/previews/*.png`,
  `tables/dem_terrain_summary.json`, and `reports/field_report.png`
- Per-field soil summary at `fields/<field_slug>/soil/ssurgo_summary.csv`
- Per-farm report at `farms/<farm>/derived/reports/<farm>_farm_report.html`

Missing dossier files are skipped, so partially built fields still render with
the data they have.

The generator resolves `field_slug` from the inventory CSV when the boundary
properties do not include it. It supports `Polygon` and `MultiPolygon`
geometries and multiple farms per grower.

For the current crop label, canonical field metadata wins over the boundary
properties. Add `crop_name` to `field.json` when an imported or model-derived
label is missing or wrong:

```json
{
  "field_slug": "ar-r3",
  "display_name": "ar-r3",
  "crop_name": "Wheat"
}
```

The lookup order is `field.json` → `crop` or `crop_name` on the boundary
feature → `Unknown`.

## Deep links

- Combined: `growers_field_map.html#grower=il-grower&field=il-r1`
- Standalone: `il-grower_field_map.html#field=il-r1`

Grower `all` is valid in the combined map:
`growers_field_map.html#grower=all&field=ia-r2`.

The navigation links adapt to the files' location. In the nested runtime
output, a standalone map links to `../../growers_field_map.html` and the
combined map links to `./<grower>/reports/<grower>_field_map.html`. When all
four HTML files are copied together into one folder, both directions link to
the sibling `growers_field_map.html` or `<grower>_field_map.html` instead.

Opening a dossier adds `tab=<overview|ndvi|soil|terrain|report>`, for example
`growers_field_map.html#grower=il-grower&field=il-r1&tab=soil`.

## Field dossier

Clicking a field list row opens the dossier directly. Clicking a field on the
map opens the compact popup; its **Open field dossier** button opens the same
drawer. Tabs:

- **Overview** — field record, soil/NDVI/terrain highlights, and summary-table
  links.
- **NDVI** — crop-conditional NDVI figures, means, and year coverage.
- **Soil** — dominant soil, drainage, texture, water, and chemistry chips plus
  soil figures. AR fields read INTA data through the same `ssurgo_*` filenames.
- **Terrain** — elevation range, derived products, and terrain previews. Layers
  are advisory proxies, not drainage or erosion designs.
- **Report** — the embedded field poster preview, a full-resolution PNG link,
  and the farm report link with a visible file-size warning (typically 61–74 MB;
  individual reports can be larger).

Figures open in a full-screen viewer with previous/next, zoom, and an
**Open original** link. Links to PNGs, CSVs, JSON, and the farm report only
resolve in the runtime layout; a copied HTML file keeps its embedded figures
and shows a note instead of dead links.

## Portable copies

Every figure is embedded as a base64 WebP preview (max width 1600 px, quality
88), so copying a single HTML file preserves the dossier. Copying all four maps
into one folder additionally keeps their cross-links working. Basemap tiles
still stream from Esri.

## Related docs

- [GUIDE.md](GUIDE.md) — generator workflow, map behavior, and checks
- [AGENTS.md](AGENTS.md) — local scope and runtime rules
- [PROVENANCE.md](PROVENANCE.md) — source and attribution notes
- [Interactive web map reference](../../admin/interactive-web-map/GUIDE.md)
