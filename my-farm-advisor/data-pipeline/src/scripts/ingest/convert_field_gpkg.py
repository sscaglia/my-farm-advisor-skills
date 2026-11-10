#!/usr/bin/env python3
"""Import farm field boundaries from a GeoPackage into the canonical tree.

The default pipeline fetches OpenStreetMap fields for a US county.  When a
grower supplies digitised boundaries (for example an Argentine shapefile
exported to GeoPackage), this script normalises them to the same canonical
layout: one EPSG:4326 ``field_boundaries.geojson``, one per-field GeoJSON, the
``field-inventory.csv`` slug map, and updated ``farm.json`` metadata.

Example
-------
::

    python scripts/ingest/convert_field_gpkg.py \
        --gpkg /tmp/NewFields.gpkg --layer lote_simple_mariano \
        --grower-slug ar-grower --farm-slug ar-farm --farm-name "Entre Ríos Farm" \
        --field-prefix ar --country AR --state "Entre Ríos"

``area_acres`` is always computed in a hemisphere-aware UTM CRS so southern
fields are not distorted by a northern-zone projection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import (  # pyright: ignore[reportMissingImports]
    DATA_ROOT,
    farm_boundary_path,
    farm_dir,
    farm_manifest_dir,
    field_boundary_path,
)
from projection import utm_crs_for_geometry  # pyright: ignore[reportMissingImports]
from reporting_bootstrap import (  # pyright: ignore[reportMissingImports]
    ensure_canonical_data_tree,
    field_slug_map_from_inventory,
)

SQUARE_METERS_PER_ACRE = 4046.8564224


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpkg", required=True, help="Source GeoPackage path")
    parser.add_argument("--layer", default=None, help="Layer name (defaults to the first layer)")
    parser.add_argument("--grower-slug", default=os.environ.get("AG_GROWER_SLUG", "default-grower"))
    parser.add_argument("--farm-slug", default=os.environ.get("AG_FARM_SLUG", "default-farm"))
    parser.add_argument("--farm-name", default=None, help="Farm display name")
    parser.add_argument("--field-prefix", default=None, help="Field ID prefix, e.g. 'ar' -> ar-r1")
    parser.add_argument("--id-field", default=None, help="Existing layer attribute to use as field_id")
    parser.add_argument("--name-field", default=None, help="Optional layer attribute for field name")
    parser.add_argument("--country", required=True, help="ISO country code written to every field, e.g. AR")
    parser.add_argument("--state", default=None, help="State / province label written to every field")
    parser.add_argument(
        "--inventory",
        default=None,
        help="Inventory CSV target (defaults to the farm manifests directory)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing boundaries")
    return parser.parse_args()


def _pick_layer(path: Path, layer: str | None) -> str:
    layers = gpd.list_layers(path)
    if layers.empty:
        raise SystemExit(f"No layers found in {path}")
    if layer:
        if layer not in set(layers["name"].astype(str)):
            raise SystemExit(f"Layer '{layer}' not found. Available: {', '.join(layers['name'])}")
        return layer
    return str(layers.iloc[0]["name"])


def _normalize_geometry(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    frame["geometry"] = frame.geometry.make_valid()
    # Explode multi-part geometries so every row is a single field polygon;
    # dissolve back to one row per original record when a field is split.
    return frame.reset_index(drop=True)


def main() -> int:
    args = parse_args()
    source_path = Path(args.gpkg)
    if not source_path.exists():
        raise SystemExit(f"GeoPackage not found: {source_path}")

    grower_slug = args.grower_slug
    farm_slug = args.farm_slug
    farm_name = args.farm_name or f"{farm_slug} farm"
    inventory_path = (
        Path(args.inventory)
        if args.inventory
        else farm_manifest_dir(grower_slug, farm_slug) / "field-inventory.csv"
    )

    canonical_output = farm_boundary_path(grower_slug, farm_slug)
    if canonical_output.exists() and not args.force:
        raise SystemExit(
            f"Canonical boundaries already exist: {canonical_output}. Pass --force to overwrite."
        )

    ensure_canonical_data_tree(
        grower_slug=grower_slug,
        farm_slug=farm_slug,
        farm_name=farm_name,
        inventory_path=inventory_path if inventory_path.exists() else None,
        country=args.country,
        state=args.state,
    )

    layer = _pick_layer(source_path, args.layer)
    print(f"Reading layer '{layer}' from {source_path}")
    fields = gpd.read_file(source_path, layer=layer)
    if fields.empty:
        raise SystemExit("Source layer has no features")
    fields = _normalize_geometry(fields)
    fields = fields.to_crs("EPSG:4326")

    prefix = args.field_prefix or f"{grower_slug.split('-')[0] or 'field'}"
    existing_ids = (
        fields[args.id_field].astype(str).str.strip().tolist()
        if args.id_field and args.id_field in fields.columns
        else []
    )

    records: list[dict[str, object]] = []
    geometries = []
    for index, row in fields.iterrows():
        if index < len(existing_ids) and existing_ids[index]:
            field_id = existing_ids[index]
        else:
            field_id = f"{prefix}-r{index + 1}"
        record = {
            "field_id": field_id,
            "field_slug": field_id,
            "country": args.country.strip().upper(),
            "state": (args.state or "").strip(),
            "source": f"gpkg:{source_path.name}:{layer}",
            "region": (args.state or args.country).strip(),
            "crop_name": "Unknown",
        }
        if args.name_field and args.name_field in fields.columns:
            record["field_name"] = str(row[args.name_field])
        records.append(record)
        geometries.append(row.geometry)

    output = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    output["area_acres"] = [
        float(gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(utm_crs_for_geometry(geom)).area.iloc[0])
        / SQUARE_METERS_PER_ACRE
        for geom in output.geometry
    ]
    output = output.sort_values("field_id").reset_index(drop=True)

    canonical_output.parent.mkdir(parents=True, exist_ok=True)
    output.to_file(canonical_output, driver="GeoJSON")
    print(f"Wrote {len(output)} fields -> {canonical_output}")

    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"field_id": output["field_id"], "field_slug": output["field_slug"]}
    ).to_csv(inventory_path, index=False)
    print(f"Wrote inventory -> {inventory_path}")

    ensure_canonical_data_tree(
        grower_slug=grower_slug,
        farm_slug=farm_slug,
        farm_name=farm_name,
        inventory_path=inventory_path,
        country=args.country,
        state=args.state,
    )

    for _, row in output.iterrows():
        field_slug = str(row["field_slug"])
        target = field_boundary_path(grower_slug, farm_slug, field_slug)
        target.parent.mkdir(parents=True, exist_ok=True)
        gpd.GeoDataFrame([row], geometry="geometry", crs=output.crs).to_file(
            target, driver="GeoJSON"
        )

    farm_metadata_path = farm_dir(grower_slug, farm_slug) / "farm.json"
    farm_metadata = json.loads(farm_metadata_path.read_text(encoding="utf-8"))
    farm_metadata.update(
        {
            "display_name": farm_name,
            "state": (args.state or "").strip(),
            "country": args.country.strip().upper(),
            "boundary_source": str(source_path),
            "boundary_layer": layer,
            "default_crs": "EPSG:4326",
        }
    )
    farm_metadata_path.write_text(
        json.dumps(farm_metadata, indent=2) + "\n", encoding="utf-8"
    )

    provenance = {
        "imported_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_path": str(source_path),
        "source_layer": layer,
        "field_count": int(len(output)),
        "field_ids": output["field_id"].tolist(),
        "total_area_acres": round(float(output["area_acres"].sum()), 3),
        "area_crs": "per-field WGS84 UTM (hemisphere-aware)",
        "country": args.country.strip().upper(),
        "state": (args.state or "").strip(),
    }
    provenance_path = (
        farm_manifest_dir(grower_slug, farm_slug) / "field_import_provenance.json"
    )
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote provenance -> {provenance_path}")

    print("\nField summary:")
    for _, row in output.iterrows():
        print(
            f"  {row['field_id']:>10}  {float(row['area_acres']):8.2f} ac  "
            f"{row['country']}  {row['state']}"
        )
    print(f"\nRuntime data root: {DATA_ROOT}")

    # Sanity check the slug map the rest of the pipeline will use.
    slugs = field_slug_map_from_inventory(inventory_path)
    if len(slugs) != len(output):
        print(
            f"  warn  inventory slug count ({len(slugs)}) differs from field count ({len(output)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
