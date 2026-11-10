# Local Instructions

## Purpose

This folder owns the grower-level Field Atlas web-map workflow. It turns
canonical runtime field boundaries into standalone HTML maps and one optional
combined grower map, each with a per-field dossier for NDVI, soil, terrain, and
report review.

## Safe edit scope

Edits should stay in this folder, the generator at
`../src/scripts/reporting/generate_grower_web_map.py`, and the grower report
path helpers in `../src/scripts/lib/paths.py`, unless the user explicitly asks
for a broader change.

Do not modify parent `SKILL.md`, sibling workflows, or root policy from a
subskill task.

## Read nearby docs first

Read `README.md` first, then `GUIDE.md`. For the Leaflet baseline and sample
map shape, read `../../admin/interactive-web-map/GUIDE.md` and its
`examples/README.md`. For runtime rules, read `../AGENTS.md` and
`../README.md`.

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` is required and must be absolute.
- Run the generator from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src` after
  installing or refreshing the runtime source copy.
- Generated maps and manifests belong under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`, never in the checkout.
- The map embeds field geometry and metadata, plus compressed WebP previews of
  field dossier figures, so a copied HTML file stays usable. Basemap tiles
  stream from Esri; do not embed imagery or rasters.
- Full-resolution PNGs, summary CSVs/JSON, and farm report links are runtime
  relative links. Do not turn them into embedded copies of full assets.
- Embedded figures are enabled by default and require Pillow from
  `requirements.txt`. `--no-embed-figures` is the small-HTML fallback.
- Keep generated HTML, manifests, and runtime payloads out of Git.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes.
For generated maps, follow the checks in `GUIDE.md`. There is no headless
browser in the standard environment.
