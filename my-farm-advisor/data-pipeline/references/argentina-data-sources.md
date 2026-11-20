# Argentina farm seeding runbook

This runbook documents the extra data sources and commands needed to seed an
Argentine farm alongside US farms. It is written against the runtime layout
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline`.

## Country routing summary

| Data product | US | Argentina |
|---|---|---|
| Boundaries | OSM / supplied source | grower GeoPackage via `convert_field_gpkg.py` |
| Soil survey | SSURGO / SDA | INTA Cartas de Suelos de Entre Ríos 1:100,000 |
| Soil grid floor | SoilGrids 250 m | SoilGrids 250 m |
| Crop history | USDA CDL | INTA Mapa Nacional de Cultivos (MNC), 30 m |
| Weather | NASA POWER | NASA POWER |
| Imagery | Sentinel-2 via Earth Search | Sentinel-2 via Earth Search |
| Terrain | USGS 3DEP (CONUS) | Copernicus GLO-30 |
| Admin overlay | TIGER states/counties | none (basemap only) |
| Crop strategy | US latitude bands | Entre Ríos calendar/profile |

## 1. Install the runtime

```bash
cd my-farm-advisor/data-pipeline
./scripts/install.sh \
  --data-root /home/coder/my-farm-advisor-runtime \
  --prepare-shared-data
```

This builds the US shared layers (geoadmin, county weather/maturity, last-five
CONUS CDL). It does **not** download Argentina data; those are fetched on
demand by the AR pipeline.

The `--cdl-scope conus` step logs `"rasters": []` because the CONUS CDL bundle
is not served from `nassgeodata.gmu.edu` (every year 404s). This is non-fatal:
per-state rasters (`CDL_<year>_<fips>.tif`) are available for 2021-2025 and the
CDL ingest step downloads them on demand for each farm's state.

## 2. Seed the US farms

`farm_dashboard.py create` samples field polygons from OpenStreetMap via
Overpass. Public Overpass instances saturate or become unreachable; for the
US Corn Belt the repo's documented primary source is instead **USDA Crop
Sequence Boundaries via FIBOA** (`download_csb_fields.py`, see
`field-boundary-sources.md`). Use `create` when Overpass is healthy, or the
CSB path below when it is not.

### 2a. Default path (`farm_dashboard.py create`)

```bash
RUNTIME=/home/coder/my-farm-advisor-runtime
PY="${RUNTIME}/data-pipeline/.venv/bin/python"
SRC="${RUNTIME}/data-pipeline/src"

DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" "${SRC}/scripts/farm_dashboard.py" create \
  --grower-slug il-grower --farm-slug il-farm --farm-name "Illinois Farm" \
  --state Illinois --crop corn --cdl-year 2025 --field-count 3 --seed 42

DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" "${SRC}/scripts/farm_dashboard.py" create \
  --grower-slug ia-grower --farm-slug ia-farm --farm-name "Iowa Farm" \
  --state Iowa --crop corn --cdl-year 2025 --field-count 3 --seed 42
```

`create` selects the top-crop county for `--cdl-year`, writes three field
boundaries, then runs the full pipeline.

### 2b. Overpass-down path (USDA CSB, used for this assignment)

1. Scaffold the farm tree (writes `farm.json` and canonical directories):

   ```bash
   DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" - <<'PY'
   import sys
   sys.path.insert(0, "scripts"); sys.path.insert(0, "scripts/lib")
   from reporting_bootstrap import ensure_canonical_data_tree
   ensure_canonical_data_tree("il-grower", "il-farm", "Illinois Farm")
   ensure_canonical_data_tree("ia-grower", "ia-farm", "Iowa Farm")
   PY
   ```

2. Pick the same top-crop counties `create` would pick (Illinois `Iroquois`,
   Iowa `Kossuth` for corn 2025), then import the three largest eligible CSB
   fields in each county bbox (`S W N E`):

   ```bash
   AG_GROWER_SLUG=il-grower AG_FARM_SLUG=il-farm \
   DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" \
     "${SRC}/scripts/ingest/download_csb_fields.py" \
     --bbox 40.485568 -88.131935 41.010341 -87.525661 \
     --min-area-ha 40 --max-fields 3 --field-prefix il-r \
     --country US --state Illinois --year 2025

   AG_GROWER_SLUG=ia-grower AG_FARM_SLUG=ia-farm \
   DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" \
     "${SRC}/scripts/ingest/download_csb_fields.py" \
     --bbox 42.907762 -94.443289 43.500468 -93.970201 \
     --min-area-ha 40 --max-fields 3 --field-prefix ia-r \
     --country US --state Iowa --year 2025
   ```

3. Run the full pipeline for each farm:

   ```bash
   DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" "${SRC}/scripts/run_farm_pipeline.py" \
     --grower-slug il-grower --farm-slug il-farm --farm-name "Illinois Farm"
   DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" "${SRC}/scripts/run_farm_pipeline.py" \
     --grower-slug ia-grower --farm-slug ia-farm --farm-name "Iowa Farm"
   ```

CSB provenance lands in `manifests/csb_fields_provenance.json`; field
properties carry `source=usda_csb_fiboa`, `csb_id`, `crop`, and county.

## 3. Import the Argentine boundaries

```bash
DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" \
  "${SRC}/scripts/ingest/convert_field_gpkg.py" \
  --gpkg /tmp/opencode/uploads/8ff4e1c4-82f6-4a4b-a69c-faa29fa5cd27/NewFields.gpkg \
  --layer lote_simple_mariano \
  --grower-slug ar-grower --farm-slug ar-farm --farm-name "Entre Ríos Farm" \
  --field-prefix ar --country AR --state "Entre Ríos"
```

The converter writes:

- `growers/ar-grower/farms/ar-farm/boundary/field_boundaries.geojson`
- `growers/ar-grower/farms/ar-farm/manifests/field-inventory.csv`
- `growers/ar-grower/farms/ar-farm/manifests/field_import_provenance.json`
- per-field boundary GeoJSON files

Field IDs are `ar-r1`, `ar-r2`, `ar-r3`; areas are computed in the
hemisphere-correct `EPSG:32721`.

## 4. Prefetch the MNC rasters (optional)

The crop step downloads MNC rasters automatically on first use and verifies
the published MD5. To stage them ahead of time:

```bash
DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" "${SRC}/scripts/ingest/download_cdl.py" \
  --mnc-raster-only --mnc-years 2021,2022,2023,2024,2025
```

Rasters land in `shared/argentina/mnc/<year>/` (about 1.4 GB total for five
campaigns).

## 5. Run the Argentine farm pipeline

```bash
DATA_PIPELINE_DATA_ROOT="${RUNTIME}" "${PY}" \
  "${SRC}/scripts/run_farm_pipeline.py" \
  --grower-slug ar-grower --farm-slug ar-farm --farm-name "Entre Ríos Farm"
```

The default pipeline runs all 16 steps: boundaries, terrain, soil, SoilGrids,
weather, crop history, imagery, NDVI composites/cards, soil maps, field
posters, portfolio poster, soil cards, texture triangles, HTML, and Markdown.

### Argentina-specific behaviour

- **Soil** routes to `argentina-soil`; `soil_source=inta_entre_rios_100k` and
  `mukey=AR-ER-<fid>`.
- **Crop history** uses MNC campaigns 2020/21-2024/25 mapped to years
  2021-2025. The summer map is primary; the winter map is substituted only
  when summer is masked/non-agricultural. Both seasons are written to
  `derived/summaries/mnc_seasonal_detail.csv`, with
  `derived/summaries/mnc_provenance.json`.
- **Crop strategy** uses the Entre Ríos profile (spring planting, June-July
  wheat window, Vertisol waterlogging and humid-canopy disease watchouts).
- **NDVI cards** use the MNC summer raster as the crop mask with MNC codes
  (`Corn=10`, `Soybeans=11`), southern peak windows (DOY 10-90 / 15-95), and
  July-June crop-year grouping for the cumulative chart. Card summaries record
  `country`, `state_fips`, `hemisphere`, and `crop_mask_source`.
- **Area / headlands / posters** use hemisphere-aware UTM (`EPSG:327xx`).

## 6. Verify the outputs

```bash
find "${RUNTIME}/data-pipeline/growers" -name 'field_boundaries.geojson'
find "${RUNTIME}/data-pipeline/growers" -name 'ssurgo_full.csv' | wc -l      # expect 9
find "${RUNTIME}/data-pipeline/growers" -name 'field_report.png' | wc -l     # expect 9
cat "${RUNTIME}/data-pipeline/growers/ar-grower/farms/ar-farm/derived/tables/ar_ssurgo_summary.csv"
cat "${RUNTIME}/data-pipeline/growers/ar-grower/farms/ar-farm/derived/tables/ar_crop_rotation.csv"
cat "${RUNTIME}/data-pipeline/growers/ar-grower/farms/ar-farm/derived/summaries/mnc_seasonal_detail.csv"
python - "${RUNTIME}/data-pipeline/growers/ar-grower/farms/ar-farm/fields/ar-r1/derived/summaries/ndvi_card_summary.json" <<'PY'
import json
import sys
cards = json.load(open(sys.argv[1]))["cards"]
print({key: value["status"] for key, value in cards.items()})
PY
```

Expected grower/farm/field shape: 3 growers × 1 farm × 3 fields = 9 fields.
Every `ar-*` NDVI card should report `available` with `crop_mask_source`
`MNC summer` on the peak cards.

## Data licences

- **INTA soil survey**: public domain; cite Bedendo et al. (2014).
- **MNC**: CC BY 4.0, INTA. Campaign DOIs
  `10.5281/zenodo.8286318`, `10.5281/zenodo.8284081`,
  `10.5281/zenodo.10103323`, `10.5281/zenodo.13984185`,
  `10.5281/zenodo.17652712`.
- **Sentinel-2**: Copernicus open data.
- **NASA POWER**: open data.
- **Copernicus DEM GLO-30**: open data, attribution required.

See `../../soil/argentina-soil/PROVENANCE.md` for the series profile
provenance and the endpoints that were checked and found unavailable.
