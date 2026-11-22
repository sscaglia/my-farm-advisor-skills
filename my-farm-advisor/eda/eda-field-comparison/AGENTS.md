# Local Instructions

## Purpose

This folder owns the **code-backed** field-level EDA across growers: boundary geometry,
CDL/MNC cropland history, and weather-series comparison. It produces static artifacts
only. It is the one EDA subtree with runnable source, so it is also the one where a code
change can silently change a number that ends up in a report.

## Safe edit scope

Edits stay in this folder and its children. Do not change the sibling EDA guides, parent
`SKILL.md`, or root policy from a subskill task unless explicitly asked. The runtime
entrypoint (`data-pipeline/src/scripts/eda/run_field_comparison.py`) is a deliberate thin
wrapper: keep it thin.

## Read nearby docs first

Read `GUIDE.md` for the method contract and the artifact contract. Read `../../SKILL.md`
and `../INDEX.md` only when routing context is needed. Map changes also require
`data-pipeline/references/field-map-frame.md` and `basemap.md`.

## Non-negotiable invariants

Changing any of these changes every number downstream; treat as a contract, not a detail.

1. Weather is hashed into distinct series and de-duplicated **before** any aggregation.
   Never aggregate per field row.
2. Crop class comes from the CDL/MNC table, never from the boundary `crop` hint.
3. `Non-agricultural` is land cover, not a crop; `is_managed_crop` gates rotation claims.
4. `SPLIT_DOMINANCE_PCT = 60` and the CDL layer's threshold must not fork.
5. Effect sizes are the claim; p-values at n = 4 growers are descriptive and must keep
   that caveat in the verdict text.
6. No scale bar on any plate; metre ticks carry distance.

## Local validation

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  my-farm-advisor/data-pipeline/src/scripts/tests/smoke_field_eda.py
./scripts/validate.sh   # from the repo root
```

For a full re-render, point `--out` at a scratch directory outside the repo
(`/tmp/field-eda`), never inside the skill tree. Commit only the reviewed example
figures under `examples/output/`.

## Figure review gate

Any change to `src/figures.py` or `src/field_maps.py` re-triggers the five-point vision
review in `CONTRIBUTING.md` for **every** figure those modules draw, including the map
plates. Do not commit a regenerated figure unseen.

## Local-delta-only reminder

This file records only what differs from the parent and root instructions. Root asset,
vendor, and validation policy is not duplicated here; see `../../../AGENTS.md`.
