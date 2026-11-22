#!/usr/bin/env python3
"""Field-level EDA for a multi-grower runtime: boundaries, cropland, weather.

Produces static artifacts under ``<runtime>/data-pipeline/eda/field-comparison``:

    boundaries/   field geometry table, tests, 2 figures
    cropland/     composition, sequence, transitions, tests, 2 figures
    weather/      series map, annual/monthly aggregates, audit, 2 figures
    maps/         grower-level boundary / 2025-crop / weather-series maps
    cross_grower_summary.csv, manifest.json, README.md

The subskill stops here.  Report assembly is a separate, one-time step that
reads ``manifest.json`` and ``cross_grower_summary.csv``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import cropland_metrics as cm
import datasets as ds
import figures as fg
import geometry_metrics as gm
import weather_metrics as wm


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Field-level EDA across growers (boundaries, cropland, weather)."
    )
    parser.add_argument(
        "--growers",
        nargs="*",
        default=None,
        help="Grower slugs or codes (il-grower, ia, ne ...). Default: every grower.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Artifact root. Default: <runtime>/data-pipeline/eda/field-comparison.",
    )
    parser.add_argument(
        "--no-figures",
        action="store_true",
        help="Write tables and the manifest only.",
    )
    parser.add_argument(
        "--no-maps",
        action="store_true",
        help="Skip the three grower-level maps (useful offline).",
    )
    parser.add_argument(
        "--latest-year",
        type=int,
        default=None,
        help="Year for the latest-crop map. Default: the newest year present.",
    )
    return parser.parse_args(argv)


def _write_csv(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.6g")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _concat(frames: list[pd.DataFrame], columns: list[str] | None = None) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return pd.DataFrame(columns=columns or [])
    return pd.concat(usable, ignore_index=True, sort=False)


def build_boundaries(farms, out_root: Path, warnings: list[str]) -> tuple[pd.DataFrame, dict]:
    geometry = _concat([gm.field_geometry(farm) for farm in farms.values()])
    tests = gm.compare_geometry(geometry)
    summary = gm.geometry_summary(geometry)

    _write_csv(geometry, out_root / "boundaries" / "field_geometry.csv")
    _write_csv(tests, out_root / "boundaries" / "geometry_tests.csv")
    return geometry, {"tests": tests, "summary": summary}


def build_cropland(farms, out_root: Path, warnings: list[str]) -> tuple[pd.DataFrame, dict]:
    dominant_parts = []
    for farm in farms.values():
        if farm.crop.empty:
            warnings.append(f"{farm.code}: no crop table, cropland category skipped")
            continue
        dominant = cm.add_identity(cm.dominant_crop(farm.crop), farm)
        dominant_parts.append(dominant)
    dominant = _concat(dominant_parts)
    if dominant.empty:
        return dominant, {}

    composed = cm.composition(dominant)
    sequence = cm.sequence_matrix(dominant)
    transitions = cm.transitions(dominant)
    tests = cm.crop_tests(dominant, transitions)
    summary = cm.cropland_summary(dominant)

    _write_csv(dominant, out_root / "cropland" / "field_crop_sequence.csv")
    _write_csv(composed, out_root / "cropland" / "crop_composition.csv")
    _write_csv(transitions, out_root / "cropland" / "crop_transitions.csv")
    _write_csv(tests, out_root / "cropland" / "crop_tests.csv")
    return dominant, {
        "composition": composed,
        "sequence": sequence,
        "transitions": transitions,
        "tests": tests,
        "summary": summary,
    }


def build_weather(farms, out_root: Path, warnings: list[str]) -> tuple[pd.DataFrame, dict]:
    field_series_parts = []
    annual_parts = []
    monthly_parts = []
    series_parts = []
    for farm in farms.values():
        if farm.weather.empty:
            warnings.append(f"{farm.code}: no weather table, weather category skipped")
            continue
        assigned = wm.assign_series(farm.weather, farm)
        field_series_parts.append(wm.field_series_table(assigned, farm))
        series = wm.series_weather(assigned)
        series_parts.append(series)
        annual_parts.append(wm.annual_by_series(series))
        monthly_parts.append(wm.monthly_by_farm_year(series, farm))

    field_series = _concat(field_series_parts)
    annual = _concat(annual_parts)
    monthly = _concat(monthly_parts)
    if field_series.empty:
        return field_series, {}

    series_ids = sorted(annual["series_id"].unique()) if not annual.empty else []
    corr = wm.correlation(_concat(series_parts), series_ids)
    audit_table = wm.audit(field_series, annual, corr)
    summary = wm.weather_summary(audit_table, annual, field_series)

    _write_csv(field_series, out_root / "weather" / "weather_series.csv")
    _write_csv(annual, out_root / "weather" / "weather_annual_by_series.csv")
    _write_csv(monthly, out_root / "weather" / "weather_monthly_by_farm_year.csv")
    _write_csv(corr, out_root / "weather" / "weather_series_correlation.csv")
    _write_csv(audit_table, out_root / "weather" / "weather_audit.csv")
    return field_series, {
        "annual": annual,
        "monthly": monthly,
        "correlation": corr,
        "audit": audit_table,
        "summary": summary,
    }


def _gdd_note(annual: pd.DataFrame, field_series: pd.DataFrame) -> str:
    if annual.empty or field_series.empty:
        return "Annual GDD10 unavailable"
    grower_by_series = (
        field_series.drop_duplicates("series_id")
        .set_index("series_id")["grower"]
        .to_dict()
    )
    frame = annual.copy()
    frame["grower"] = frame["series_id"].map(grower_by_series)
    parts = []
    for grower in frame["grower"].drop_duplicates():
        values = frame.loc[frame["grower"].eq(grower), "gdd10"]
        parts.append(f"{grower.upper()} {values.min():,.0f}-{values.max():,.0f}")
    return "Annual GDD10 (base 10 °C) across series-years: " + " · ".join(parts)


def _cross_grower_summary(parts: dict, farms) -> pd.DataFrame:
    base = pd.DataFrame({"grower": list(farms)})
    geometry = parts.get("geometry_summary")
    cropland = parts.get("cropland_summary")
    weather = parts.get("weather_summary")
    for frame in (geometry, cropland, weather):
        if frame is not None and not frame.empty:
            base = base.merge(frame, on="grower", how="left")
    return base


def _write_readme(out_root: Path, entries: list[dict], farms, generated: str) -> Path:
    lines = [
        "# Field-comparison EDA — generated artifact index",
        "",
        f"Generated {generated} from {len(farms)} growers "
        f"({', '.join(farms)}). Do not edit by hand; re-run the CLI.",
        "",
        "| Artifact | Kind | Story |",
        "| --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            f"| `{entry['path']}` | {entry['kind']} | {entry.get('story', '')} |"
        )
    lines.extend(
        [
            "",
            "## Method contract",
            "",
            "- Weather is aggregated **per distinct series**, never per field: duplicate",
            "  field rows are collapsed before any sum or mean.",
            "- Crop class comes from CDL (US) or MNC (AR), never from the boundary hint.",
            "- A field-year is *split* when the dominant class is below 60 %.",
            "- p-values at n=4 growers are descriptive; effect sizes carry the claim.",
            "",
            "Report assembly is intentionally outside this artifact set.",
            "",
        ]
    )
    path = out_root / "README.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


_STORIES = {
    "boundaries/field_area_by_grower.png": "Field size separates growers before agronomy.",
    "boundaries/compactness_vs_area.png": "Smaller fields are more elongated.",
    "cropland/crop_composition_by_grower_year.png": "Crop mix is grower identity.",
    "cropland/field_crop_sequence.png": "Each field's five-year history in one grid.",
    "weather/annual_precip_by_series.png": "Water supply by distinct weather series.",
    "weather/monthly_temperature_climatology.png": "Season length and heat load.",
    "maps/boundaries_by_grower.png": "Farm layout: ten dispersed parcels per grower, not one block.",
    "maps/latest_crop_map.png": "What is on the ground in the latest mapped year.",
    "maps/weather_series_map.png": "The weather grid is not the field grid.",
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_root = (args.out or ds.default_output_root()).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    farms = ds.load_farms(args.growers)
    warnings: list[str] = []
    for farm in farms.values():
        warnings.extend(f"{farm.grower_slug}: {message}" for message in farm.warnings)

    short_labels = {
        code: farm.display_name.split(" (")[0] for code, farm in farms.items()
    }

    geometry, geom_parts = build_boundaries(farms, out_root, warnings)
    dominant, crop_parts = build_cropland(farms, out_root, warnings)
    field_series, weather_parts = build_weather(farms, out_root, warnings)

    outputs: list[Path] = []
    if not args.no_figures:
        outputs.append(
            fg.plot_area_distribution(
                geometry, geom_parts["tests"], short_labels,
                out_root / "boundaries" / "field_area_by_grower.png",
            )
        )
        outputs.append(
            fg.plot_compactness_vs_area(
                geometry, geom_parts["tests"], short_labels,
                out_root / "boundaries" / "compactness_vs_area.png",
            )
        )
        if not crop_parts:
            warnings.append("cropland figures skipped: no crop data")
        else:
            outputs.append(
                fg.plot_crop_composition(
                    crop_parts["composition"], short_labels,
                    out_root / "cropland" / "crop_composition_by_grower_year.png",
                )
            )
            outputs.append(
                fg.plot_crop_sequence(
                    crop_parts["sequence"], dominant, short_labels,
                    out_root / "cropland" / "field_crop_sequence.png",
                )
            )
        if not weather_parts:
            warnings.append("weather figures skipped: no weather data")
        else:
            outputs.append(
                fg.plot_annual_precip(
                    weather_parts["annual"], field_series, short_labels,
                    out_root / "weather" / "annual_precip_by_series.png",
                )
            )
            outputs.append(
                fg.plot_monthly_temperature(
                    weather_parts["monthly"],
                    _gdd_note(weather_parts["annual"], field_series),
                    short_labels,
                    out_root / "weather" / "monthly_temperature_climatology.png",
                )
            )

    if not args.no_maps:
        import field_maps as fm

        outputs.append(
            fm.boundaries_map(farms, geometry, out_root / "maps" / "boundaries_by_grower.png")
        )
        if crop_parts:
            latest_year = args.latest_year or int(dominant["year"].max())
            outputs.append(
                fm.latest_crop_map(
                    farms, dominant, latest_year,
                    out_root / "maps" / "latest_crop_map.png",
                )
            )
        if weather_parts:
            outputs.append(
                fm.weather_series_map(
                    farms, field_series,
                    out_root / "maps" / "weather_series_map.png",
                )
            )

    summary = _cross_grower_summary(
        {
            "geometry_summary": geom_parts["summary"],
            "cropland_summary": crop_parts.get("summary") if crop_parts else None,
            "weather_summary": weather_parts.get("summary") if weather_parts else None,
        },
        farms,
    )
    _write_csv(summary, out_root / "cross_grower_summary.csv")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries: list[dict] = []
    for path in sorted(out_root.rglob("*")):
        if not path.is_file() or path.name in {"manifest.json"}:
            continue
        if path.name == "README.md" and path.parent == out_root:
            continue
        relative = path.relative_to(out_root).as_posix()
        kind = (
            "figure"
            if path.suffix.lower() == ".png"
            else "table"
            if path.suffix.lower() == ".csv"
            else "other"
        )
        entries.append(
            {
                "path": relative,
                "kind": kind,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "story": _STORIES.get(relative, ""),
            }
        )

    manifest = {
        "generated_at": generated,
        "skill": "eda-field-comparison",
        "skill_version": "0.1.0",
        "data_root": str(ds.pipeline_root()),
        "out_root": str(out_root),
        "growers": [
            {
                "grower": farm.grower_slug,
                "farm": farm.farm_slug,
                "code": farm.code,
                "fields": len(farm.field_ids),
                "crop_rows": int(len(farm.crop)),
                "weather_rows": int(len(farm.weather)),
                "weather_series": int(
                    field_series.loc[field_series.grower.eq(farm.code), "series_id"].nunique()
                )
                if not field_series.empty
                else 0,
            }
            for farm in farms.values()
        ],
        "years": sorted(int(y) for y in dominant["year"].dropna().unique())
        if not dominant.empty
        else [],
        "thresholds": {
            "split_dominance_pct": cm.SPLIT_DOMINANCE_PCT,
            "gdd_base_c": 10.0,
            "min_year_coverage": wm.MIN_YEAR_COVERAGE,
        },
        "method_notes": [
            "weather is aggregated per distinct series, never per field",
            "crop class from CDL (US) / MNC (AR), not from the boundary hint",
            "boundaries are a single snapshot; only cropland and weather carry time",
            "p-values at n=4 growers are descriptive; effect sizes carry the claim",
            "map frame is fitted to the farm union; scale bar suppressed per repo contract",
        ],
        "warnings": sorted(set(warnings)),
        "outputs": entries,
    }
    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _write_readme(out_root, entries, farms, generated)

    figures = sum(1 for entry in entries if entry["kind"] == "figure")
    tables = sum(1 for entry in entries if entry["kind"] == "table")
    print(f"wrote {figures} figures, {tables} tables -> {out_root}")
    for message in manifest["warnings"]:
        print(f"warning: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
