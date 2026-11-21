# Dataset expansion runbook (Assignment 2 shape)

Reproducible recipe for the four-grower, forty-field demo dataset:
one grower per region, one farm each, ten fields each. It extends the
Assignment 1 shape (three growers × three fields) without touching any
existing field polygon.

Runtime layout is unchanged: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`,
generated assets under `growers/` and `shared/`, nothing written to the
skill checkout.

## Target shape

| Grower | Farm | Region | Fields | Boundary source |
|---|---|---|---:|---|
| `il-grower` | `il-farm` | Iroquois County, IL | 10 | USDA CSB via FIBOA (`usda_csb_fiboa`) |
| `ia-grower` | `ia-farm` | Kossuth County, IA | 10 | USDA CSB via FIBOA (`usda_csb_fiboa`) |
| `ar-grower` | `ar-farm` | Entre Ríos, AR | 10 | 3 grower GeoPackage + 7 OSM (`osm_farmland') |
| `ne-grower` | `ne-farm` | Hamilton County, NE | 10 | USDA CSB via FIBOA (`usda_csb_fiboa`) |

All four farms get the full pipeline (terrain, soil, SoilGrids, weather, CDL
or MNC crop history, imagery, NDVI, posters, HTML, Markdown) plus per-field
FIPS assignment for the three US farms.

## Non-destructive field IDs

The important invariant: **Assignment 1 shapes survive**.

- `download_csb_fields.py` ranks candidates by `(-area_ha, id)` and numbers
  them from `1`. Re-running the *same* bbox and prefix with a larger
  `--max-fields` therefore reproduces the original `r1…r3` byte-for-byte and
  appends `r4…r10`. Snapshot `csb_id` + geometry hash before the run and diff
  after; a mismatch means the bbox or threshold changed and the run must be
  rejected.
- OSM ingest numbers from `1` as well, so the Argentine additions use a
  distinct prefix (`ar-o`) rather than `ar-r`. That keeps the three
  grower-supplied polygons and their provenance intact and lets
  `field_import_provenance.json` and `osm_fields_provenance.json` coexist.
- Never shrink a bbox to "clean up" field spread. A tighter window re-ranks
  the largest-field selection and silently replaces `r1…r3`.

## Commands

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
PY="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python"
SRC="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
cd "$SRC"

# 1. Scaffold a new grower/farm (writes grower.json + farm.json routing metadata)
"$PY" - <<'PY'
import sys
sys.path.insert(0, "scripts"); sys.path.insert(0, "scripts/lib")
from reporting_bootstrap import ensure_canonical_data_tree
ensure_canonical_data_tree("ne-grower", "ne-farm", "Nebraska Farm",
                           country="US", state="Nebraska")
PY

# 2a. US expansion — same county bbox and prefix as the existing farm
AG_GROWER_SLUG=ne-grower AG_FARM_SLUG=ne-farm "$PY" scripts/ingest/download_csb_fields.py \
  --bbox 40.6983 -98.2829 41.1734 -97.8256 \
  --min-area-ha 40 --max-fields 10 --field-prefix ne-r \
  --country US --state Nebraska --year 2025

# 2b. Argentina additions — field-scale window, distinct prefix
AG_GROWER_SLUG=ar-grower AG_FARM_SLUG=ar-farm "$PY" scripts/ingest/download_osm_fields.py \
  --bbox -33.32 -59.05 -33.03 -58.58 \
  --min-area-ha 20 --max-area-ha 150 --max-fields 7 \
  --field-prefix ar-o --country AR --state "Entre Ríos" --year 2025

# 3. Full pipeline per farm (idempotent; skips unchanged steps)
"$PY" scripts/run_farm_pipeline.py --grower-slug ne-grower --farm-slug ne-farm \
  --farm-name "Nebraska Farm"

# 4. County FIPS join for the US farms (not called by the pipeline)
"$PY" scripts/ingest/assign_field_fips.py --grower-slug ne-grower --farm-slug ne-farm

# 5. Field Atlas regeneration
"$PY" scripts/reporting/generate_grower_web_map.py --all-growers --combined
```

## `--max-area-ha` and estate polygons

Rural OSM frequently maps a whole property as one `landuse=farmland` way. In
the Entre Ríos window the largest ways are 1 600–16 000 ha estates; without an
upper bound the area ranking returns them first and the "fields" are
unusable for field-scale EDA. `download_osm_fields.py --max-area-ha`
(default `None`, so existing behaviour is unchanged) rejects them and the
20–150 ha window returns 140 ha lots comparable to the grower-supplied ones.

## Expected provenance files

| Farm | Files |
|---|---|
| `il-farm`, `ia-farm`, `ne-farm` | `manifests/csb_fields_provenance.json` (bbox, row groups read, `csb_id` list) |
| `ar-farm` | `manifests/field_import_provenance.json` (gpkg layer, 3 fields) **and** `manifests/osm_fields_provenance.json` (bbox, Overpass instance, response sha256, 7 fields) |
| all | `manifests/field-inventory.csv` (10 rows), `growers/<grower>/manifests/pipeline_schedule.json` |

## Verification checklist

- 4 growers × 10 fields; `field-inventory.csv` has 10 rows per farm.
- Pre-expansion `r1…r3` `csb_id` and geometry hashes unchanged.
- Every US field carries `csb_id` and a `county` property; AR fields carry
  `osm_way_id` (new) or the gpkg source label (original three).
- Weather table has 10 field IDs × 2021–2025 × 1 826 days.
- `<farm>_<year>_cdl.csv` exists for 2021–2025 with 10 fields; rotation table
  has 10 rows.
- `shared/cdl/rasters/CDL_<year>_31.tif` present for Nebraska.
- `derived/tables/field_fips_mapping.parquet` for the US farms.
- Each grower's Field Atlas lists 10 fields.

## Known county spread

CSB filters on bbox overlap, not county containment, so a county-sized window
picks up adjacent fields. This is deliberate and honest — the `county`
property records the truth:

| Farm | County distribution |
|---|---|
| `il-farm` | 9 Iroquois, 1 Ford |
| `ia-farm` | 9 Kossuth, 1 Humboldt |
| `ne-farm` | 8 Hamilton, 1 Merrick, 1 York |

Keeping the county bbox is what preserves `r1…r3`; the spill is the cost of
that guarantee, and it is useful for cross-county weather comparison.

## Farm display names survive later legs

`run_farm_pipeline.py --farm-name` records the name in
`manifests/pipeline_schedule.json` and `farm.json`, but the individual ingest
and reporting legs call `ensure_canonical_data_tree(grower, farm)` without a
farm name purely to guarantee the tree exists. Until 2026-11-21 that call
applied the module default (`AG_FARM_NAME` / `"Default Farm"`) and overwrote
the recorded `display_name` — the expansion run left all four farms named
`Default Farm`. `reporting_bootstrap.ensure_canonical_data_tree` now treats an
omitted name as "leave whatever is on disk", so only an explicit `farm_name`
renames a farm. Farm HTML titles were unaffected throughout because they read
the schedule, but the Field Atlas farm labels were not, so re-run
`generate_grower_web_map.py` after any name repair.

Regression guard: `src/scripts/tests/smoke_reporting_bootstrap_farm_name.py`.
