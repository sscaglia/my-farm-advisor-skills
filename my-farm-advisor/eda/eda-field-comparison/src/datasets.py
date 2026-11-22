"""Runtime dataset discovery and loading for the field-comparison EDA.

The subskill reads only what the data pipeline already materialises:

* ``<farm>/boundary/field_boundaries.geojson`` — field polygons (one snapshot)
* ``<farm>/derived/tables/<code>_<year>_cdl.csv`` — CDL (US) or MNC (AR)
* ``<farm>/derived/tables/<code>_weather_<first>_<last>.csv`` — daily weather

Nothing is downloaded and nothing is written back into the grower tree.

Two invariants live here because every downstream module depends on them:

1. **Weather rows repeat per field.**  A farm with ten fields and no distinct
   weather cell still writes ten copies of the same daily series.  Summing
   without de-duplicating inflates precipitation and GDD ten-fold.
2. **The crop table is not the boundary table.**  Argentine OSM boundaries
   carry ``crop_name = "Unknown"``; crop class always comes from the CDL/MNC
   table, never from the boundary attribute.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

#: Weather columns used by the analysis.  NASA POWER names, unchanged.
WEATHER_VALUE_COLUMNS: tuple[str, ...] = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "ALLSKY_SFC_SW_DWN",
    "RH2M",
    "WS10M",
)

#: Mapping from the grower code to a readable label when the boundary file
#: cannot supply a state name.
_FALLBACK_LABELS = {"il": "Illinois", "ia": "Iowa", "ne": "Nebraska", "ar": "Argentina"}


class DatasetError(RuntimeError):
    """Raised when the runtime tree is missing or inconsistent."""


def pipeline_root() -> Path:
    """``$DATA_PIPELINE_DATA_ROOT/data-pipeline``, resolved and absolute."""
    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT", "~/my-farm-advisor-runtime")
    return Path(raw).expanduser().resolve() / "data-pipeline"


def default_output_root() -> Path:
    """Default artifact root: ``<runtime>/data-pipeline/eda/field-comparison``."""
    return pipeline_root() / "eda" / "field-comparison"


def ensure_runtime_libs() -> Path:
    """Put the runtime ``src/scripts`` directory on ``sys.path``.

    The subskill reuses ``lib.field_frame``, ``lib.basemap`` and
    ``lib.palettes``; those are pipeline libraries, deliberately not copied
    into the skill tree.
    """
    scripts = pipeline_root() / "src" / "scripts"
    if not scripts.exists():
        raise DatasetError(
            f"runtime scripts not found at {scripts}; set DATA_PIPELINE_DATA_ROOT"
        )
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return scripts


def grower_code(grower_slug: str) -> str:
    """``il-grower`` -> ``il``; ``ne`` -> ``ne``."""
    return str(grower_slug).split("-")[0].lower()


def natural_key(value: object) -> list[object]:
    """Sort ``il-r2`` before ``il-r10`` instead of lexicographically."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(value))
    ]


@dataclass
class FarmData:
    """Everything the EDA needs for one grower/farm pair."""

    grower_slug: str
    farm_slug: str
    code: str
    farm_dir: Path
    boundaries: gpd.GeoDataFrame
    crop: pd.DataFrame
    weather: pd.DataFrame
    warnings: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        state = ""
        country = ""
        if "state" in self.boundaries.columns:
            values = self.boundaries["state"].dropna()
            state = str(values.iloc[0]).strip() if len(values) else ""
        if "country" in self.boundaries.columns:
            values = self.boundaries["country"].dropna()
            country = str(values.iloc[0]).strip() if len(values) else ""
        if state and country:
            return f"{state} ({country})"
        if state:
            return state
        return _FALLBACK_LABELS.get(self.code, self.code.upper())

    @property
    def field_ids(self) -> list[str]:
        return sorted(
            (str(v) for v in self.boundaries["field_id"].dropna().unique()),
            key=natural_key,
        )


def _read_crop_tables(farm_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    tables = sorted((farm_dir / "derived" / "tables").glob("*_cdl.csv"))
    if not tables:
        warnings.append(f"no CDL/MNC table under {farm_dir / 'derived' / 'tables'}")
        return pd.DataFrame(), warnings

    frames = []
    for path in tables:
        frame = pd.read_csv(path)
        if "year" not in frame.columns:
            stem = path.stem
            match = re.search(r"_(\d{4})_cdl$", stem)
            if match:
                frame["year"] = int(match.group(1))
        frame["source_table"] = path.name
        frames.append(frame)
    crop = pd.concat(frames, ignore_index=True, sort=False)

    for column in ("field_id", "year", "crop_name"):
        if column not in crop.columns:
            raise DatasetError(f"{farm_dir}: crop table missing column {column!r}")
    crop["field_id"] = crop["field_id"].astype(str)
    crop["year"] = pd.to_numeric(crop["year"], errors="coerce").astype("Int64")
    crop["crop_name"] = crop["crop_name"].fillna("No Data").astype(str).str.strip()
    # ``pixel_count`` is optional in the table contract; ``pct`` is the share we
    # actually use.  ``DataFrame.get`` returns None for an absent column, and
    # ``pd.to_numeric(None)`` is a scalar — hence the explicit defaults.
    crop["pct"] = pd.to_numeric(
        crop["pct"] if "pct" in crop.columns else pd.Series(0.0, index=crop.index),
        errors="coerce",
    ).fillna(0.0)
    crop["pixel_count"] = pd.to_numeric(
        crop["pixel_count"]
        if "pixel_count" in crop.columns
        else pd.Series(0, index=crop.index),
        errors="coerce",
    ).fillna(0)
    for column in ("agricultural_share", "cropland_status", "season", "crop_source"):
        if column in crop.columns:
            crop[column] = crop[column].astype(object)
    # Drop placeholder rows that carry no class, matching cdl_reporting's
    # filter_cdl_categories(): "No Data" and "Code_<n>" are not crop classes.
    crop = crop.loc[
        ~crop["crop_name"].str.startswith("Code_") & crop["crop_name"].ne("No Data")
    ].copy()
    if crop.empty:
        warnings.append(f"{farm_dir}: crop tables contain no usable class rows")
    return crop, warnings


def _read_weather(farm_dir: Path, code: str) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    tables = sorted((farm_dir / "derived" / "tables").glob("*_weather_*.csv"))
    if not tables:
        warnings.append(f"no weather table under {farm_dir / 'derived' / 'tables'}")
        return pd.DataFrame(), warnings
    preferred = [p for p in tables if p.name.startswith(f"{code}_weather_")]
    path = preferred[0] if preferred else tables[0]
    if len(tables) > 1:
        warnings.append(
            f"multiple weather tables for {code}; using {path.name} "
            f"(ignored: {', '.join(p.name for p in tables if p != path)})"
        )
    weather = pd.read_csv(path, parse_dates=["date"])
    if "field_id" not in weather.columns or "date" not in weather.columns:
        raise DatasetError(f"{path}: weather table needs field_id and date columns")

    missing = [c for c in WEATHER_VALUE_COLUMNS if c not in weather.columns]
    if missing:
        raise DatasetError(f"{path}: weather table missing {', '.join(missing)}")
    weather["field_id"] = weather["field_id"].astype(str)
    for column in WEATHER_VALUE_COLUMNS:
        weather[column] = pd.to_numeric(weather[column], errors="coerce")

    expected = weather["date"].nunique()
    per_field = weather.groupby("field_id")["date"].nunique()
    short = per_field[per_field < expected]
    if len(short):
        warnings.append(
            f"{path.name}: {len(short)} field(s) have fewer than {expected} days "
            f"({', '.join(short.index[:5])})"
        )
    duplicates = weather.duplicated(subset=["field_id", "date"]).sum()
    if duplicates:
        warnings.append(f"{path.name}: dropped {duplicates} duplicate field-day rows")
        weather = weather.drop_duplicates(subset=["field_id", "date"], keep="first")
    return weather.sort_values(["field_id", "date"]).reset_index(drop=True), warnings


def load_farm(grower_slug: str, farm_slug: str) -> FarmData:
    farm_dir = pipeline_root() / "growers" / grower_slug / "farms" / farm_slug
    boundary_path = farm_dir / "boundary" / "field_boundaries.geojson"
    if not boundary_path.exists():
        raise DatasetError(f"boundary file not found: {boundary_path}")

    boundaries = gpd.read_file(boundary_path)
    if boundaries.crs is None:
        boundaries = boundaries.set_crs(4326)
    if "field_id" not in boundaries.columns:
        raise DatasetError(f"{boundary_path}: missing field_id column")
    boundaries["field_id"] = boundaries["field_id"].astype(str)
    if boundaries["field_id"].duplicated().any():
        dupes = boundaries.loc[boundaries["field_id"].duplicated(), "field_id"].tolist()
        raise DatasetError(f"{boundary_path}: duplicate field_id(s): {dupes}")
    if boundaries.crs.to_epsg() != 4326:
        boundaries = boundaries.to_crs(4326)

    code = grower_code(grower_slug)
    crop, crop_warnings = _read_crop_tables(farm_dir)
    weather, weather_warnings = _read_weather(farm_dir, code)

    warnings = [*crop_warnings, *weather_warnings]
    if not crop.empty:
        unknown = set(crop["field_id"]) - set(boundaries["field_id"])
        if unknown:
            warnings.append(
                f"crop table field_id(s) absent from boundaries: "
                f"{', '.join(sorted(unknown, key=natural_key))}"
            )
    return FarmData(
        grower_slug=grower_slug,
        farm_slug=farm_slug,
        code=code,
        farm_dir=farm_dir,
        boundaries=boundaries,
        crop=crop,
        weather=weather,
        warnings=warnings,
    )


def discover_farms(growers: list[str] | None = None) -> list[tuple[str, str]]:
    """Return ``(grower_slug, farm_slug)`` pairs under the runtime growers tree.

    ``growers`` accepts either slugs (``il-grower``) or codes (``il``).
    """
    root = pipeline_root() / "growers"
    if not root.exists():
        raise DatasetError(
            f"growers tree not found at {root}; set DATA_PIPELINE_DATA_ROOT"
        )
    wanted = {str(g).strip().lower() for g in growers} if growers else None
    pairs: list[tuple[str, str]] = []
    for grower_dir in sorted(root.iterdir(), key=lambda p: p.name):
        if not grower_dir.is_dir():
            continue
        code = grower_code(grower_dir.name)
        if wanted and grower_dir.name.lower() not in wanted and code not in wanted:
            continue
        farms_dir = grower_dir / "farms"
        if not farms_dir.exists():
            continue
        for farm_dir in sorted(farms_dir.iterdir(), key=lambda p: p.name):
            if (
                farm_dir.is_dir()
                and (farm_dir / "boundary" / "field_boundaries.geojson").exists()
            ):
                pairs.append((grower_dir.name, farm_dir.name))
    if not pairs:
        requested = ", ".join(sorted(wanted)) if wanted else "any grower"
        raise DatasetError(f"no farms with boundaries found for {requested} under {root}")
    return pairs


def load_farms(growers: list[str] | None = None) -> dict[str, FarmData]:
    """Load every requested farm, keyed by grower code (``il``, ``ia``, ...)."""
    farms: dict[str, FarmData] = {}
    for grower_slug, farm_slug in discover_farms(growers):
        farm = load_farm(grower_slug, farm_slug)
        if farm.code in farms:
            raise DatasetError(
                f"grower code {farm.code!r} resolves to more than one farm: "
                f"{farms[farm.code].farm_slug}, {farm.farm_slug}"
            )
        farms[farm.code] = farm
    return farms
