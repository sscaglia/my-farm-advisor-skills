# PROJECT_CONTEXT

> **Central technical reference for this repository.**
> Last verified against the codebase: **2026-11-10**.
> Update this file in the same commit as any change to architecture, runtime
> contracts, data models, external sources, or skill status.

This document describes what the repository actually contains, not what it
aspires to contain. Where a capability is partial, stubbed, or a proxy, that is
stated explicitly. File paths are relative to the repository root unless
stated otherwise.

---

## Table of contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Project Architecture](#3-project-architecture)
4. [Folder Structure](#4-folder-structure)
5. [Implemented Features](#5-implemented-features)
6. [Database & Data Models](#6-database--data-models)
7. [API & Integrations](#7-api--integrations)
8. [Authentication & Authorization](#8-authentication--authorization)
9. [UI/UX Guidelines](#9-uiux-guidelines)
10. [Coding Standards](#10-coding-standards)
11. [Important Technical Decisions](#11-important-technical-decisions)
12. [Known Issues & Pending Tasks](#12-known-issues--pending-tasks)
13. [Development Guidelines](#13-development-guidelines)

Appendix: [A. Key File Map](#appendix-a-key-file-map) ·
[B. Glossary](#appendix-b-glossary) ·
[C. Quick Commands](#appendix-c-quick-commands)

---

## 1. Project Overview

### 1.1 What this repository is

`my-farm-advisor-skills` is a **harness-neutral skill catalog**. It packages
portable, document-routed agent skills that turn farm, field, trial, and
genotype data into reproducible analyses, maps, and reports. Any agent runtime
that reads `SKILL.md` / `AGENTS.md` / `INDEX.md` can load it; Hermes and
OpenCode are the tested first-class harnesses, but nothing in the L0 contract
requires a specific harness.

The repository is deliberately **not** a web application, service, or SDK. It
ships:

- Markdown routing documents (`SKILL.md` → `INDEX.md` → `AGENTS.md` / `GUIDE.md`).
- Python (and a little R/shell) implementation modules and runnable examples.
- Provenance and import records for every imported skill.
- A repository-level validator (`scripts/validate.sh`).
- Small, vision-reviewed example figures (PNG) for each output family.

The catalog currently contains **three top-level skills**:

| Skill | Version | Status | Scope |
| --- | --- | --- | --- |
| `my-farm-advisor` | `1.0.0` | **Active focus** | Farm data pipelines, field management, soil, weather, imagery, terrain, EDA, strategy, administrative maps |
| `my-farm-breeding-trial-management` | `0.1.0` | **Initial stab — expanding** | Trial design, fieldbooks, germplasm, selection, crossing, field-trial placement |
| `my-farm-qtl-analysis` | `1.0.0` (declared) | **Initial stab — expanding** | GWAS, eQTL, classical QTL, QC, population structure, genomic prediction, genetics reporting |

`my-farm-advisor` is the keystone skill and receives nearly all implementation
investment. The breeding and QTL skills are earlier-stage: they contain real
runnable examples but also simplified proxies and stubs (see
[§12](#12-known-issues--pending-tasks)).

### 1.2 Goals

1. **Route, don't dump.** An agent should open the smallest correct subtree
   document for a request instead of loading a single giant prompt.
2. **Evidence first.** Every farm product keeps field-level source lineage
   (manifests, provenance JSON, source URLs, licences).
3. **Deterministic reruns.** Pipeline steps are idempotent and skip when inputs,
   code, and config are unchanged.
4. **Keyless by default.** Public data sources are preferred so the catalog works
   with zero accounts and zero API keys.
5. **Portable provenance.** Every imported skill has a committed `PROVENANCE.md`
   and a manifest entry.
6. **Honest maturity.** Partial implementations are labelled, not hidden.

### 1.3 Main functionality

- Rebuild canonical farm data from real field boundaries (USDA CSB, OSM) and
  seed a grower → farm → field tree.
- Ingest soil, weather, crop history, satellite imagery, and DEM terrain.
- Generate NDVI composites/cards, soil maps and cards, texture triangles, field
  posters, farm posters, farm HTML/Markdown reports, maturity maps, and
  standalone grower web maps ("Field Atlas").
- Provide document-routed agronomy guidance for EDA, strategy, imagery, soil
  routing, terrain, and administrative geographies.
- Provide example-first breeding and QTL workflows with sample data and
  visualizations.

### 1.4 What this repository is not

- No database server, ORM, or migrations.
- No inbound HTTP API, GraphQL endpoint, or web backend.
- No application login, user accounts, roles, or sessions.
- No CI pipeline configuration committed (validation is a local script).
- No root `pyproject.toml`, `setup.py`, or root `requirements.txt`.
- No root `LICENSE` file even though Apache-2.0 is declared in frontmatter and
  docs (see [§12.7](#127-repository-hygiene)).

### 1.5 Repository scale (tracked files)

| Metric | Value |
| --- | --- |
| Tracked files | 643 |
| Tracked bytes | 24,828,433 (~24.8 MB) |
| Worktree size | ~28 MB |
| Markdown | 237 |
| Python | 224 |
| PNG (examples) | 101 |
| CSV | 42 |
| JSON | 12 |
| Shell | 3 |
| GeoJSON | 3 |
| R | 1 |
| HTML | 1 |

Python files by skill: `my-farm-advisor` 111, `my-farm-breeding-trial-management`
29, `my-farm-qtl-analysis` 84. The only R file is
`my-farm-qtl-analysis/research/genomic_cv_r.R`.

---

## 2. Technology Stack

### 2.1 Languages and runtimes

| Layer | Technology |
| --- | --- |
| Skill/routing docs | Markdown with YAML frontmatter |
| Farm pipeline and tooling | Python 3 (type-hinted, `from __future__ import annotations`) |
| Shell | Bash (installer + validator) |
| Breeding/QTL examples | Python, R (one file), shell |
| Outputs | PNG, HTML (self-contained), Markdown, JSON, CSV, Parquet, GeoJSON, GeoTIFF, JSONL |
| Validation | Bash + standard Unix tools (`find`, `grep`, `awk`) |

No pinned Python version is declared in a `pyproject.toml`; the runtime uses the
interpreter in the runtime venv. Some type syntax (for example `list[Path]`,
`str | None`) implies modern Python (3.10+); `datetime.UTC` implies 3.11+.

### 2.2 Python dependencies

There is no root dependency file. The authoritative runtime list is
[`my-farm-advisor/data-pipeline/requirements.txt`](my-farm-advisor/data-pipeline/requirements.txt):

| Group | Packages |
| --- | --- |
| Core data stack | `pandas>=2.1`, `numpy>=1.25`, `scipy>=1.11`, `scikit-learn>=1.3`, `tqdm>=4.66` |
| Geospatial | `geopandas>=0.14`, `fiona>=1.9`, `pyproj>=3.6`, `shapely>=2.0`, `rasterio>=1.3`, `rasterstats>=0.19` |
| Storage/interchange | `pyarrow>=15`, `xarray>=2026.1`, `zarr>=3,<4`, `fsspec[http]>=2024.3` |
| Plotting/reporting | `matplotlib>=3.8`, `seaborn>=0.13`, `contextily>=1.6` |
| Utilities | `requests>=2.31`, `beautifulsoup4>=4.12`, `python-dotenv>=1.0` |

Optional, **not installed by default** because it pulls Torch:
`worldcereal @ git+https://github.com/WorldCereal/worldcereal-classification.git@v2.8.2`
(see `my-farm-advisor/data-pipeline/references/crop-rotation-sources.md`).

Additional skill-local requirements:

- [`my-farm-advisor/data-sources/farm-data-rebuild/requirements.txt`](my-farm-advisor/data-sources/farm-data-rebuild/requirements.txt)
- [`my-farm-advisor/soil/ssurgo-poster-cards/requirements.txt`](my-farm-advisor/soil/ssurgo-poster-cards/requirements.txt)

### 2.3 External tools (QTL / breeding)

Declared in `my-farm-qtl-analysis/SKILL.md` and used by example workflows:
**tensorQTL, GEMMA, PLINK, R/qtl2, pyQTL**. The QTL skill's scripts detect
whether these are installed; when absent, several workflows fall back to
simplified proxies (see [§12.4](#124-qtl-analysis-caveats)).

### 2.4 External services and data sources

Summary (details in [§7](#7-api--integrations)): NASA POWER (S3 Zarr + point
API), Microsoft Planetary Computer STAC and SAS signing, USGS TNM 3DEP, NRCS
Soil Data Access, INTA GeoNode WFS, OpenStreetMap Overpass, FIBOA/USDA Crop
Sequence Boundaries GeoParquet, ISRIC SoilGrids, GADM/Census/Natural Earth,
and Esri World Imagery/Street tiles.

### 2.5 Development tooling

- `scripts/validate.sh` — the canonical repository check.
- `my-farm-advisor/data-pipeline/src/scripts/tests/smoke_dem_pipeline.py` — the
  only committed test-style script (a DEM pipeline smoke check; not a full test
  suite, and not wired into the validator).
- Code contains `# ruff: noqa` and `# pyright:` comments, but **no committed
  ruff/pyright/black configuration**. These annotations document local intent,
  not an enforced CI gate.

---

## 3. Project Architecture

### 3.1 Conceptual layers

```text
L0  Catalog contract        SKILL.md / AGENTS.md / INDEX.md / frontmatter
L1  Top-level skills        my-farm-advisor | breeding | qtl
L2  Subskills / workflows   admin, soil, weather, eda, terrain, ...
L3  Runtime data tree       ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/...
```

- **L0** is harness-neutral routing metadata. It has no executable code.
- **L1** is the discoverable unit (`SKILL.md` with `name`, `description`,
  `license`, `metadata.version/author`).
- **L2** folders hold focused `GUIDE.md`, `AGENTS.md`, `README.md`, `src/`, and
  `examples/`. These are **document-routed workflows, not separate
  runtime-discoverable skills** (stated in `my-farm-advisor/SKILL.md`).
- **L3** exists only at runtime, outside the checkout, and is rebuilt by the
  installer and pipeline.

### 3.2 Routing model

The canonical navigation chain is:

```text
SKILL.md  ->  INDEX.md  ->  subtree AGENTS.md / GUIDE.md / README.md
          ->  scripts + examples
```

`CONTRIBUTING.md` calls this out as load-bearing: "documentation drift is a
functional bug." Routers must stay accurate and small; deeper docs are loaded
on demand.

`my-farm-advisor/SKILL.md` routes to nine subtree indexes:

`admin/`, `data-sources/`, `eda/`, `field-management/`, `imagery/`, `soil/`,
`terrain/`, `strategy/`, `weather/`.

The `data-pipeline` subtree is routed through `data-sources/INDEX.md` and the
data-pipeline `AGENTS.md`/`README.md`.

### 3.3 Farm data-pipeline architecture

```text
checkout (committed)                    runtime (generated, outside repo)
────────────────────                    ───────────────────────────────
data-pipeline/src/  ──install.sh──▶     ${ROOT}/data-pipeline/src/
data-pipeline/scripts/install.sh        ${ROOT}/data-pipeline/.venv/
data-pipeline/requirements.txt          ${ROOT}/data-pipeline/growers/
                                        ${ROOT}/data-pipeline/shared/
```

Runtime contract (authoritative in `my-farm-advisor/data-pipeline/AGENTS.md`):

- `DATA_PIPELINE_DATA_ROOT` is **required**, absolute, writable, and outside the
  checkout.
- Runtime base: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`.
- Runtime source copy: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`. Scripts
  run **from this copy**, never from checkout `src/`.
- Runtime venv: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv` unless
  `DATA_PIPELINE_VENV_DIR` points elsewhere (absolute).
- Generated outputs: `growers/`, `shared/`, `logs/`, `manifests/` under the
  runtime base.

Key mechanics:

1. **Installer** (`my-farm-advisor/data-pipeline/scripts/install.sh`) validates
   the root, `rsync`s `src/` excluding caches/output/data, writes a source
   locator (`.my-farm-advisor-source.json`), creates the venv, and installs
   `requirements.txt`.
2. **Bootstrap** (`src/scripts/bootstrap_runtime.py`) runs at the top of entry
   scripts. If the script is executing from the checkout, it ensures the runtime
   copy and venv exist, then re-execs the matching runtime script with the
   runtime Python. It sets `DATA_PIPELINE_RUNTIME_SOURCE_SCRIPT` and preserves
   install-related env vars.
3. **Path resolution** (`src/scripts/lib/runtime_paths.py`, `lib/paths.py`)
   centralises the runtime base, script root, `growers/`, `shared/`, and slug
   validation.
4. **Reporting bootstrap** (`src/scripts/reporting_bootstrap.py`) scaffolds the
   canonical tree (`ensure_canonical_data_tree`) and loads skill modules from
   the runtime source, the locator's checkout root, or env-provided roots
   (`ensure_skill_path`). This is how pipeline scripts import `ssurgo_soil`,
   `cdl_reporting`, etc. without vendoring them into `data-pipeline/src`.
5. **Master orchestration**
   (`src/scripts/run_farm_pipeline.py`) runs the 16 steps in order, updating
   `growers/<grower>/manifests/pipeline_schedule.json` after each step.

### 3.4 Idempotency and staleness model

`my-farm-advisor/data-sources/farm-intelligence-reporting/src/pipeline.py`
implements the reusable pattern:

- `build_code_fingerprint` — hash of relevant source files.
- `build_config_fingerprint` — hash of normalised parameters.
- `build_step_manifest` — records code/config/input fingerprints, timestamps,
  and outputs.
- `step_is_stale` — compares current fingerprints to the last manifest.
- `run_step` — executes only when stale (or forced).

`run_farm_pipeline.py` stores a grower-level schedule manifest and per-field
manifests such as `manifests/ndvi_composite_build_<field>.json`. Reruns are
safe; `--force` overrides staleness.

### 3.5 Design patterns in use

| Pattern | Where |
| --- | --- |
| Router/progressive disclosure | `SKILL.md` → `INDEX.md` → subtree docs |
| Bootstrap + re-exec | `bootstrap_runtime.py` |
| Adapter/strategy | `terrain/dem-terrain/src/dem_terrain/source_resolver.py`, `global_adapters.py` |
| Provider registry | `lib/admin_regions.py`, `lib/geoadmin_context.py`, `soil/soil-routing.md` |
| Manifest/fingerprint idempotency | `farm-intelligence-reporting/src/pipeline.py` |
| Canonical path builders | `lib/paths.py` |
| Facade over national soil modules | `ingest/download_soil.py` + `reporting_bootstrap.ensure_skill_path` |
| Data-driven country routing | boundary `country` property → soil/crop/weather provider |
| Example-first documentation | breeding/QTL `examples/<area>/<name>/` |

---

## 4. Folder Structure

### 4.1 Repository root

```text
.
├── AGENTS.md                     # Repo-level instructions for agents
├── README.md                     # Human overview, coverage ladders, gallery
├── CONTRIBUTING.md               # Doc-sync rule, editing discipline, figure policy
├── PROVENANCE.md                 # Provenance record template + verification policy
├── IMPORT_MANIFEST.md            # Per-import record
├── FINAL_IMPORT_MANIFEST.md      # Finalized import table (dated 2026-04-28)
├── ASSET_POLICY.md               # What may be committed; LFS rules
├── REPOSITORY_ASSET_AUDIT.md     # Asset audit findings
├── PROJECT_CONTEXT.md            # This document
├── .gitattributes                # LFS rules for .npy/.npz/.raw/.bin/.so/.dylib/.dll
├── .gitignore                    # data/, node_modules/, .cache/, caches, payloads
├── .sisyphus/                    # Local agent metadata (ignored)
├── scripts/
│   └── validate.sh               # Canonical validation gate
├── my-farm-advisor/              # Keystone skill (111 .py, 96 .md)
├── my-farm-breeding-trial-management/
└── my-farm-qtl-analysis/
```

Root-level policy highlights:

- **Asset policy:** do not commit `data/`, dependencies, caches, build outputs,
  or runtime geoadmin payloads (`countries.geojson`, `states_usa.geojson`).
  Binary assets over 1 MB require LFS and reviewer approval.
- **LFS formats:** `.npy`, `.npz`, `.raw`, `.bin`, `.so`, `.dylib`, `.dll`.
- **Forbidden paths** enforced by the validator: `superior-byte-works-wrighter`,
  `superior-byte-works-google-timesfm-forecasting`, `node_modules`, `.cache`,
  `data`.

### 4.2 `my-farm-advisor/` (keystone skill)

```text
my-farm-advisor/
├── SKILL.md                 # Routing entrypoint (v1.0.0)
├── README.md                # Human overview + coverage ladders
├── INDEX.md                 # Progressive router
├── AGENTS.md                # Local editing rules
├── PROVENANCE.md            # Import record
├── admin/
│   ├── geoadmin-admin/      # L0/L1/L2 admin geographies, GADM, FIPS lookups
│   └── interactive-web-map/ # Self-contained HTML field maps
├── data-sources/
│   ├── farm-data-rebuild/
│   └── farm-intelligence-reporting/
├── eda/
│   ├── eda-explore/  eda-compare/  eda-correlate/
│   ├── eda-time-series/  eda-visualize/
├── field-management/
│   ├── csb-field-sampling/
│   ├── field-boundaries/
│   └── headlands-ring/
├── imagery/
│   ├── landsat-imagery/
│   └── sentinel2-imagery/
├── soil/
│   ├── argentina-soil/  australia-soil/  cdl-cropland/
│   ├── ontario-soil-survey/  soilgrids-global/
│   ├── ssurgo-poster-cards/  ssurgo-soil/
│   └── soil-routing.md
├── strategy/
│   ├── crop-strategy/       # Crop playbooks (corn, soybean, wheat, cotton, sorghum)
│   └── maturity-by-fips/    # RM/MG by county
├── terrain/
│   └── dem-terrain/         # DEM policy, adapters, clipping, derivatives
├── weather/
│   └── nasa-power-weather/
├── references/              # Cross-cutting source notes
│   ├── argentina-data-sources.md
│   ├── canada-shared-geodata.md
│   ├── crop-rotation-sources.md
│   ├── field-boundary-sources.md
│   └── non-us-soil-sources.md
├── docs/
│   └── GEODATA.md           # Geoadmin runtime payload policy
└── data-pipeline/           # Deterministic runtime pipeline (see 4.3)
```

Sub-workflow counts: admin 2, data-sources 2, EDA 5, field-management 3,
imagery 2, soil 7 (+ routing doc), strategy 2, terrain 1, weather 1.

### 4.3 `my-farm-advisor/data-pipeline/`

```text
data-pipeline/
├── README.md                # Runtime setup + command runbook
├── AGENTS.md                # Runtime contract and local workflow rules
├── requirements.txt
├── scripts/
│   └── install.sh           # Installer (rsync, venv, shared-data flags)
├── references/
│   ├── argentina-data-sources.md
│   ├── crop-rotation-sources.md
│   ├── field-boundary-sources.md
│   └── runtime-data-inventory.md   # Point-in-time runtime snapshot (2026-11-10)
├── grower-web-map/
│   ├── README.md            # Output contract for Field Atlas maps
│   └── GUIDE.md             # Build/run details
├── examples/                # Committed vision-reviewed PNGs only
│   ├── field-components/  field-maps/  maturity/
│   ├── soil-maps/  terrain-derivatives/
│   ├── weather-eda/  worldcereal/
└── src/
    ├── shared/              # Metadata only (geoadmin, maturity, manifests)
    └── scripts/
        ├── run_farm_pipeline.py
        ├── init_shared_data.py
        ├── bootstrap_runtime.py
        ├── reporting_bootstrap.py
        ├── farm_dashboard.py
        ├── ingest/          # 18 source download/normalisation modules
        ├── reporting/       # 14 render/report modules
        ├── eda/             # 6 EDA modules
        ├── lib/             # paths, runtime_paths, manifest, naming,
        │                    # nasa_power, satellite_imagery, projection,
        │                    # admin_regions, geoadmin_context
        └── tests/           # smoke_dem_pipeline.py
```

### 4.4 `my-farm-breeding-trial-management/`

```text
my-farm-breeding-trial-management/
├── SKILL.md                 # v0.1.0
├── README.md  INDEX.md  AGENTS.md  PROVENANCE.md
├── scripts/
│   ├── breeding_cli.py      # Stub subcommand wrapper
│   └── check_system.py      # Environment probe
├── references/              # Method notes
└── examples/                # 19 folders; grouped canonical + flat mirrors
    ├── design/  fieldbook/  germplasm/  select/  cross/  ...   (grouped)
    └── rcbd-design/  field-book/  selection-index/  crossing-plan/ ...
```

### 4.5 `my-farm-qtl-analysis/`

```text
my-farm-qtl-analysis/
├── SKILL.md                 # v1.0.0 declared
├── README.md  INDEX.md  AGENTS.md  PROVENANCE.md
├── scripts/
│   ├── check_system.py
│   ├── qtl_cli.py
│   ├── generate_all_visualizations.py
│   ├── generate_sample_qtl_data.py
│   ├── verify_gpu_hpc.py
│   └── install_deps.sh
├── assets/sample_data/      # Genotype/phenotype fixtures
├── research/                # Long-form method and visualization guides
└── examples/                # ~43 folders; grouped canonical + flat mirrors
    ├── mapping/  qc/  structure/  prediction/  reporting/   (grouped)
    └── gwas-glm/  gwas-lmm/  classical-qtl/  ld-decay/ ...  (flat)
```

### 4.6 Runtime tree (generated, outside checkout)

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/
├── .venv/
├── .my-farm-advisor-source.json     # Locator back to the skill checkout
├── src/                             # Runtime copy of committed src/
├── RUNTIME_DATA_INVENTORY.md        # Copy of the committed inventory
├── growers/
│   └── <grower_slug>/
│       ├── grower.json
│       ├── manifests/ pipeline_schedule.json
│       ├── reports/ <grower>_field_map.html
│       ├── logs/
│       └── farms/<farm_slug>/
│           ├── farm.json
│           ├── boundary/field_boundaries.geojson
│           ├── manifests/ field-inventory.csv, *.json
│           ├── derived/{reports,summaries,tables,dashboards}/
│           ├── logs/
│           └── fields/<field_slug>/
│               ├── field.json
│               ├── boundary/field_boundary.geojson
│               ├── soil/ weather/ satellite/ terrain/dem/
│               ├── manifests/ logs/
│               └── derived/{features,reports,summaries,tables,terrain}/
└── shared/
    ├── geoadmin/{l0_countries,l1_states,l2_counties}/
    ├── weather/nasa-power/
    ├── cdl/{rasters,derived,metadata,manifests,logs}/
    ├── corn_maturity/  soybean_maturity/
    ├── dem/{nasadem,usgs_tnm_3dep}/
    ├── soilgrids/
    ├── argentina/{inta,mnc}/
    ├── osm/
    ├── reference/{crop_codes,schemas,units}/
    ├── manifests/
    └── logs/
```

The committed copy of the runtime inventory is
[`my-farm-advisor/data-pipeline/references/runtime-data-inventory.md`](my-farm-advisor/data-pipeline/references/runtime-data-inventory.md).
It documents `shared/` types and consumers, common grower/farm/field files, and
per-grower particularities for the 2026-11-10 snapshot. Treat it as a
point-in-time reference, not a live mirror.

---

## 5. Implemented Features

Status legend: **Complete** = implemented and exercised in the pipeline;
**Partial** = implemented with documented limits or simplified behaviour;
**Stub/Proxy** = interface or placeholder only, or a heuristic standing in for a
real method.

### 5.1 `my-farm-advisor` — data pipeline

| Feature | Entry point | Status |
| --- | --- | --- |
| Runtime installer | `data-pipeline/scripts/install.sh` | Complete |
| Runtime bootstrap/re-exec | `src/scripts/bootstrap_runtime.py` | Complete |
| Canonical tree scaffolding | `src/scripts/reporting_bootstrap.py` | Complete |
| Master 16-step farm pipeline | `src/scripts/run_farm_pipeline.py` | Complete |
| One-command dashboard orchestration | `src/scripts/farm_dashboard.py` (`create`, `add-fields`, …) | Complete |
| Shared baseline initialisation | `src/scripts/init_shared_data.py` | Complete |
| County → farm bootstrap | `ingest/bootstrap_farm_from_county.py` | Complete |
| Field boundary download | `ingest/download_fields.py` | Complete |
| DEM terrain ingest | `ingest/download_dem_terrain.py` | Partial (see §12.1) |
| Soil routing + ingest | `ingest/download_soil.py` | Complete for US/CA/AR/AU; SoilGrids fallback |
| SoilGrids clips | `ingest/download_soilgrids.py` | Complete |
| Weather ingest | `ingest/download_weather.py` | Complete (Zarr default; API debug) |
| Crop history / CDL / MNC | `ingest/download_cdl.py` | Complete for US; AR via INTA MNC; global WorldCereal optional |
| Satellite + NDVI | `ingest/download_satellite_imagery.py` | Complete |
| FIPS assignment | `ingest/assign_field_fips.py` | Complete |
| WorldCereal crop classification | `ingest/apply_worldcereal.py` | Partial (optional Torch dependency; unvalidated outside reference regions) |
| County weather aggregation | `ingest/aggregate_weather_by_fips.py` | Complete |
| Maturity-by-FIPS tables | `ingest/calculate_corn_rm_by_fips.py`, `calculate_soybean_mg_by_fips.py`, `calculate_gdd_by_fips.py` | Complete (lower-48 heuristics) |
| GeoPackage conversion | `ingest/convert_field_gpkg.py` | Complete |
| CSB / FIBOA boundary ingest | `ingest/download_csb_fields.py` | Complete |

**The 16 master pipeline steps** (order enforced by
`src/scripts/run_farm_pipeline.py`):

1. `ingest/download_fields.py` — canonical field boundaries
2. `ingest/download_dem_terrain.py` — live DEM terrain derivatives
3. `ingest/download_soil.py` — country-routed soil tables
4. `ingest/download_soilgrids.py` — 250 m soil grid clips + stats
5. `ingest/download_weather.py` — weather history tables
6. `ingest/download_cdl.py` — CDL/ACI history tables
7. `ingest/download_satellite_imagery.py` — raw satellite TIFFs
8. `reporting/generate_ndvi_composites.py` — yearly NDVI composites
9. `reporting/generate_ndvi_cards.py` — NDVI cards
10. `reporting/generate_ssurgo_maps.py` — soil maps with basemap
11. `reporting/generate_field_posters.py` — per-field posters
12. `reporting/generate_aggregate_poster.py` — farm portfolio poster
13. `reporting/generate_ssurgo_cards.py` — soil profile cards
14. `reporting/generate_soil_texture_triangles.py` — triangles, horizon tables, area-weighted maps
15. `reporting/generate_farm_html.py` — self-contained HTML report
16. `reporting/generate_farm_markdown.py` — Markdown report

### 5.2 `my-farm-advisor` — reporting and maps

| Feature | Entry point | Status |
| --- | --- | --- |
| NDVI composites/cards | `reporting/generate_ndvi_composites.py`, `generate_ndvi_cards.py` | Complete |
| SSURGO maps/cards | `reporting/generate_ssurgo_maps.py`, `generate_ssurgo_cards.py` | Complete |
| Soil texture triangles/horizon tables | `reporting/generate_soil_texture_triangles.py` | Complete |
| Field posters / farm poster | `reporting/generate_field_posters.py`, `generate_aggregate_poster.py` | Complete |
| Farm HTML/Markdown | `reporting/generate_farm_html.py`, `generate_farm_markdown.py` | Complete |
| Weather charts | `reporting/generate_weather_charts.py` | Complete |
| Maturity maps | `reporting/generate_maturity_maps.py` | Complete (lower-48) |
| Terrain derivative rendering | `reporting/render_terrain_derivatives.py` | Partial (conditioning often skipped) |
| Grower Field Atlas maps | `reporting/generate_grower_web_map.py` | Complete (field dossier with Overview/NDVI/Soil/Terrain/Report tabs) |
| EDA overview/time series/correlations/distributions/field cards/dashboard | `src/scripts/eda/*.py` | Complete |

### 5.3 `my-farm-advisor` — advisory subskills

| Area | Implemented |
| --- | --- |
| **Admin** | L0 countries / L1 states / L2 counties from Natural Earth + Census TIGER; GADM any-country `--gadm-iso`; FIPS lookup; interactive self-contained HTML maps |
| **Data sources** | Deterministic rebuild contract and reporting runner (`farm-intelligence-reporting/src/pipeline.py`, `reporting.py`) |
| **EDA** | Explore, compare, correlate, time-series, visualize workflows with runnable snippets and example figures |
| **Field management** | Boundary ingest/validation, CSB deterministic sampling, headlands/ring geometry |
| **Imagery** | Landsat C2 L2 and Sentinel-2 L2A acquisition via Planetary Computer, NDVI |
| **Soil** | US SSURGO (NRCS SDA) + gNATSGO; Ontario detailed survey; Australia SLGA/ASF + ANSIS; Argentina INTA Entre Ríos; SoilGrids global floor; country routing in `soil/soil-routing.md`; CDL/ACI/MNC crop layers |
| **Strategy** | Crop playbooks (corn, soybean, wheat, cotton, sorghum) and county maturity (RM/MG) maps |
| **Terrain** | DEM source policy and adapters (USGS 3DEP, NASADEM, Copernicus GLO-30, ALOS AW3D30), clipping, slope/aspect/hillshade/curvature/flow proxies, manifests |
| **Weather** | NASA POWER S3 Zarr (default) and point API (debug), daily tables, GDD, county aggregation |

### 5.4 `my-farm-breeding-trial-management`

Implemented as example-first workflows with scripts and reference docs.

| Feature | Status |
| --- | --- |
| RCBD trial design + randomization | Partial (RCBD path works; other designs limited) |
| Alpha-lattice design | Partial (efficiency value hardcoded) |
| Augmented design | Partial (not truly randomized) |
| Fieldbook generation/import | Complete for documented layout |
| Germplasm records | Example-level |
| Selection index / breeding-value ranking | Example-level |
| Crossing plans | Example-level |
| Field-trial placement with field boundaries | Partial (RCBD only despite docstrings) |
| Breedbase client | **Mock** |
| BMS (Breeding Management System) client | **Mock** |
| IoT field sync | Example-level |
| Pedigree management | Partial (inbreeding values hardcoded) |
| `breeding_cli.py` subcommands | **Stubs** |

### 5.5 `my-farm-qtl-analysis`

| Feature | Status |
| --- | --- |
| GWAS (GLM/LMM) | Partial (proxy when GEMMA absent) |
| eQTL cis mapping | Partial (proxy when tensorQTL absent) |
| Classical QTL (R/qtl2) | Partial (proxy when R/qtl2 absent) |
| VCF/SNP QC, filtering, validation | Example-level, runnable |
| Population structure (PCA, admixture, kinship) | Example-level |
| LD decay, haplotype analysis | Example-level |
| Genomic prediction (BLUP, Bayesian, elastic net, CV) | Example-level |
| GxE GWAS/prediction | Example-level |
| Multi-trait GWAS, epistasis, rare-variant tests | Example-level |
| Visualization generation | Complete scripts, but some stale paths |
| `qtl_cli.py` | Optional wrapper |
| GPU/HPC verification | Complete (`verify_gpu_hpc.py`) |

### 5.6 Example figures

Committed example outputs live under `examples/**/output/` and are PNG-only
(`my-farm-advisor/data-pipeline/examples/`, plus breeding/QTL example outputs).
They are vision-reviewed demos, not runtime artifacts. Do not regenerate them
into the repo casually; follow `CONTRIBUTING.md` and `ASSET_POLICY.md`.

---

## 6. Database & Data Models

### 6.1 No database

There is **no database** in this repository: no SQLite, DuckDB, PostgreSQL, ORM,
schema migrations, or server-side store. A search for `.db`, `.sqlite`, and
`.duckdb` tracked files returns nothing.

Data is managed as a **filesystem-based canonical tree** with structured files
and manifests. Parquet is used for tabular/columnar artifacts; GeoJSON for
boundaries and vector products; GeoTIFF for rasters; CSV for small tables;
JSON/JSONL for metadata, manifests, and run logs.

### 6.2 Canonical hierarchy

```text
grower
└── farm
    └── field
        ├── boundary
        ├── soil
        ├── weather
        ├── satellite
        ├── terrain
        ├── manifests
        ├── logs
        └── derived
```

Relationships are encoded by directory nesting and by repeated `grower_slug` /
`farm_slug` / `field_slug` fields in metadata files. There are no foreign keys;
consistency is enforced by path builders (`lib/paths.py`) and slug validation.

### 6.3 Identity and metadata files

| File | Purpose | Example fields |
| --- | --- | --- |
| `growers/<grower>/grower.json` | Grower identity | `grower_slug`, `display_name`, `notes` |
| `growers/<grower>/farms/<farm>/farm.json` | Farm identity and CRS | `grower_slug`, `farm_slug`, `display_name`, `state`, `country`, `default_crs`, `notes` |
| `growers/<grower>/farms/<farm>/fields/<field>/field.json` | Field identity and file pointers | `grower_slug`, `farm_slug`, `field_slug`, `display_name`, `field_id`, `boundary_file`, `soil_file`, `weather_file`, `satellite_dir`, `notes` |
| `.../manifests/field-inventory.csv` | Field registry used by scripts | `field_id`, `field_slug` |
| `.../manifests/pipeline_schedule.json` | Grower-level pipeline run state | run status, active step, per-step results |

Real runtime examples (2026-11-10):

```json
// growers/ia-grower/farms/ia-farm/farm.json
{
  "grower_slug": "ia-grower",
  "farm_slug": "ia-farm",
  "display_name": "Iowa Farm",
  "state": "Iowa",
  "country": "US",
  "default_crs": "EPSG:4326",
  "notes": "Canonical farm metadata"
}
```

```json
// growers/ia-grower/farms/ia-farm/fields/ia-r1/field.json
{
  "grower_slug": "ia-grower",
  "farm_slug": "ia-farm",
  "field_slug": "ia-r1",
  "display_name": "ia-r1",
  "field_id": "IA_R1",
  "boundary_file": "boundary/field_boundary.geojson",
  "soil_file": "soil/ssurgo_soil_types.geojson",
  "weather_file": "weather/daily_weather.csv",
  "satellite_dir": "satellite/",
  "notes": "Canonical field metadata"
}
```

### 6.4 Boundaries

| Path | Format | Notes |
| --- | --- | --- |
| `farms/<farm>/boundary/field_boundaries.geojson` | GeoJSON FeatureCollection | Farm-level union of all fields |
| `fields/<field>/boundary/field_boundary.geojson` | GeoJSON Feature | Per-field polygon/multipolygon |

Boundary properties carry the source identity and the `country` used for
provider routing. For US CSB-sourced fields, the property set can include
`field_id`, area, crop history, and source IDs. Non-US OSM-derived fields carry
OSM identifiers and `country`.

The boundary repository contract (per-source requirements, provider quirks,
new-country checklist) is
`my-farm-advisor/data-pipeline/references/field-boundary-sources.md`.

### 6.5 Field-level asset layout

| Directory | Typical contents |
| --- | --- |
| `boundary/` | `field_boundary.geojson` |
| `soil/` | `ssurgo_soil_types.geojson`, `ssurgo_summary.csv`, `ssurgo_full.csv`, `metadata.json`; Argentina uses `ssurgo_*` filenames despite INTA source (documented quirk) |
| `weather/` | `daily_weather.csv`, `metadata.json` |
| `satellite/landsat/`, `satellite/sentinel/` | Clipped GeoTIFFs and NDVI rasters |
| `terrain/dem/` | DEM tiles/clips and terrain manifests |
| `manifests/` | Per-step JSON manifests, e.g. `ndvi_composite_build_<field>.json`, `dem_terrain_manifest.json` |
| `logs/` | `pipeline_runs.jsonl` |
| `derived/features/` | Extracted features |
| `derived/reports/` | Field posters, NDVI cards, soil cards |
| `derived/summaries/` | Summary tables |
| `derived/tables/` | `dem_terrain_summary.csv/.json`, soil tables |
| `derived/terrain/` | Derived rasters (slope, aspect, hillshade, …) |

### 6.6 Farm-level derived layout

| Directory | Typical contents |
| --- | --- |
| `derived/reports/` | Farm poster, farm HTML, farm Markdown, soil maps |
| `derived/summaries/` | Farm-level summary tables |
| `derived/tables/` | Aggregated tables |
| `derived/dashboards/` | Dashboard outputs (placeholder in inspected runtime) |
| `manifests/` | `field-inventory.csv`, `farm_html_render.json`, `farm_markdown.json`, `farm_poster_render.json`, `csb_fields_provenance.json`, `soilgrids_provenance.json` |

### 6.7 Shared data model

`shared/` holds reusable, non-field-specific assets:

| Path | Contents | Consumers |
| --- | --- | --- |
| `shared/geoadmin/l0_countries/` | Natural Earth countries + metadata | Admin maps, country lookup |
| `shared/geoadmin/l1_states/` | Census TIGER states | US state lookups |
| `shared/geoadmin/l2_counties/` | Census TIGER counties + FIPS lookup Parquet | FIPS assignment, maturity maps |
| `shared/weather/nasa-power/` | Lower-48 county daily weather | County aggregation, maturity |
| `shared/corn_maturity/` | Corn RM by FIPS (annual + 5-year average) | Strategy, maturity maps |
| `shared/soybean_maturity/` | Soybean MG by FIPS | Strategy, maturity maps |
| `shared/cdl/` | CDL rasters + derived composition | Crop history, rotation |
| `shared/dem/` | NASADEM and USGS TNM 3DEP tiles | Terrain |
| `shared/soilgrids/` | 250 m SoilGrids clips/stats | Global soil floor |
| `shared/argentina/inta/` | INTA Entre Ríos soil extracts | Argentina soil |
| `shared/argentina/mnc/` | INTA Mapa Nacional de Cultivos | Argentina crop history |
| `shared/osm/` | Field-source journal/manifests | Boundary provenance |
| `shared/reference/` | Crop codes, schemas, units (metadata) | Cross-cutting |
| `shared/manifests/` | Shared run manifests | Auditing |

Committed `src/shared/` files are **metadata, source records, or tiny manifests
only**. Generated payloads are rebuilt under the runtime root.

### 6.8 Manifests, provenance, and audit trail

Manifests are the closest thing to a schema contract. A typical step manifest
records:

- step/script name and status,
- code fingerprint and config fingerprint,
- input paths and fingerprints,
- output paths,
- `started_at` / `finished_at` timestamps,
- optional warnings and source metadata.

Provenance JSON examples include `csb_fields_provenance.json`:

```json
{
  "source": "FIBOA us-usda-cropland (USDA NASS Crop Sequence Boundaries)",
  "url": "https://data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet",
  "license": "CC-BY-4.0 (FIBOA); USDA public (CSB)",
  "file_crs": "Albers_Conic_Equal_Area",
  "bbox": [42.907762, -94.443289, 43.500468, -93.970201],
  "row_groups_read": 36,
  "total_row_groups": 648,
  "min_area_ha": 40.0,
  "accessed_at": "2026-11-08T06:39:14+00:00",
  "fields": ["ia-r1", "ia-r2", "ia-r3"]
}
```

### 6.9 File format conventions

| Format | Use |
| --- | --- |
| `.json` | Metadata, manifests, provenance, map payloads |
| `.jsonl` | Append-only run logs (`pipeline_runs.jsonl`) |
| `.csv` | Small tabular outputs and inventories |
| `.parquet` | Larger tabular data (FIPS lookups, maturity tables, weather aggregates) |
| `.geojson` | Boundaries, soil polygons, administrative layers |
| `.tif/.tiff` | Satellite and DEM rasters |
| `.png` | Example figures and rendered reports |
| `.html` | Self-contained reports and Field Atlas maps |
| `.md` | Reports, routing docs, guides |

### 6.10 Per-grower particularities (runtime snapshot)

The inspected runtime contains three growers and nine fields:

| Grower | Farm | Fields | Area | Particularities |
| --- | --- | --- | --- | --- |
| `ar-grower` | `ar-farm` | `ar-r1`, `ar-r2`, `ar-r3` | 667.2 ac | INTA soil + MNC crop history; `ssurgo_*` filenames despite INTA source; boundary crop `Unknown` corrected via `field.json`; point weather; reused NASADEM tile |
| `ia-grower` | `ia-farm` | `ia-r1`, `ia-r2`, `ia-r3` | 2,266.2 ac | US SSURGO/CDL/NASA POWER; county FIPS assignment |
| `il-grower` | `il-farm` | `il-r1`, `il-r2`, `il-r3` | 2,352.9 ac | US SSURGO/CDL/NASA POWER; default combined Field Atlas grower |

Runtime sizes at snapshot: `shared/` ~6.3 GB, `growers/` ~1.3 GB. See the
inventory reference for the full breakdown.

---

## 7. API & Integrations

### 7.1 Inbound APIs

**None.** There are no server endpoints, route handlers, OpenAPI specs, or
long-running services in the repository. All interaction is CLI/script-driven
or document-driven. The only "API-like" artifacts are data-service URLs that
the ingest scripts call outbound.

### 7.2 Outbound integrations

| Domain | Provider | Endpoint / mechanism | Key required? |
| --- | --- | --- | --- |
| Weather (default) | NASA POWER | Public S3 Zarr: `nasa-power.s3.us-west-2.amazonaws.com` | No |
| Weather (debug) | NASA POWER point API | `power.larc.nasa.gov` | No |
| Satellite | Microsoft Planetary Computer STAC | `planetarycomputer.microsoft.com/api/stac/v1/search`, collections `sentinel-2-l2a`, `landsat-c2-l2` | No |
| Satellite asset access | Planetary Computer SAS | `planetarycomputer.microsoft.com/api/sas/v1/token` (anonymous SAS signing) | No |
| DEM (US) | USGS TNM 3DEP | `nassgeodata.gmu.edu` / USGS 3DEP services | No |
| DEM (global) | NASADEM / Copernicus GLO-30 / ALOS AW3D30 | AWS public buckets (`copernicus-dem-30m.s3.amazonaws.com`), JAXA/EORC, PC SAS | No |
| Soil (US) | NRCS Soil Data Access | `sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest` | No |
| Soil (AR) | INTA GeoNode | `geo-nodo03.inta.gob.ar` WFS | No |
| Soil (AU) | CSIRO SLGA/ASF DAP mirror | `data.tern.org.au`, `files.isric.org` | No |
| Soil (global) | ISRIC SoilGrids | `files.isric.org` | No |
| Crop history (US) | USDA CDL / NASS | `nassgeodata.gmu.edu` | No |
| Crop history (CA) | AAFC ACI | `agriculture.canada.ca` | No |
| Crop history (global) | WorldCereal v2.8.2 | Optional git-pinned package, model download | No |
| Boundaries (US) | FIBOA / USDA CSB | `data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet` | No |
| Boundaries (global) | OpenStreetMap Overpass | `overpass-api.de`, `overpass.kumi.systems`, `lz4.overpass-api.de`, plus registry rotation | No |
| Admin geography | Natural Earth, US Census TIGER, GADM | `www2.census.gov`, GADM mirrors | No |
| Basemaps (maps) | Esri World Imagery / World Street Map | `server.arcgisonline.com` | No |

### 7.3 Communication flows

**Boundary → data → report:**

```text
CSB GeoParquet / OSM Overpass
        │
        ▼
download_fields.py ──▶ canonical boundaries + field-inventory.csv
        │
        ├─▶ download_dem_terrain.py ──▶ DEM tiles → terrain derivatives
        ├─▶ download_soil.py ──▶ SSURGO/INTA/SLGA/Ontario
        ├─▶ download_soilgrids.py ──▶ global soil clips
        ├─▶ download_weather.py ──▶ NASA POWER Zarr/API
        ├─▶ download_cdl.py ──▶ CDL/ACI/MNC
        └─▶ download_satellite_imagery.py ──▶ STAC → clipped TIFFs → NDVI
        │
        ▼
reporting/* ──▶ posters, cards, maps, HTML, Markdown, Field Atlas
```

**County baseline flow:**

```text
install.sh --prepare-shared-data / init_shared_data.py
  → geoadmin layers
  → county weather aggregation
  → GDD, corn RM, soybean MG by FIPS
  → CDL CONUS rasters (last 5 years)
  → shared/*
```

### 7.4 Resilience and retry behaviour

- NASA POWER and STAC calls use retries with backoff (see
  `lib/satellite_imagery.py` and `lib/nasa_power.py`).
- Overpass rotates across multiple instances and supports `--from-json` replay.
- Provider responses are validated against expected CRS/bbox/attributes before
  acceptance.
- Failures halt the master pipeline at the failing step and are recorded in the
  grower manifest.

### 7.5 Credentials and secrets

No secrets are committed. Optional environment variables
(`DATA_PIPELINE_DATA_ROOT`, `DATA_PIPELINE_VENV_DIR`, `AG_*`) configure
behaviour. The installer may persist only `DATA_PIPELINE_DATA_ROOT` to
`${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf`, and
only in `user` persist mode. Never commit `.env` files.

---

## 8. Authentication & Authorization

### 8.1 Current state

There is **no application authentication or authorization layer**:

- No user accounts, login, sessions, tokens, roles, or permission checks.
- No protected HTTP surface.
- No multi-tenant isolation beyond separate runtime roots.

### 8.2 Security posture

The catalog is designed around **public, keyless data access**:

- NASA POWER public S3 Zarr and point API.
- Planetary Computer STAC search plus anonymous SAS token signing for asset
  reads.
- USGS/NRCS/INTA/CSIRO/ISRIC public endpoints.
- OSM Overpass public instances.
- Esri public basemap tiles at view time.

### 8.3 Controls that do exist

| Control | Implementation |
| --- | --- |
| Path traversal prevention | `validate_path_slug` in `lib/paths.py` rejects empty, `.`, `..`, separators, absolute paths, `://`, and unsafe characters |
| Runtime root isolation | Installer requires an absolute writable root outside the checkout |
| Non-destructive seeding | Safe mode uses `rsync --ignore-existing`; upgrade uses `--checksum`; neither deletes live data |
| Non-interactive divergence guard | A changed source tree requires `--force-refresh`; the installer refuses to overwrite silently |
| Secret hygiene | No committed credentials; only the data root is persisted |
| Asset policy | Validator blocks forbidden paths and runtime geojson payloads |

If authentication is ever added (for example, a hosted report service), it must
be documented here and implemented outside the skill tree so the harness-neutral
contract is preserved.

---

## 9. UI/UX Guidelines

### 9.1 There is no application UI

The repository has no frontend framework, component library, design tokens, or
CSS build. "UI" means generated artifacts:

- **PNG figures** (posters, maps, cards, triangles, charts).
- **Self-contained HTML** (farm reports, Field Atlas maps).
- **Markdown reports**.

### 9.2 Field Atlas map UX

Contract in `my-farm-advisor/data-pipeline/grower-web-map/README.md` and
`GUIDE.md`:

- One standalone HTML map per grower, plus one combined map.
- Default basemap: Esri World Imagery; toggle to Esri World Street Map.
- Field geometry and metadata are embedded; satellite tiles stream at view time.
- The combined map opens on `il-grower` when present and includes an **ALL**
  pill listing every field and fitting the world view.
- Standalone maps link back to the combined atlas; the combined map links to
  each standalone map.
- URL hash links: `#grower=<slug>&field=<id>`, plus
  `&tab=<overview|ndvi|soil|terrain|report>` when a dossier is open.
- Each field opens a dossier drawer (bottom sheet on mobile) with five tabs:
  Overview, NDVI, Soil, Terrain, Report. The map popup stays compact and links
  into the dossier.
- Dossier figures are embedded as base64 WebP previews (max width 1600 px,
  quality 88); full-resolution PNGs, summary CSV/JSON, and the farm HTML report
  stay runtime-relative links. The Report tab shows a large-file warning
  (typically 61–74 MB; individual reports can be larger).
- Portable copies keep embedded figures and hide dead runtime-only links.
  `--no-embed-figures` produces a link-only map under 100 KB.
- Outputs:
  - `growers/growers_field_map.html` (~12 MB with 153 embedded figures)
  - `growers/growers_field_map.json` (records `figure_count`,
    `figures_embedded`, `combined_bytes`)
  - `growers/<grower>/reports/<grower>_field_map.html` (~3–5 MB each)

### 9.3 Report and figure conventions

- **Self-contained HTML**: inline CSS/JS and embedded GeoJSON; no build step.
  Field Atlas maps also inline compressed WebP dossier previews. External
  network access is limited to basemap tiles.
- **Professional palettes**: muted, print-friendly colors; consistent legends;
  readable labels at README size.
- **Posters/cards**: one field per poster; consistent panel order; explicit
  units; honest caveats in captions.
- **Maps**: basemap + overlay; north arrow/scale where appropriate; masked
  nodata; colorbar norms computed from compressed valid pixels.
- **Cross-border maps**: one continuous surface and color ramp across the
  US/Canada border; no per-country palettes or gaps.

### 9.4 Figure quality gate

`CONTRIBUTING.md` requires, for every new capability:

1. At least one rendered demo figure per output type and relevant geography,
   plus one from a country with no specialized source.
2. Vision review before commit (no blank panels, correct masking, legible
   legends, numbers consistent with source).
3. Best available version, with honest caveats.
4. Commit only under `examples/**/output/`.

### 9.5 Accessibility and portability

- HTML outputs should be readable without a build toolchain and degrade
  gracefully if tiles fail.
- Avoid requiring a specific harness or OS path.
- Keep absolute machine paths out of the skill tree; use
  `DATA_PIPELINE_DATA_ROOT` and relative links.

---

## 10. Coding Standards

### 10.1 Python

| Convention | Detail |
| --- | --- |
| Module header | `from __future__ import annotations` |
| Typing | Built-in generics (`list[Path]`, `dict[str, Any]`), `X | None`, explicit return types |
| Entrypoint pattern | `main()` + `if __name__ == "__main__": raise SystemExit(main())` or `main()` |
| CLI | `argparse`; descriptive `--flags`; sensible defaults matching pipeline defaults |
| Imports | Standard library, third-party, then local; `sys.path` insertion only for standalone scripts |
| Bootstrap | Entry scripts call `ensure_runtime_environment()` before importing runtime-only modules |
| Paths | Use `lib/paths.py` builders; never hardcode runtime roots |
| Errors | Raise `SystemExit`/custom exceptions with actionable messages; pipeline halts with context |
| Logging | Print progress plus JSON/JSONL manifests; no silent long-running work |
| Lint intent | `# ruff: noqa` / `# pyright:` comments where dynamic imports or untyped third-party code require it |

### 10.2 Naming

| Entity | Convention | Example |
| --- | --- | --- |
| Skills | kebab-case | `my-farm-advisor` |
| Grower/farm/field slugs | lowercase kebab, safe chars only | `ia-grower`, `ia-farm`, `ia-r1` |
| Scripts | snake_case, verb-led | `download_soil.py`, `generate_farm_html.py` |
| Modules | snake_case | `satellite_imagery.py` |
| Manifests | `<step>_<artifact>.json` or `<step>_render.json` | `ndvi_composite_build_ia-r1.json` |
| Outputs | `<field>_<product>.png`, `<grower>_field_map.html` | `ia-r1_field_map.png` |
| Environment vars | `UPPER_SNAKE` | `DATA_PIPELINE_DATA_ROOT` |
| Metadata keys | `snake_case` | `grower_slug`, `default_crs` |

### 10.3 Code organization

- Keep `SKILL.md` short and route-focused.
- Put long workflows in subtree `README.md`, `GUIDE.md`, `AGENTS.md`, or
  `references/`.
- Keep implementation in `src/`; keep examples in `examples/`; keep docs beside
  the workflow.
- Do not duplicate a workflow across routers when a deeper doc already covers
  it.

### 10.4 Shell

- `#!/usr/bin/env bash` with `set -euo pipefail` (validator uses `set -u -o
  pipefail` and manages non-fatal checks).
- Quote all paths; support spaces.
- Validate inputs before destructive actions.
- Prefer `rsync --ignore-existing` / `--checksum` over delete-and-copy.

### 10.5 R (QTL)

- Single research script (`research/genomic_cv_r.R`); follow base R + common
  packages (`qtl2`, `ggplot2`) conventions already present.

### 10.6 Documentation standards

- Valid frontmatter: `name`, `description`, `license`, `metadata.author`,
  `metadata.version`.
- Relative Markdown links only; no absolute machine paths.
- Keep claims current; drift is a functional bug.
- Document provenance for every import.
- State caveats honestly; mark stubs and proxies.

### 10.7 Validation

`./scripts/validate.sh` enforces:

- Expected top-level skills exist.
- Required `SKILL.md` / `README.md` / `INDEX.md` / `PROVENANCE.md`.
- YAML frontmatter fields.
- Valid relative Markdown links and anchors.
- Forbidden paths.
- Forbidden tracked runtime assets (`countries.geojson`,
  `states_usa.geojson`).
- Geoadmin metadata fields.

It is the only canonical gate. Run it from the repo root after structural or
documentation changes.

---

## 11. Important Technical Decisions

Preserve these unless the user explicitly changes direction.

1. **Skill catalog, not application.** The repo ships documents + scripts, not a
   service. Do not introduce a server, database, or auth layer without an
   explicit request.
2. **Harness neutrality.** `SKILL.md` / `AGENTS.md` / `INDEX.md` are the
   contract. Do not make docs require Hermes, OpenCode, or any specific runtime.
3. **Runtime data lives outside the checkout.** `DATA_PIPELINE_DATA_ROOT` is
   mandatory; generated assets never go under the repo (`data/` is ignored and
   forbidden by the validator).
4. **Runtime source copy wins.** Pipeline commands run from
   `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`, not checkout `src/`. This
   keeps live runs insulated from edits and makes installs reproducible.
5. **Live data is never silently overwritten.** Safe seeding uses
   `--ignore-existing`; upgrades use `--checksum`; divergence requires
   `--force-refresh`.
6. **Keyless-first sources.** Prefer public S3/STAC/WFS/SDA endpoints; avoid
   accounts and API keys. Anonymous SAS signing is used where required.
7. **Country-aware routing, no silent cross-border fills.** Soil, crop history,
   weather, and terrain route on the boundary `country` property. Unsupported
   countries fall back to explicit global products (SoilGrids, WorldCereal).
8. **Manifest-based idempotency.** Fingerprints of code/config/inputs determine
   staleness. `--force` is the explicit override.
9. **Filesystem as the data model.** Directory hierarchy + JSON metadata +
   Parquet/GeoJSON/GeoTIFF. No ORM or database.
10. **One implementation, one doc-sync commit.** Behavior changes and their docs
    ship together.
11. **Examples are vision-reviewed artifacts.** Only curated PNGs under
    `examples/**/output/`; generated runtime outputs stay outside the repo.
12. **LFS for large binaries.** `.npy`, `.npz`, `.raw`, `.bin`, `.so`, `.dylib`,
    `.dll` go through Git LFS; >1 MB assets need reviewer approval.
13. **No vendored Superior Byte Works skills.** The dependency boundary keeps
    `superior-byte-works-skills` external; only the three My Farm Advisor skills
    live here.
14. **Honest maturity metadata.** Partial features are labelled rather than
    presented as production-ready.
15. **Field Atlas is portable by default.** Dossier figures are embedded as
    compressed WebP previews so a copied HTML file remains useful. Full assets
    stay linked from the runtime tree rather than embedded, except field
    geometry and slim metadata. `--no-embed-figures` is the explicit small-file
    fallback.

---

## 12. Known Issues & Pending Tasks

This section records observed limitations at the verified date. Fixing them
should be explicit, scoped work.

### 12.1 Terrain conditioning is often unavailable

- In the inspected runtime, all fields report
  `conditioning_status: skipped_backend_unavailable`.
- Hydrology products (flow accumulation, wetness, depression depth) are
  **advisory proxies**, not drainage design evidence.
- Live DEM downloads exist, but conditioning may require providers/tools not
  present in the environment. Do not claim terrain-conditioned results when the
  manifest says skipped.

### 12.2 Maturity metadata contradicts generated outputs

- Corn/soybean maturity metadata marks outputs as `planned` even though the
  lower-48 county RM/MG outputs are complete for 2021–2025 (3,109 counties).
- Reconcile metadata status before citing maturity as "planned".

### 12.3 Breeding skill is early-stage

- `breeding_cli.py` subcommands are stubs.
- Breedbase and BMS clients are **mocks** (no real network/auth flow).
- Alpha-lattice efficiency is hardcoded.
- Augmented design is not truly randomized.
- Pedigree inbreeding values are hardcoded.
- Field-trial placement supports RCBD only despite broader docstrings.

### 12.4 QTL analysis caveats

- Many methods are **proxies/simulated** when GEMMA, PLINK, tensorQTL, R/qtl2,
  or pyQTL are absent.
- `gwas-lmm` hardcodes "3/3 causal loci recovered" and λ = 1.02.
- `threshold-correction` README reports power 0.0.
- Stale paths exist in `scripts/generate_all_visualizations.py`,
  `scripts/generate_sample_qtl_data.py`, and
  `examples/analysis-report/run_report.py`.

### 12.5 Duplicated example layouts (breeding and QTL)

- Both skills have a canonical grouped layout
  (`examples/<area>/<name>/`) and a flat mirror (`examples/<name>/`).
- Flat copies contain most committed `output/` PNGs; scripts are mostly
  byte-identical, except the flat `bms-client` copy is newer.
- This duplication is a maintenance hazard: fixes can land in only one copy.
  Consolidation is pending.

### 12.6 Runtime placeholders and empty directories

Observed empty in the inspected runtime:

- `shared/reference/*`
- `shared/logs`
- `shared/cdl/metadata`, `manifests`, `derived`, `logs`
- farm `derived/dashboards/`
- per-farm and per-field `pipeline_runs.jsonl`

They are scaffolded but not populated. Do not assume content exists.

### 12.7 Repository hygiene

- No root `LICENSE` file despite Apache-2.0 declarations. Add one if the repo is
  distributed.
- 101 committed PNGs, some >1 MB (`on-r1_terrain_derivatives.png` ~1.12 MB,
  `wc_verify_ia_soy_cdl.png` ~1.10 MB). They are within the asset policy as
  curated examples, but keep them intentional.
- No committed CI workflow; validation is local-only.
- No Python packaging metadata (no root `pyproject.toml` / `setup.py`).
- `__pycache__` directories exist locally but are ignored and untracked.
- `references/runtime-data-inventory.md` and this file were untracked at the
  verified date; commit them when the user requests.

### 12.8 Test coverage

- Only `data-pipeline/src/scripts/tests/smoke_dem_pipeline.py` resembles a test.
- No unit-test suite, fixtures harness, or coverage reporting.
- `scripts/validate.sh` checks structure/docs/assets, not runtime behaviour.

### 12.9 Environment/version risks

- `xarray>=2026.1` with `zarr>=3,<4` is a careful pairing; NASA POWER stores
  are v2 format and are opened with `zarr_format=2`. Changes here can break
  weather ingest.
- WorldCereal is optional and pulls Torch; do not assume it is installed.
- `contextily`, `fiona`, and `rasterio` have native dependencies that may fail
  on minimal systems.

### 12.10 Documentation drift risks

- Long command runbooks duplicated between root `README.md`,
  `my-farm-advisor/README.md`, `data-pipeline/README.md`, and
  `data-pipeline/AGENTS.md`. Update all relevant copies.
- Router descriptions must match actual script behaviour and flags.

---

## 13. Development Guidelines

### 13.1 Before you change anything

1. Read `AGENTS.md` (root), `CONTRIBUTING.md`, and the `AGENTS.md` for the
   subtree you are touching.
2. Read the subtree `SKILL.md` / `INDEX.md` / `README.md` / `GUIDE.md`.
3. Check `git status` and treat unfamiliar files as user work; do not delete or
   overwrite them without investigating.
4. For runtime work, read `data-pipeline/AGENTS.md`,
   `scripts/install.sh`, `src/scripts/bootstrap_runtime.py`, and
   `src/scripts/run_farm_pipeline.py` first.
5. Confirm whether the task is docs-only or code; do not run commands a
   docs-only task explicitly excludes.

### 13.2 Scope discipline

- Branch work should create a new skill unless the user explicitly asks to add,
  extend, or modify an existing skill.
- Keep changes inside the requested skill tree.
- Make the smallest change that satisfies the request; avoid wholesale rewrites.
- Do not vendor, copy, mirror, or partially import Superior Byte Works skills.
- Do not modify parent `SKILL.md`, sibling workflows, or root policy from a
  subskill task unless explicitly requested.

### 13.3 Runtime contract rules

- Set `DATA_PIPELINE_DATA_ROOT` to an absolute writable path **outside** the
  checkout.
- Run pipeline commands from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src` with
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python`.
- Never write generated data, caches, or runtime payloads into the repo.
- Keep `src/` shaped like the runtime tree (`growers/`, `shared/`, `scripts/`).
- Preserve live data: safe seeding `--ignore-existing`, upgrades `--checksum`,
  divergence requires `--force-refresh`.
- Weather defaults: `--weather-backend zarr`, 2021–2025, `lst`. Use `api` only
  for small debug pulls.
- `--structure-test` must remain no-DEM, no-download, dependency-light.

### 13.4 Doc-sync rule

When a feature changes, update every doc that describes it in the same commit:

| Changed | Also update |
| --- | --- |
| Script behavior, flags, outputs | Workflow `README.md` / `GUIDE.md`; `INDEX.md` row if description shifts; root `README.md` if the capability story changed |
| Data source added/removed/tier changed | Coverage ladders in root `README.md` and `my-farm-advisor/README.md`; relevant `data-pipeline/references/` playbook |
| Router (`SKILL.md`, `INDEX.md`, `AGENTS.md`) | Cross-references from sibling routers; run validator |
| Example figures | Only under `examples/**/output/`; regenerate + vision review |

Also update this `PROJECT_CONTEXT.md` when architecture, runtime contract, data
model, integrations, or skill status changes.

### 13.5 Asset policy

- Do not commit `data/`, `node_modules/`, `.cache/`, build artifacts, generated
  `output/` folders (except curated `examples/**/output/`), or runtime geoadmin
  payloads.
- Binary assets >1 MB require LFS + reviewer approval.
- LFS-backed formats: `.npy`, `.npz`, `.raw`, `.bin`, `.so`, `.dylib`, `.dll`.
- Committed `src/shared/` content must remain metadata/source records/tiny
  manifests.
- Run a vision review before committing any figure.

### 13.6 Adding or extending a skill

New skill root needs:

- `SKILL.md` (compact routing entrypoint, valid frontmatter)
- `README.md` (human overview)
- `PROVENANCE.md` (source/import record)
- `INDEX.md` (progressive router)
- `AGENTS.md` (local instructions)
- examples/references/scripts as needed
- validator compatibility

Update `EXPECTED_SKILLS` in `scripts/validate.sh` and the root `README.md` table
when adding a top-level skill.

### 13.7 Extending the pipeline

- Add the script under `src/scripts/ingest/` or `src/scripts/reporting/`.
- Use `lib/paths.py` builders; validate slugs.
- Emit a manifest with code/config/input fingerprints.
- Make it idempotent and `--force`-aware.
- Register the step in `run_farm_pipeline.py` in the correct order.
- Update `data-pipeline/README.md`, `AGENTS.md`, the root coverage docs, and this
  file.
- Add an example figure if it produces a new output family.

### 13.8 Working on breeding or QTL

- Check whether you are editing the grouped canonical example or the flat
  mirror; update both if the behavior is shared.
- Do not present proxy/simulated results as real method output; label them.
- Verify external tool availability (`check_system.py`) before claiming a
  method ran.
- Keep sample data small and provenance clear.

### 13.9 Validation and pre-push

```bash
cd /home/coder/workspace/my-farm-advisor-skills-assignment-1
./scripts/validate.sh
```

Expect a passing run (44 checks at the verified date). Treat failure as a
blocker unless the task is docs-only and explicitly says not to run commands.

For runtime changes, also run the installer smoke and structure test described
in `data-pipeline/AGENTS.md`.

### 13.10 Commit and sync

- Commit messages should name both code and docs touched.
- Keep the skills tree and any mirrored monorepo `skills/` folder byte-identical
  when the workflow requires mirroring.
- Do not commit runtime artifacts, secrets, or absolute machine paths.
- Only stage/commit when the user asks.

---

## Appendix A. Key File Map

| Concern | File |
| --- | --- |
| Repo purpose and coverage | `README.md` |
| Agent instructions | `AGENTS.md` |
| Contribution/doc-sync rules | `CONTRIBUTING.md` |
| Provenance template | `PROVENANCE.md` |
| Import records | `IMPORT_MANIFEST.md`, `FINAL_IMPORT_MANIFEST.md` |
| Asset policy | `ASSET_POLICY.md`, `.gitattributes`, `.gitignore` |
| Validation | `scripts/validate.sh` |
| Farm routing | `my-farm-advisor/SKILL.md`, `INDEX.md`, `AGENTS.md` |
| Farm overview | `my-farm-advisor/README.md` |
| Pipeline runtime contract | `my-farm-advisor/data-pipeline/AGENTS.md`, `README.md` |
| Installer | `my-farm-advisor/data-pipeline/scripts/install.sh` |
| Bootstrap/re-exec | `my-farm-advisor/data-pipeline/src/scripts/bootstrap_runtime.py` |
| Path builders | `my-farm-advisor/data-pipeline/src/scripts/lib/paths.py` |
| Runtime path resolution | `my-farm-advisor/data-pipeline/src/scripts/lib/runtime_paths.py` |
| Skill module loading | `my-farm-advisor/data-pipeline/src/scripts/reporting_bootstrap.py` |
| Master pipeline | `my-farm-advisor/data-pipeline/src/scripts/run_farm_pipeline.py` |
| Shared initialisation | `my-farm-advisor/data-pipeline/src/scripts/init_shared_data.py` |
| Dashboard orchestration | `my-farm-advisor/data-pipeline/src/scripts/farm_dashboard.py` |
| Idempotency library | `my-farm-advisor/data-sources/farm-intelligence-reporting/src/pipeline.py` |
| Soil routing | `my-farm-advisor/soil/soil-routing.md` |
| Boundary sources | `my-farm-advisor/data-pipeline/references/field-boundary-sources.md` |
| Crop rotation sources | `my-farm-advisor/data-pipeline/references/crop-rotation-sources.md` |
| Non-US soil sources | `my-farm-advisor/references/non-us-soil-sources.md` |
| Canada geodata | `my-farm-advisor/references/canada-shared-geodata.md` |
| Geoadmin policy | `my-farm-advisor/docs/GEODATA.md` |
| Field Atlas contract | `my-farm-advisor/data-pipeline/grower-web-map/README.md`, `GUIDE.md` |
| Terrain contract | `my-farm-advisor/terrain/dem-terrain/README.md` |
| Runtime inventory | `my-farm-advisor/data-pipeline/references/runtime-data-inventory.md` |
| Breeding skill | `my-farm-breeding-trial-management/SKILL.md`, `INDEX.md` |
| QTL skill | `my-farm-qtl-analysis/SKILL.md`, `INDEX.md` |

---

## Appendix B. Glossary

| Term | Meaning |
| --- | --- |
| **Grower** | Top-level data owner (a farm business or person) |
| **Farm** | A managed unit within a grower |
| **Field** | A boundary polygon with per-field assets |
| **Runtime root** | `DATA_PIPELINE_DATA_ROOT`; external storage for generated data |
| **Canonical tree** | The `growers/<grower>/farms/<farm>/fields/<field>` layout |
| **Shared** | Reusable, non-field-specific assets under `shared/` |
| **Manifest** | JSON record of a step's inputs, outputs, fingerprints, timestamps |
| **Provenance** | Source URL, licence, CRS, bbox, access time, row-group info |
| **CSB** | USDA NASS Crop Sequence Boundaries |
| **FIBOA** | Field Boundaries for Agriculture; hosted CSB GeoParquet |
| **CDL** | USDA Cropland Data Layer |
| **ACI** | Annual Crop Inventory (Canada, AAFC) |
| **MNC** | Mapa Nacional de Cultivos (INTA, Argentina) |
| **SSURGO** | USDA soil survey geographic database |
| **SDA** | NRCS Soil Data Access |
| **SLGA/ASF** | Australian soil attribute grids |
| **ANSIS** | Australian National Soil Information System |
| **RM / MG** | Corn relative maturity / soybean maturity group |
| **GDD** | Growing degree days |
| **NDVI** | Normalized Difference Vegetation Index |
| **DEM** | Digital Elevation Model |
| **STAC** | SpatioTemporal Asset Catalog (Planetary Computer) |
| **SAS** | Shared Access Signature (anonymous asset signing) |
| **RCBD** | Randomized Complete Block Design |
| **GWAS** | Genome-Wide Association Study |
| **eQTL** | Expression quantitative trait locus |
| **Field Atlas** | The standalone grower web-map product |

---

## Appendix C. Quick Commands

### Validate the repository

```bash
cd /home/coder/workspace/my-farm-advisor-skills-assignment-1
./scripts/validate.sh
```

### Install and run the pipeline

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh

cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py --structure-test
```

### Run a farm

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py \
  --grower-slug il-dekalb-grower \
  --farm-slug dekalb-demo-farm \
  --farm-name "DeKalb Demo Farm" \
  --weather-backend zarr \
  --weather-start-year 2021 \
  --weather-end-year 2025 \
  --weather-time-standard lst
```

### Prepare shared baselines

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --prepare-shared-data
```

### Generate Field Atlas maps

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py
```

Add `--no-embed-figures` for a small link-only map, or
`--figure-max-width` / `--figure-quality` to tune embedded previews.

### Installer smoke (no deps, temp root)

```bash
tmp_root="$(mktemp -d)"
DATA_PIPELINE_DATA_ROOT="$tmp_root" \
  ./scripts/install.sh --non-interactive --force-refresh --no-install-deps
```

---

*End of document. Keep it accurate; update it with the code.*
