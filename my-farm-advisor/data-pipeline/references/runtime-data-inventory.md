# Runtime data inventory

**Snapshot date:** 2026-11-10
**Inspected runtime:** `~/my-farm-advisor-runtime/data-pipeline`
**Scope:** descriptive inventory of the live data-pipeline runtime (`shared/` and `growers/`)

This document describes what the data-pipeline actually materialises on disk, what
each dataset contains, how it is consumed, and where growers differ. It is a
point-in-time snapshot, not a schema contract: file counts and sizes change as
pipelines re-run and as more farms are seeded.

Regenerate the numbers in this document with:

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
R="${DATA_PIPELINE_DATA_ROOT}/data-pipeline"

du -sh "$R/shared" "$R/growers"
for d in "$R"/shared/*; do printf '%-28s %5s files %8s\n' "${d#$R/}" "$(find "$d" -type f | wc -l)" "$(du -sh "$d" | cut -f1)"; done
for g in "$R"/growers/*-grower; do printf '%-24s %5s files %8s\n' "${g#$R/}" "$(find "$g" -type f | wc -l)" "$(du -sh "$g" | cut -f1)"; done
```

## 1. Runtime layout

The runtime is a separate writable tree. Committed pipeline code is copied into
`src/` at install time and is executed from the runtime copy, never from the skill
checkout.

```text
data-pipeline/
├── .my-farm-advisor-source.json   # provenance pointer to the installed source
├── .install.lock
├── .venv/                         # runtime Python environment (rasterio, GDAL, pyarrow, ...)
├── src/                           # runtime copy of pipeline code (ingest/, reporting/, eda/, lib/)
├── shared/                        # reusable, multi-grower datasets + shared manifests
└── growers/                       # per-grower, per-farm, per-field outputs
```

Measured footprint at snapshot time:

| Tree | Size | Notes |
|---|---:|---|
| `shared/` | 6.3 GB | Dominated by CDL rasters (2.2 GB), DEM (2.1 GB) and Argentina MNC (1.5 GB) |
| `growers/` | 1.3 GB | Three growers, one farm each, three fields each (9 fields total) |

### `shared/` directory sizes

| Path | Files | Size | Content class |
|---|---:|---:|---|
| `shared/argentina` | 13 | 1.5 GB | Argentina MNC crop rasters + INTA soil extracts |
| `shared/cdl` | 13 | 2.2 GB | USDA Cropland Data Layer state rasters |
| `shared/corn_maturity` | 34 | 8.2 MB | County GDD and corn relative-maturity tables |
| `shared/dem` | 14 | 2.1 GB | NASADEM (AR) and USGS 3DEP (IA/IL) source DEM tiles |
| `shared/geoadmin` | 14 | 498 MB | Country/state/county boundaries and FIPS lookup |
| `shared/logs` | 0 | 4 KB | Empty placeholder |
| `shared/manifests` | 7 | 36 KB | Shared initialization + maturity manifests |
| `shared/osm` | 1 | 12 KB | Field-source download journal (FIBOA/CSB) |
| `shared/reference` | 0 | 16 KB | Empty `crop_codes`, `schemas`, `units` placeholders |
| `shared/soilgrids` | 245 | 1.2 MB | Per-field SoilGrids rasters, stats table, hash journal |
| `shared/soybean_maturity` | 24 | 8.2 MB | County soybean maturity-group tables |
| `shared/weather` | 10 | 103 MB | Lower-48 county daily weather parquet by year |

### `growers/` directory sizes

| Grower | Files | Size | Farm | Fields |
|---|---:|---:|---|---:|
| `ar-grower` | 1,959 | 224 MB | `ar-farm` (Entre Ríos, AR) | 3 |
| `ia-grower` | 1,725 | 522 MB | `ia-farm` (Kossuth County, IA) | 3 |
| `il-grower` | 1,864 | 527 MB | `il-farm` (Iroquois County, IL) | 3 |

## 2. What is in `shared/`

`shared/` holds datasets that are expensive or redundant to recompute per field.
They are downloaded, clipped, or aggregated once and then read by grower
pipelines. Two shared products are naturally county-wide/US-only; the Argentina
farm therefore reaches into a different set of shared assets.

### 2.1 `shared/geoadmin/` — administrative geography

Natural Earth countries plus US Census TIGER states and counties, stored as
GeoJSON, GeoParquet (WKB geometry, EPSG:4326), and raw source archives.

| Path | Rows/features | Contents |
|---|---:|---|
| `l0_countries/countries.geojson` / `.parquet` | 258 | Countries with `adm0_a3`, `iso_a3`, `name`, `continent`, `region_un` |
| `l1_states/states_usa.geojson` / `.parquet` | 56 | US states/territories |
| `l2_counties/counties_usa.geojson` / `.parquet` | 3,235 | US counties |
| `l2_counties/fips_lookup.parquet` | 3,235 | FIPS ↔ state/county name lookup used for joins |

Each level also carries `metadata.json` with source URL, vintage, feature count,
and column list. Used by: all growers (basemaps, admin overlays, FIPS assignment).
The AR farm uses the country layer only; US counties do not apply.

### 2.2 `shared/weather/nasa-power/` — lower-48 county daily weather

One directory per year (2021–2025), each with a county-level parquet and a
coverage summary.

- `daily_weather_by_fips.parquet` — ~1.13 M rows/year, 17 columns:
  `date, year, fips, state_fips, county_fips, county_name, county_name_full,
  field_count, centroid_lat, centroid_lon, T2M, T2M_MAX, T2M_MIN, PRECTOTCORR,
  ALLSKY_SFC_SW_DWN, RH2M, WS10M`.
- `county_weather_coverage_summary.json` — 3,109 lower-48 counties, 100% covered,
  zero request failures.

Used by: `ia-grower` and `il-grower` (county join), and by the maturity/GDD
calculations. **Not** used by `ar-grower`, which is outside the lower-48 grid and
uses point-based NASA POWER weather fetched per field instead.

### 2.3 `shared/corn_maturity/` and `shared/soybean_maturity/` — county maturity guidance

Per-year county tables derived from the county weather series.

| Product | Files | Contents |
|---|---|---|
| Corn GDD | `tables/gdd_by_fips_<year>.parquet` | Growing-degree-day accumulation per FIPS |
| Corn RM | `tables/rm_by_fips_<year>.parquet` / `.csv` | Relative-maturity estimate per FIPS |
| Corn RM average | `tables/rm_by_fips_2021_2025_average.*` | 5-year mean, 3,109 counties |
| Soybean MG | `tables/mg_by_fips_<year>.parquet` / `.csv` | Maturity-group estimate per FIPS |
| Soybean MG average | `tables/mg_by_fips_2021_2025_average.*` | 5-year mean, 3,109 counties |

Each tree also has `metadata/`, `reports/` (per-year RM choropleth PNGs for corn),
and `logs/`. The dataset metadata labels the product `planned`, but the tables
and reports for all five years are present and complete. Both averages carry an
explicit caveat: they are **planning heuristics**, not recommendation-grade
hybrid/variety guidance.

Used by: `ia-grower` and `il-grower` farm reports (e.g. IA report cites RM 104 /
MG 1). Not applicable to `ar-grower`, which uses Entre Ríos crop-calendar
guidance instead.

### 2.4 `shared/cdl/` — USDA Cropland Data Layer

State-scoped GeoTIFFs, not CONUS mosaics.

- `rasters/CDL_<year>_<state_fips>.tif` for 2021–2025.
- Present states: `17` (Illinois) and `19` (Iowa), 10 rasters total, ~200–245 MB each.
- `derived/`, `metadata/`, `manifests/`, and `logs/` subdirectories exist but are empty.
- A few `*.tif.aux.xml` sidecars hold band statistics.

Used by: `il-grower` and `ia-grower` for crop-history composition and rotation
tables. `ar-grower` uses `shared/argentina/mnc` instead.

### 2.5 `shared/dem/` — source elevation

| Source | Fields | Files | Notes |
|---|---|---:|---|
| `nasadem/` | `ar-r1`, `ar-r2`, `ar-r3` | 3 | All three point at the same tile, `NASADEM_HGT_s34w059.tif` (~6.7 MB) |
| `usgs_tnm_3dep/` | `ia-r1..r3`, `il-r1..r3` | 8 | 1 m 3DEP tiles, 167–301 MB each; some fields need two tiles |

Each field directory has a `cog_download_manifest.json` recording the source URL
and access time. Grower pipelines clip these tiles into
`fields/<field>/terrain/dem/dem_clipped.tif`. Used by all growers.

### 2.6 `shared/soilgrids/` — 250 m soil grid floor

- `soilgrids/<field>/soilgrids_<band>_<depth>.tif` for 9 fields.
- 9 bands (`bdod, cec, cfvo, clay, nitrogen, phh2o, sand, silt, soc`) × 3 depths
  (`0-5cm, 5-15cm, 15-30cm`) = 243 small rasters, plus 50 m field buffer.
- `tables/soilgrids_field_stats.parquet` — 243 rows of per-field zonal statistics.
- `manifests/sha256_journal.json` — per-raster SHA-256, band, depth, source URL,
  GDAL version, and access time.

Used by all nine fields as a consistent grid-based soil floor and as cross-check
for survey soil. Scale factors/units live in each grower's
`manifests/soilgrids_provenance.json`.

### 2.7 `shared/argentina/mnc/` — INTA Mapa Nacional de Cultivos

Ten 30 m GeoTIFFs, one summer and one winter campaign per year 2021–2025
(~1.5 GB total). Summer maps are the primary crop source; winter maps supply
winter cereals and are used only when the summer map is masked or
non-agricultural (summer share < 20%). Attribution and per-campaign DOIs are in
`growers/ar-grower/farms/ar-farm/derived/summaries/mnc_provenance.json`.

Used by: `ar-grower` only.

### 2.8 `shared/argentina/inta/` — INTA Entre Ríos soil extracts

Three WFS-exported GeoJSON bounding-box extracts (~323 KB each) from the INTA
1:100,000 Cartas de Suelos de Entre Ríos layer. These are the source polygons
behind the AR field soil tables; series profiles (taxonomy, drainage, horizon
count) are recorded in the AR farm's `manifests/inta_soil_provenance.json`.

Used by: `ar-grower` only.

### 2.9 `shared/osm/` — field-source journal

`manifests/sha256_journal.json` records the per-bbox download of the FIBOA
`us-usda-cropland` parquet used to derive US field boundaries, including URL,
license, CRS, bbox, row groups read, minimum area, and field list. (Despite the
directory name, the current US boundary source is USDA CSB via FIBOA, not OSM.)

Used by: `ia-grower` and `il-grower` provenance; not applicable to `ar-grower`.

### 2.10 `shared/manifests/` and `shared/reference/`

- `shared_data_initialization.json` — start/end year 2021–2025, coverage
  `lower48`, weather backend `zarr`, time standard `lst`, CDL scope `conus`,
  five-year window, and step status for shared-maturity and shared-CDL.
- `maturity_by_fips_<year>.json` and `maturity_by_fips_2021_2025.json` — the
  authoritative inventory of annual weather/maturity outputs, with per-file
  existence and byte size.
- `shared/reference/{crop_codes,schemas,units}` and `shared/logs` are **empty
  placeholders**; no lookup tables have been materialised there yet.

## 3. `shared/` → grower consumer matrix

| Shared dataset | `ar-grower` | `ia-grower` | `il-grower` |
|---|:---:|:---:|:---:|
| `geoadmin/l0_countries` | yes | yes | yes |
| `geoadmin/l1_states`, `l2_counties`, `fips_lookup` | no | yes | yes |
| `weather/nasa-power` (county) | no | yes | yes |
| `corn_maturity`, `soybean_maturity` | no | yes | yes |
| `cdl/rasters` (state) | no | yes (FIPS 19) | yes (FIPS 17) |
| `argentina/mnc` | yes | no | no |
| `argentina/inta` | yes | no | no |
| `dem/nasadem` | yes | no | no |
| `dem/usgs_tnm_3dep` | no | yes | yes |
| `soilgrids` | yes | yes | yes |
| `osm` journal | no | yes | yes |

Practical consequence: `shared/` is not a single uniform bundle. The US growers
share the county weather/maturity/CDL stack; the Argentina grower shares only the
generic layers (geoadmin country, DEM source, SoilGrids) and replaces weather,
crop history, and soil survey with country-specific sources.

## 4. Structure under `growers/`

Every grower follows the same `grower → farm → field` tree, so tooling can walk
it generically. Per-grower differences are in data values and a few
country-specific artifacts, not directory shape.

```text
growers/
├── growers_field_map.json           # index of combined + per-grower maps
├── growers_field_map.html           # combined interactive Field Atlas (74 KB)
├── <grower>/
│   ├── grower.json
│   ├── manifests/pipeline_schedule.json
│   ├── logs/pipeline_runs.jsonl
│   ├── reports/<grower>_field_map.html
│   └── farms/<farm>/
│       ├── farm.json
│       ├── boundary/field_boundaries.geojson
│       ├── manifests/               # import, soil, SoilGrids, and render manifests
│       ├── derived/
│       │   ├── dashboards/          # empty placeholder
│       │   ├── reports/             # farm HTML/Markdown/PNG reports
│       │   ├── summaries/           # crop-source provenance, seasonal detail
│       │   └── tables/              # farm-level CDL, soil, weather, rotation, DEM CSVs
│       ├── logs/pipeline_runs.jsonl
│       └── fields/<field>/
│           ├── field.json
│           ├── boundary/field_boundary.geojson
│           ├── soil/                # survey table, summary, GeoJSON, metadata
│           ├── weather/             # daily_weather.csv + metadata
│           ├── satellite/           # landsat/ and sentinel/ scene trees + manifests
│           ├── terrain/dem/         # clipped DEM
│           ├── derived/
│           │   ├── features/        # NDVI rolls/composites, soil maps
│           │   ├── reports/         # field_report.png
│           │   ├── summaries/       # NDVI cards/summaries, soil quality PNGs
│           │   ├── tables/          # per-field DEM/NDVI tables
│           │   └── terrain/         # slope, curvature, TWI, conditioned DEM
│           ├── manifests/           # DEM/NDVI/poster render manifests
│           └── logs/pipeline_runs.jsonl
```

At the top of `growers/`, `growers_field_map.json` records `generated_at`,
`default_grower` (`il-grower`), 3 growers, 9 fields, and each grower's map path.
The combined map is `growers/growers_field_map.html`; each grower also has a
standalone `reports/<grower>_field_map.html`.

## 5. Common files and the data they provide

### 5.1 Identity and metadata files

| File | Key contents |
|---|---|
| `growers/<grower>/grower.json` | `grower_slug`, `display_name`, `notes` |
| `farms/<farm>/farm.json` | `grower_slug`, `farm_slug`, `display_name`, `state`, `country`, `default_crs`, `notes` |
| `fields/<field>/field.json` | `grower_slug`, `farm_slug`, `field_slug`, `display_name`, `crop_name`, `field_id`, plus relative paths to boundary, soil, weather, and satellite |

`field.json` is the routing record: downstream steps resolve inputs through these
relative paths, so renaming a field directory without updating it breaks the
pipeline. It is also the supported override point for crop naming (see AR below).

### 5.2 Boundaries

`boundary/field_boundaries.geojson` (farm) and `boundary/field_boundary.geojson`
(field) are EPSG:4326 polygons. Farm-level properties vary by source:

- US fields: `field_id, country, state, year, area_ha_est, crop, area_acres,
  source, csb_id, county` (source `usda_csb_fiboa`).
- AR fields: `field_id, field_slug, country, state, source, region, crop_name,
  area_acres` (source `gpkg:NewFields.gpkg:lote_simple_mariano`).

These geometries drive area, clipping, zonal statistics, and the Field Atlas map.

### 5.3 Soil

All three growers currently emit the same four filenames per field:

| File | Contents |
|---|---|
| `soil/ssurgo_soil_types.geojson` | Soil map units clipped to the field |
| `soil/ssurgo_full.csv` | Horizon-level rows: `mukey, muname, compname, comppct_r, drainagecl, hzdept_r, hzdepb_r, om_r, ph1to1h2o_r, awc_r, claytotal_r, sandtotal_r, silttotal_r, dbthirdbar_r, cec7_r, caco3_pct, soil_area_share, soil_source` |
| `soil/ssurgo_summary.csv` | Per-field rollup: mukey/component/horizon counts, avg OM/pH/CEC/clay/sand, total available water storage, dominant soil, drainage class, pH constraint, erosion risk |
| `soil/metadata.json` | Dataset name, source, field scope, format, CRS |

Naming caveat: the AR files are **INTA** data but keep the `ssurgo_*` filenames
and `"source": "usda-sda"` metadata generated by the shared writer. Treat the
filename as a schema convention, not a provenance claim; the real source is in
`manifests/inta_soil_provenance.json`.

### 5.4 Weather

`weather/daily_weather.csv` — one row per day, 2021–2025, with
`T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, ALLSKY_SFC_SW_DWN, RH2M, WS10M` plus
field/lat/lon keys in the farm-level rollup. `weather/metadata.json` records
`source: nasa-power` and `spatial_scope: field` for every grower. Weather is
sampled per field, but the US farms' values come from the shared county grid,
while AR is a true point extraction.

### 5.5 Satellite imagery and NDVI

`satellite/landsat/` and `satellite/sentinel/`, each organised as
`<sensor>/<year>/<sensor>_<yyyymmdd>/`, with per-scene rasters:

- `*_red.tif`, `*_nir.tif`, `*_ndvi.tif`, `*_qa_pixel.tif`
- `*_epsg4326.tif` reprojected variants

Each sensor tree has a `manifest.json` listing years, scene counts, covered and
missing months, coverage status, reuse flags, cloud cover, and scene status.
Scene counts at snapshot:

| Field | Landsat scenes | Sentinel scenes |
|---|---:|---:|
| `ar-r1`/`r2`/`r3` | 37 each | 43 each |
| `ia-r1` | 34 | 33 |
| `ia-r2` | 34 | 31 |
| `ia-r3` | 34 | 45 |
| `il-r1` | 40 | 35 |
| `il-r2` | 40 | 41 |
| `il-r3` | 40 | 35 |

### 5.6 Terrain

`terrain/dem/dem_clipped.tif` is the survey-grade clip. `derived/terrain/` holds
conditioned DEM and terrain derivatives (slope, curvature, TWI, flow
accumulation). `derived/tables/dem_terrain_summary.{csv,json}` summarises
elevation range, slope percentiles, ponding/erosion proxy areas, CRS, and
conditioning status. `manifests/dem_terrain_manifest.json` records inputs,
outputs, checksums, and quality warnings.

Important caveat: all nine fields currently report
`conditioning_status: skipped_backend_unavailable` with no conditioning backend.
Terrain products and previews still exist, but hydrology-derived layers are
**advisory proxies, not engineered drainage design**. The JSON summary states
this explicitly.

### 5.7 Field-level derived products

| Path | Contents |
|---|---|
| `derived/features/ndvi_year_<year>_composite.tif` | Per-year NDVI composite, 2021–2025 |
| `derived/features/ndvi_corn*.{tif,png}`, `ndvi_soybean*.{tif,png}` | Crop-conditional NDVI rollups and 95th-percentile peak cards |
| `derived/features/ndvi_current_season_cumulative.png` | Current-season cumulative NDVI |
| `derived/features/soil_*_map.png` | Per-property soil maps (pH, OM, clay, sand, silt, AWC, CEC, bulk density, component) |
| `derived/summaries/ndvi_card_summary.json` | Per-crop NDVI availability, years used, mean NDVI, output paths |
| `derived/summaries/ndvi_yearly_summary.json` | Year-by-year NDVI summary |
| `derived/summaries/soil_properties.png`, `soil_texture.png` | Soil cards |
| `derived/tables/ndvi_year_crop_join.csv` | Year → crop → NDVI join used by reports |
| `derived/tables/dem_terrain_summary.{csv,json}` | Terrain metrics |
| `derived/reports/field_report.png` | Rendered field poster |

All fields get `soil_component_map.png`, `soil_weighted_property_map.png`,
`soil_texture_triangle.png`, and `soil_horizon_table.png`. AR fields additionally
get discrete per-property layers (`soil_ph_map.png`, `soil_organic_matter_map.png`,
`soil_clay_map.png`, `soil_sand_map.png`, `soil_silt_map.png`, `soil_awc_map.png`,
`soil_cec_map.png`, `soil_bulk_density_map.png`, `soil_component_pct_map.png`);
US fields do not.

### 5.8 Farm-level derived products

`derived/tables/` holds the cross-field analysis inputs:

| File pattern | Contents |
|---|---|
| `<grower>_<year>_cdl.csv` | Per-field crop composition for that year |
| `<grower>_cdl_2021_2025_full_composition.csv` | Long table of field × year × season × crop, pixel count, percent, source |
| `<grower>_crop_rotation.csv` | Rotation sequence, diversity, corn/soybean year counts, predicted next crops, confidence |
| `<grower>_fields_soil.csv` | Horizon-level soil rows across fields |
| `<grower>_ssurgo_summary.csv` | Per-field soil rollup |
| `<grower>_dem_summary.csv` | Per-field terrain summary |
| `<grower>_weather_2021_2025.csv` | Long daily weather for all fields |
| `soil_polygons_<region>.gpkg` | Dissolved/combined soil polygons (AR only) |

`derived/reports/` holds `<farm>_report.html`, `.md`, and `.png`. `derived/summaries/`
holds crop-source provenance and, for AR, MNC seasonal selection detail.

### 5.9 Manifests and logs

- Grower: `manifests/pipeline_schedule.json` (per-farm run status and step
  results), `logs/pipeline_runs.jsonl`.
- Farm: `manifests/field_import_provenance.json`, `field-inventory.csv`,
  `inta_soil_provenance.json` (AR), `soilgrids_provenance.json`,
  `farm_html_render.json`, `farm_markdown.json`, `farm_poster_render.json`.
- Field: `manifests/dem_terrain_manifest.json`,
  `ndvi_composite_build_<field>.json`, `ndvi_card_render_<field>.json`,
  `field_poster_render_<field>.json`, `logs/pipeline_runs.jsonl`.

Render manifests contain code fingerprints, input/output fingerprints, status,
and step name, which is what makes incremental re-runs possible.

## 6. Grower profiles

All three growers ran the same 16-step schedule to `complete`:
`download_fields → download_dem_terrain → download_soil → download_soilgrids →
download_weather → download_cdl → download_satellite_imagery → NDVI composites →
NDVI cards → SSURGO maps → field posters → aggregate poster → SSURGO cards →
soil texture triangles → farm HTML → farm Markdown`.

### 6.1 `ar-grower` — Entre Ríos, Argentina

| Item | Value |
|---|---|
| Farm | `ar-farm`, "Entre Ríos Farm", country `AR`, state `Entre Ríos` |
| Total area | 667.2 acres |
| Fields | `ar-r1` 358.4 ac, `ar-r2` 157.1 ac, `ar-r3` 151.6 ac |
| 2025 crops (`field.json`) | Corn, Corn, Wheat |
| Crop history source | INTA MNC 30 m summer/winter campaigns |
| Soil source | INTA Entre Ríos 1:100,000 |
| DEM source | NASADEM tile `s34w059` |
| Satellite | 37 Landsat + 43 Sentinel scenes per field |

Particularities:

- **Boundaries came from a grower GeoPackage** (`NewFields.gpkg`, layer
  `lote_simple_mariano`), not the US CSB extractor. Boundary properties therefore
  carry `crop_name: "Unknown"` and a `region` field; there is no `county`,
  `csb_id`, or `year`.
- **Crops are corrected in `field.json`** (`Corn`, `Corn`, `Wheat`) because the
  GPKG did not supply them. Anything reading crop identity should prefer
  `field.json` over boundary properties.
- **Soil is INTA, not SSURGO.** Output filenames remain `ssurgo_*` and
  `soil/metadata.json` still says `usda-sda`, but the farm manifest
  `inta_soil_provenance.json` is authoritative: WFS layer, license, attribution,
  and per-series taxonomy/drainage (e.g. Estancia Retiro = Argiudol ácuico,
  well drained; La Monona = Peluderte árgico, moderately well drained). AWC uses
  a USDA texture-class lookup with the measured moisture equivalent retained for
  audit.
- **Crop history is MNC summer/winter.** `derived/summaries/mnc_seasonal_detail.csv`
  records both seasons and why one was selected (rule: summer primary; winter
  only when summer share < 20%). Composition rows carry `crop_source: mnc` and a
  campaign label such as `2024/25`.
- **Weather is point-based**, not from `shared/weather`: AR is outside the
  lower-48 grid, so `derived/tables/ar_weather_2021_2025.csv` is a per-field
  latitude/longitude extraction.
- **No CDL, no state/county geoadmin.** AR farm tables are named `<year>_cdl.csv`
  for schema compatibility but contain MNC results.
- **DEM reuse:** all three fields clip the same NASADEM tile, so terrain inputs
  are identical across fields at source resolution.
- **Report size:** the farm HTML report is ~142 MB, the largest of the three,
  because it embeds Argentina soil/NDVI imagery.

### 6.2 `ia-grower` — Kossuth County, Iowa

| Item | Value |
|---|---|
| Farm | `ia-farm`, country `US`, state `Iowa`, default CRS `EPSG:4326` |
| Total area | 2,266.2 acres |
| Fields | `ia-r1` 873.0 ac (Soybeans), `ia-r2` 731.3 ac (Corn), `ia-r3` 661.9 ac (Soybeans) |
| Crop history source | USDA CDL FIPS 19 |
| Soil source | SSURGO / SDA |
| DEM source | USGS TNM 3DEP 1 m (`ia-r3` needs two tiles) |
| Satellite | Landsat 34/34/34, Sentinel 33/31/45 scenes |

Particularities:

- Boundaries come from FIBOA USDA CSB (`usda_csb_fiboa`) with `csb_id`, `year`,
  `area_ha_est`, `county`, and boundary-level `crop` populated, so crop identity
  is available both in the boundary and via CDL.
- Corn/soybean rotation is high-confidence and alternating. `ia-r1` and `ia-r3`
  run Soybeans → Corn → Soybeans → Corn → Soybeans over 2021–2025, `ia-r2` runs
  the inverse; the outlook predicts Corn next on `ia-r1`/`ia-r3`.
- County weather and maturity guidance (RM/MG) are read from shared lower-48
  tables; the report cites values such as RM 104.
- Soil summary shows poorly drained Webster as dominant on `ia-r1` (high OM,
  moderate erosion risk), which is typical of the Des Moines Lobe and drives the
  drainage/ponding narrative.
- `ia-r3` has the most Sentinel scenes (45), reflecting scene availability rather
  than a configuration difference.

### 6.3 `il-grower` — Iroquois County, Illinois

| Item | Value |
|---|---|
| Farm | `il-farm`, country `US`, state `Illinois` |
| Total area | 2,352.9 acres |
| Fields | `il-r1` 956.9 ac, `il-r2` 715.1 ac, `il-r3` 680.9 ac — all Corn in 2025 |
| Crop history source | USDA CDL FIPS 17 |
| Soil source | SSURGO / SDA |
| DEM source | USGS TNM 3DEP 1 m (`il-r2` needs two tiles) |
| Satellite | Landsat 40/40/40, Sentinel 35/41/35 scenes |

Particularities:

- **All three fields are corn in 2025**, so crop-conditional NDVI produces a corn
  card for every field and soybean cards depend on earlier years.
- It is the **default grower** in `growers_field_map.json`, so the combined Field
  Atlas opens on `il-grower`.
- Highest Landsat scene count (40 per field) of the runtime, giving the densest
  optical time series.
- Has the same US stack as Iowa (CDL, county weather, RM/MG, 3DEP) but with
  FIPS 17 rasters and Iroquois-specific soil/rotation values.
- Farm HTML report is ~61 MB.

### 6.4 Cross-grower comparison

| Dimension | `ar-grower` | `ia-grower` | `il-grower` |
|---|---|---|---|
| Country / state | AR / Entre Ríos | US / Iowa | US / Illinois |
| Total acres | 667.2 | 2,266.2 | 2,352.9 |
| Boundary source | grower GPKG | USDA CSB (FIBOA) | USDA CSB (FIBOA) |
| Boundary crop | `Unknown` (override in `field.json`) | populated | populated |
| Crop history | INTA MNC | CDL FIPS 19 | CDL FIPS 17 |
| Soil survey | INTA 1:100k | SSURGO | SSURGO |
| Weather | per-field point | county grid | county grid |
| Maturity guidance | Entre Ríos calendar | RM/MG tables | RM/MG tables |
| DEM | NASADEM 30 m-class | 3DEP 1 m | 3DEP 1 m |
| Field terrain | advisory proxies | advisory proxies | advisory proxies |

## 7. Particularities and caveats to carry forward

1. **`shared/` is regionally split.** County weather, county maturity, CDL, and
   US geoadmin are lower-48-only. AR substitutes MNC, INTA, NASADEM, and point
   weather. Do not assume every shared dataset applies to every grower.
2. **Soil filename vs provenance mismatch in AR.** `ssurgo_*` names and
   `usda-sda` metadata are inherited writer conventions. Use
   `manifests/inta_soil_provenance.json` for AR provenance.
3. **AR boundary crops are `Unknown`.** `field.json` `crop_name` is the corrected
   source of truth; boundary geometry carries no reliable crop.
4. **Terrain conditioning is disabled everywhere** (`skipped_backend_unavailable`).
   Derived hydrology is advisory; do not present ponding/erosion proxies as
   drainage design.
5. **Maturity products are heuristics.** Corn RM and soybean MG averages are
   planning aids derived from county GDD/latitude, not hybrid recommendations.
6. **Maturity metadata says `planned` while outputs are complete.** Trust the
   files and `shared/manifests/maturity_by_fips_2021_2025.json`, not the status
   label in `metadata/dataset.json`.
7. **CDL is state-scoped, not CONUS.** Only FIPS 17 and 19 exist. A new state
   requires its own `CDL_<year>_<fips>.tif` download; the runtime does not hold a
   national mosaic.
8. **CDL metadata/manifests/derived/logs are empty.** Crop composition is
   assembled at the farm level instead.
9. **`shared/reference/*` and `shared/logs` are empty placeholders.** No
   canonical crop-code, schema, or unit tables are materialised yet, even though
   crop codes (10= corn, 11= soybeans, 22= other) appear in outputs.
10. **Shared DEM can be shared per field group.** All AR fields point at one
    NASADEM tile; US fields may need one or two 3DEP tiles. Storage cost is
    concentrated on the US side (2.1 GB).
11. **Report HTML files are large** (~61–142 MB) because imagery is embedded;
    they are runtime artifacts, not Git content.
12. **Empty `derived/dashboards/` and empty per-farm/per-field
    `pipeline_runs.jsonl`** exist by design in this snapshot; run history lives
    primarily in `manifests/pipeline_schedule.json`.
13. **Field Atlas is a separate product** from the farm reports:
    `growers/growers_field_map.html` + `.json` plus per-grower
    `reports/<grower>_field_map.html`, generated 2026-11-09, default grower
    `il-grower`.

## 8. Where each shared asset enters the pipeline

```text
geoadmin (l0/l1/l2, fips_lookup)
    └─ field FIPS assignment, basemaps, admin overlays, Field Atlas

weather/nasa-power (county) ──► corn_maturity (GDD → RM)
    │                       └─► soybean_maturity (MG)
    ├─► US farm weather rollups (ia/il_weather_2021_2025.csv)
    └─► farm reports (RM/MG, precipitation, GDD context)

cdl/rasters/<year>_<fips> ──► farm crop composition + crop rotation (IA/IL)
argentina/mnc ──────────────► farm crop composition + rotation (AR)
argentina/inta ─────────────► field/farm soil tables (AR)
soilgrids ──────────────────► per-field grid soil stats + SoilGrids provenance (all)
dem/{nasadem,usgs_tnm_3dep} ► clipped DEM → terrain derivatives (all)
osm journal ────────────────► US boundary provenance
```

## 9. Known gaps

- No national CDL mosaic and no CDL metadata sidecars.
- No populated `shared/reference` lookup tables.
- No terrain-conditioning backend, so hydrology layers remain proxies.
- AR weather and maturity are not comparable row-for-row with US county tables.
- `shared/logs` empty; reproducibility depends on the JSON manifests rather than
  a shared log stream.

## 10. Maintenance note

This document describes runtime state and therefore must not be treated as a
stable schema. When the runtime is re-seeded or a new grower is added:

1. Re-run the commands in the preamble and refresh the size/count tables.
2. Add the grower to the consumer matrix and cross-grower comparison.
3. Record any new country-specific substitution (the AR pattern is the
   template: new crop history, soil survey, DEM, and weather sources while
   keeping the shared directory/file conventions).
4. Keep generated runtime data out of Git; commit only this kind of reference
   documentation and downloader/provenance metadata.
