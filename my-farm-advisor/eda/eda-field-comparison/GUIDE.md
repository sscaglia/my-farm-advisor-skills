---
name: eda-field-comparison
description: Field-level EDA across growers — compare field boundaries, CDL/MNC cropland history, and weather series for a multi-grower runtime, and emit static figures, tables, and a manifest plus a one-page cross-grower verdict table.
version: 0.1.0
tags: [eda, field-boundaries, cropland, weather, multi-grower, static-figures]
---

# Workflow: eda-field-comparison

Code-backed EDA subskill. It reads the runtime tree, computes three categories of
field-level comparison, and writes static artifacts (PNG / CSV / JSON). Nothing is
downloaded, nothing is written back into the grower tree.

**It is not a dashboard and it is not a report.** Report assembly is a separate,
one-time step that reads `manifest.json` and `cross_grower_summary.csv`; it does not
belong in this reusable subskill.

## When to use it

- You have a runtime with **more than one grower** (each grower = one farm) and you
  want the field-level story behind the data: are the fields comparable in size and
  shape, does the rotation differ, is the weather actually independent between fields?
- You are about to model, and need to know whether `field_id` is a meaningful
  experimental unit or just a row label.
- You are re-running after a data rebuild and want the same artifacts to compare.

Do **not** use it when:

- you want a single-field profile or a time series for one field — use the pipeline's
  own `render_field_maps.py` and the `weather/` / `imagery/` subtree guides;
- you want a soil comparison — out of scope by design;
- you want an interactive map — the admin/atlas web maps cover that.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  my-farm-advisor/data-pipeline/src/scripts/eda/run_field_comparison.py \
  --out /tmp/field-eda
```

Defaults: every grower and farm under `$DATA_PIPELINE_DATA_ROOT/data-pipeline/growers`
that has `boundary/field_boundaries.geojson`; output under
`$DATA_PIPELINE_DATA_ROOT/data-pipeline/eda/field-comparison`.

| Flag | Effect |
| --- | --- |
| `--growers il-grower ar` | restrict to grower slugs or codes (`il`, `ia`, `ne`, `ar`) |
| `--out DIR` | artifact root instead of the runtime default |
| `--no-figures` | tables + manifest only |
| `--no-maps` | skip the three grower plates (offline / slow tiles) |
| `--latest-year 2024` | year for the latest-crop plate (default: newest mapped year) |

The entrypoint is a thin runtime wrapper around
`my-farm-advisor/eda/eda-field-comparison/src/cli.py`; call the CLI directly only if
the skill tree is already on `sys.path`.

## Inputs

| Path under `<farm>/` | Used for | Required columns |
| --- | --- | --- |
| `boundary/field_boundaries.geojson` | geometry, identity, label | `field_id`, geometry (any CRS; reprojected to 4326) |
| `derived/tables/*_cdl.csv` | cropland composition, rotation | `field_id`, `year`, `crop_name`, `pct`; AR also `agricultural_share`, `cropland_status`, `season` |
| `derived/tables/<code>_weather_*.csv` | weather | `field_id`, `date`, plus all of `T2M`, `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`, `ALLSKY_SFC_SW_DWN`, `RH2M`, `WS10M` |

Hard refusals (raise, do not silently degrade): missing boundary file, duplicate
`field_id` in the boundary file, crop table without `field_id`/`year`/`crop_name`,
weather table without `field_id`/`date` or with a missing value column. A missing
*category* is a warning, not a refusal: a grower without a crop table loses the
cropland figures but still gets boundaries and weather.

Data-quality warnings are collected into `manifest.json: warnings` and printed, never
swallowed: duplicate field-days (dropped, counted), short series (fewer days than the
farm's calendar), crop `field_id`s absent from the boundaries, multiple weather tables
for one grower.

## The four comparisons

| Question | Scope | Where it lands |
| --- | --- | --- |
| Does one field change over time? | field × year, 2021-2025 | `cropland/field_crop_sequence.csv` + heatmap |
| Are fields within a grower alike? | field within grower | `boundaries/field_geometry.csv`, `weather/weather_series.csv` |
| Do growers differ? | grower | `boundaries/geometry_tests.csv`, `cropland/crop_tests.csv`, `weather/weather_audit.csv`, `cross_grower_summary.csv` |
| Do the categories agree? | cross-category | `cross_grower_summary.csv` — the same four growers ranked by size, rotation, water |

Boundaries are a **single snapshot**: they are cross-sectional by construction, and
the only time axis in this subskill is cropland (5 annual maps) and weather (1,826
daily records per farm).

## Method contract

These are the decisions that make the numbers correct; keep them when extending.

1. **Weather is aggregated per distinct series, never per field.** A farm with ten
   fields and one weather cell writes ten identical daily series. The CLI hashes each
   field's rounded daily values, labels identical series `xx-S1`, `xx-S2`, ..., and
   drops duplicate `(series_id, date)` rows **before** any sum or mean. Summing the
   raw rows inflates annual precipitation and GDD ten-fold.
   `weather/weather_series.csv` keeps the field → series mapping so every field-level
   claim remains traceable.
2. **Crop class comes from the CDL/MNC table, never the boundary `crop` hint.**
   Argentine OSM boundaries carry `crop_name: "Unknown"`; the boundary attribute is a
   human override slot, not evidence.
3. **`Non-agricultural` is a land-cover class, not an "other crop".** It is MNC class
   22 (pasture / natural land). It stays in the composition table so pasture share is
   visible, but `is_managed_crop = False` keeps it out of rotation claims. The
   non-crop vocabulary is imported from `soil/cdl-cropland/src/cdl_reporting.py`
   (`NON_CROP_LABELS`) so the two layers cannot drift; a literal fallback keeps the
   module importable outside the repo.
4. **A field-year is *split* when the dominant class holds < 60 %** of the field's
   pixels (`SPLIT_DOMINANCE_PCT`). Same threshold the CDL reporting layer already
   uses; split years are annotated in the heatmap and counted in the summary.
5. **One season per field-year.** When MNC ships summer *and* winter extractions, the
   season covering the most pixels wins, so area is never double-counted.
6. **GDD10 = Σ max(T2M − 10 °C, 0)** over the calendar year, using NASA POWER's daily
   mean (`T2M`), not `(T2M_MAX + T2M_MIN)/2`. A year is trusted at ≥ 90 % daily
   coverage (`MIN_YEAR_COVERAGE`); `coverage` and `coverage_ok` travel with the
   aggregates.
7. **Area and perimeter are geodesic** (WGS84 ellipsoid), so an Argentine field and an
   Illinois field are measured with one ruler. Compactness is the isoperimetric
   quotient `4πA/P²` (1.0 = circle, ~0.79 = square, < 0.4 = strongly elongated);
   aspect ratio and long-edge bearing come from the minimum rotated rectangle in the
   field's own UTM zone.
8. **p-values at n = 4 growers are descriptive.** Ten fields per grower is *not* ten
   independent climate observations (see rule 1), and the growers were not sampled.
   Every test therefore ships an effect size — Cliff's delta for pairwise
   Mann-Whitney, Holm-corrected p-values, ε² for Kruskal-Wallis, Cramér's V for
   chi-square, Spearman ρ for size-vs-shape — and the verdict text says what the
   effect size means. Do not quote a p-value from these tables as inference.

## Artifact contract

```
boundaries/  field_geometry.csv          one row per field: geodesic area, perimeter,
                                         compactness, aspect ratio, long-edge bearing,
                                         centroid  → CSV is the id-to-measurement key
             geometry_tests.csv          Kruskal-Wallis + pairwise Mann-Whitney (Holm)
                                         + Spearman size-vs-shape, long form with verdict
             field_area_by_grower.png    A1
             compactness_vs_area.png     A2
cropland/    field_crop_sequence.csv     field × year dominant class + purity + split
             crop_composition.csv        grower × year × class share (+ field_years)
             crop_transitions.csv        consecutive-year class changes per grower
             crop_tests.csv              chi-square (mix, rigidity) + per-grower descriptors
             crop_composition_by_grower_year.png   B1
             field_crop_sequence.png               B2
weather/     weather_series.csv          field → series_id, span, day count
             weather_annual_by_series.csv  series × year: precip, GS precip, GDD10,
                                         frost/dry days, coverage
             weather_monthly_by_farm_year.csv  grower × year × month means
             weather_series_correlation.csv    pairwise daily Pearson r (T2M, precip)
             weather_audit.csv           per grower: fields vs series, spread, verdict
             annual_precip_by_series.png        C1
             monthly_temperature_climatology.png C2
maps/        boundaries_by_grower.png     A4
             latest_crop_map.png         B4
             weather_series_map.png      C4
cross_grower_summary.csv                 one row per grower: the whole story
manifest.json                            provenance, thresholds, hashes, warnings
README.md                                generated index (do not hand-edit)
```

`manifest.json` records the data root, out root, per-grower row counts, the distinct
series count, years, thresholds, method notes, warnings, and a SHA-256 per artifact.

## What each figure says

Write-ups assume the current Assignment 2 runtime (four growers × ten fields,
2021-2025); the code makes no assumption about those values.

**A1 `field_area_by_grower.png` — "field size separates the growers before agronomy
enters the picture."** Strip + box, log axis. Medians: IL 245 ha, IA 243, NE 221, AR
143. Argentina is a different population (61-147 ha, no overlap with the US growers,
Cliff's δ = −1.00 against each), not a smaller sample of the same one. Kruskal-Wallis
p < 0.001 is shown but flagged descriptive.

**A2 `compactness_vs_area.png` — "small fields are also elongated — shape is not just
size."** Compactness against area with a binned-median curve. Across all 40 fields
Spearman ρ = −0.65 (p < 0.001): bigger fields are more compact, i.e. long thin parcels
are a *size* effect in this dataset. Within a grower the relationship collapses (ρ from
−0.44 to +0.62, none significant at n = 10) — which is the honest reading: the
cross-grower trend is driven by AR's small, blocky parcels vs IL's large, elongated
ones.

**B1 `crop_composition_by_grower_year.png` — "crop mix is grower identity."** 100 %
stacked bars, grower × year, dominant class. IL/IA alternate corn–soy near 50/50,
NE is corn-heavy (70-90 % corn), AR is soy-first with a large non-agricultural share
that shrinks across the five years. Chi-square grower × class V = 0.49.

**B2 `field_crop_sequence.png` — "five years per field: rotation, monoculture, and the
AR conversion."** The 40 × 5 categorical grid, grouped by grower, one block per field.
Rotation change rates: IA 98 %, IL 90 %, AR 45 %, NE 32 %; effective class counts 2.0 /
2.0 / 2.8 / 1.6. NE is *not* continuous corn — two parcels (`ne-r4`, `ne-r10`) rotate
soy in, the rest stay corn. AR shows the pasture block (`ar-o1..o3`, non-agricultural
all five years) and parcels converted to soy in 2024-2025. Bold percentages mark split
field-years (`il-r3` 2024, `ne-r1` 2025, `ar-o2`/`ar-o4`/`ar-o7` in several years).

**C1 `annual_precip_by_series.png` — "water supply: Argentina is wettest and most
volatile, Nebraska driest."** One line per distinct series, mean per grower, so the
reader can see both the spread and the level. Annual totals on this runtime: NE
463-750 mm, IA 577-1 027, IL 782-1 091, AR 733-1 190. AR is a single series: its
year-to-year swing is climate, not field-to-field variation.

**C2 `monthly_temperature_climatology.png` — "season length, not just rainfall,
separates the four growers."** Monthly mean with a min-max band per grower. Southern-
hemisphere AR inverts the curve; NE runs hottest in summer and coldest in winter.
GDD10 (base 10 °C) across series-years: IA 1 677-1 974, IL 1 901-2 140, NE 2 055-2 342,
AR 2 920-3 547.

**Map plates (A4 / B4 / C4)** — four grower panels each, Esri World Imagery underlay,
grower-local metre axes, boxed north arrow, no scale bar.

- A4 `boundaries_by_grower.png`: "ten dispersed parcels per grower, not one block."
  The parcels are county-scale footprints spread over 20-60 km, not contiguous
  blocks. This killed an earlier draft claim ("contiguous blocks in NE/IL") that the
  imagery disproved.
- B4 `latest_crop_map.png`: dominant class per parcel in the latest mapped year.
- C4 `weather_series_map.png`: identical fill = identical daily series. This is the
  visual form of the de-duplication rule: AR's ten parcels are one colour because
  they are one weather series.

None of the plates carry per-field ids: at 40-60 km width a 6 pt id is unreadable at
README size, and the sequence plate already labels all 40 fields legibly. Field ids
live in `field_geometry.csv` (with centroids) and `field_crop_sequence.csv`.

## Map contract compliance

`data-pipeline/references/field-map-frame.md` and `basemap.md` are the contracts; this
subskill deliberately extends them from one field to a farm union:

- the frame is fitted to the **farm union**, so the axis label says "frame rotated",
  not "field rotated";
- metre tick axes stay visible and honest, and there is **no scale bar** — the repo
  default, since the ticks already carry distance;
- Esri World Imagery is drawn first, warped into the same rotated frame, and covers
  the padded viewport, with a single figure-level "Imagery © Esri" credit;
- the north arrow is placed in the emptiest corner (scored from parcel centroids) and
  pulled back along its own direction so the boxed `N` stays inside the axes — a fixed
  top-right anchor lands on `ne-r4` and pushes the `N` into the next panel on a 86°
  rotation;
- panel rows are sized from each row's content aspect, so `set_aspect("equal")` fills
  the box instead of letterboxing a wide farm union.

## Limits of the first build

- Boundaries are one snapshot; there is no boundary-change history to compare.
- Weather is NASA POWER per grower grid cell — the series count is the real
  replication count, often 1. Do not compute field-level weather statistics.
- No soil, no imagery indices, no yield: deliberately out of scope for this subskill.
- Group tests assume nothing but ranks; with four growers they describe, they do not
  infer.
- The maps resolve to county scale; individual parcels are 1-3 % of panel width.

## Tests

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  my-farm-advisor/data-pipeline/src/scripts/tests/smoke_field_eda.py
```

The smoke test builds a synthetic two-grower runtime (four fields, two years, one
grower with a single shared weather series and one grower with two distinct series)
and asserts the de-duplication invariant, the series count, the artifact set, the
split-flag threshold, and that crop class and AR land status come from the table. It
runs offline and needs no network tiles.
