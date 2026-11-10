"""Argentina National Map of Crops (MNC) reporting helpers.

The MNC is INTA's annual 30 m crop-type map for Argentina, published on
Zenodo under CC BY 4.0.  Each campaign ships two seasonal rasters:

* a *summer* raster (main crop season, e.g. soybean/maize/sunflower), and
* a *winter* raster (winter cereals, peas, chickpeas, fallow).

The pipeline uses the national map as the Argentine counterpart of the USDA
CDL.  Because the two seasons overlap in time, the summer map is treated as
the primary source: the winter map is only substituted for a field when the
summer map is mostly masked or non-agricultural for that field.  Both
seasonal compositions are always written to ``mnc_seasonal_detail.csv`` so the
substitution is auditable.

Campaigns are keyed by the *summer* calendar year.  For example the 2024/25
campaign maps to ``year=2025`` and uses ``MNC_ver25.tif`` (summer) and
``MNC_inv24.tif`` (winter).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from lib.paths import shared_mnc_campaign_dir  # pyright: ignore[reportMissingImports]
from rasterstats import zonal_stats

SOURCE_NAME = "mnc"
LICENSE = "CC BY 4.0"
ATTRIBUTION = (
    "Mapa Nacional de Cultivos (MNC), INTA - Instituto Nacional de Tecnología "
    "Agropecuaria. https://doi.org/10.5281/zenodo.8286318"
)
ZENODO_API = "https://zenodo.org/api/records"

# year -> campaign metadata. ``year`` is the summer calendar year.
MNC_CAMPAIGNS: dict[int, dict[str, Any]] = {
    2021: {
        "record_id": 8286318,
        "doi": "10.5281/zenodo.8286318",
        "campaign": "2020/21",
        "summer": {
            "file": "verano-2021.tif",
            "md5": "9b650b09b405e89e752fa513b610da25",
        },
        "winter": {
            "file": "invierno-2020.tif",
            "md5": "50be96fdd567c4338b9b0ebda13beaa6",
        },
    },
    2022: {
        "record_id": 8284081,
        "doi": "10.5281/zenodo.8284081",
        "campaign": "2021/22",
        "summer": {
            "file": "MNC_verano2022.tif",
            "md5": "f88ffac06865b36038916ec22c1ffe28",
        },
        "winter": {
            "file": "MNC_invierno2021.tif",
            "md5": "571069f9549ca74cc779f55257694d84",
        },
    },
    2023: {
        "record_id": 10103323,
        "doi": "10.5281/zenodo.10103323",
        "campaign": "2022/23",
        "summer": {
            "file": "MNC_verano-2023.tif",
            "md5": "d42887ad60bd95878ad806aa78f69341",
        },
        "winter": {
            "file": "MNC_invierno2022.tif",
            "md5": "2f0f4b4a99d06c7d785db8dd7246f4c4",
        },
    },
    2024: {
        "record_id": 13984185,
        "doi": "10.5281/zenodo.13984185",
        "campaign": "2023/24",
        "summer": {
            "file": "MNC_verano-2024.tif",
            "md5": "8290b6023c41832f4b31a44371b36ff4",
        },
        "winter": {
            "file": "MNC_invierno2023.tif",
            "md5": "89778c7386470b29d1f3d780c025f0a3",
        },
    },
    2025: {
        "record_id": 17652712,
        "doi": "10.5281/zenodo.17652712",
        "campaign": "2024/25",
        "summer": {
            "file": "MNC_ver25.tif",
            "md5": "c6a82309243f0d53793e4d41f02a72ce",
        },
        "winter": {
            "file": "MNC_inv24.tif",
            "md5": "55cfac03da3849090e7d3adf6530bd63",
        },
    },
}

MNC_YEARS: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)

# Legend transcribed from the campaign QML style files.  Codes are stable
# across campaigns except where noted in the MNC report PDFs.
MNC_SUMMER_LEGEND: dict[int, str] = {
    10: "Maíz",
    11: "Soja",
    12: "Girasol",
    13: "Poroto",
    14: "Caña",
    15: "Algodón",
    16: "Maní",
    17: "Arroz",
    18: "Sorgo",
    19: "Girasol-CV",
    21: "Barbecho",
    22: "No agrícola",
    26: "Papa",
    27: "Verdeo de Maíz",
    28: "Verdeo de Sorgo",
    30: "Tabaco",
    31: "Máscara",
}

MNC_WINTER_LEGEND: dict[int, str] = {
    6: "Garbanzo",
    16: "Cereales de invierno",
    17: "Otros cultivos",
    18: "Barbecho",
    19: "Caña",
    20: "No agrícola",
    24: "Arveja",
    25: "Máscara",
    26: "Papa",
}

MNC_LEGENDS: dict[str, dict[int, str]] = {
    "summer": MNC_SUMMER_LEGEND,
    "winter": MNC_WINTER_LEGEND,
}

# MNC crop names translated to the USDA CDL names used by every downstream
# report.  ``No Data`` is filtered by cdl_reporting.filter_cdl_categories.
MNC_TO_CDL_NAME: dict[str, str] = {
    "Maíz": "Corn",
    "Soja": "Soybeans",
    "Girasol": "Sunflower",
    "Girasol-CV": "Sunflower",
    "Poroto": "Dry Beans",
    "Caña": "Sugarcane",
    "Algodón": "Cotton",
    "Maní": "Peanuts",
    "Arroz": "Rice",
    "Sorgo": "Sorghum",
    "Papa": "Potatoes",
    "Verdeo de Maíz": "Corn",
    "Verdeo de Sorgo": "Sorghum",
    "Tabaco": "Tobacco",
    "Garbanzo": "Chickpeas",
    "Cereales de invierno": "Winter Cereals",
    "Otros cultivos": "Other",
    "Arveja": "Peas",
    "Barbecho": "Fallow/Idle",
    "No agrícola": "Other",
    "Máscara": "No Data",
}

# Codes that count as an actual crop (as opposed to fallow / non-ag / mask).
MNC_AG_CODES: dict[str, set[int]] = {
    "summer": {10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 26, 27, 28, 30},
    "winter": {6, 16, 17, 19, 24, 26},
}

# Summer is considered usable when at least this share of the field pixels is
# a crop.  Below the threshold the summer raster is treated as masked /
# non-agricultural and the winter raster is evaluated instead.
SUMMER_MIN_AG_SHARE = 0.20


def campaign_metadata(year: int) -> dict[str, Any]:
    if year not in MNC_CAMPAIGNS:
        raise KeyError(f"No MNC campaign registered for {year}; known: {sorted(MNC_CAMPAIGNS)}")
    return MNC_CAMPAIGNS[year]


def mnc_raster_path(year: int, season: str) -> Path:
    """Return the shared cache path for one seasonal MNC raster."""

    season = season.strip().lower()
    if season not in {"summer", "winter"}:
        raise ValueError("season must be 'summer' or 'winter'")
    meta = campaign_metadata(year)
    return shared_mnc_campaign_dir(year) / meta[season]["file"]


def mnc_download_url(year: int, season: str) -> str:
    meta = campaign_metadata(year)
    return f"{ZENODO_API}/{meta['record_id']}/files/{meta[season]['file']}/content"


def _md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5()  # noqa: S324 - upstream publishes MD5 checksums
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_mnc_raster(year: int, season: str, *, force: bool = False) -> Path:
    """Download one seasonal raster and verify its published MD5 checksum."""

    target = mnc_raster_path(year, season)
    expected = campaign_metadata(year)[season]["md5"]
    if target.exists() and not force:
        if target.stat().st_size > 0 and _md5(target) == expected:
            return target
        print(f"  warn  MNC checksum mismatch for {target.name}; re-downloading")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    url = mnc_download_url(year, season)
    print(f"  MNC {year} {season}: {url}")
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                handle.write(chunk)
    actual = _md5(partial)
    if actual != expected:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"MNC {year} {season} checksum mismatch: expected {expected}, got {actual}"
        )
    partial.replace(target)
    return target


def prefetch_mnc_years(years: list[int] | None = None, *, force: bool = False) -> list[Path]:
    """Download the summer and winter rasters for each campaign year."""

    paths: list[Path] = []
    for year in sorted(set(years or MNC_YEARS)):
        for season in ("summer", "winter"):
            paths.append(download_mnc_raster(year, season, force=force))
    return paths


def _normalized_counts(stats: dict[Any, int] | None) -> dict[int, int]:
    counts: dict[int, int] = {}
    for code, pixels in (stats or {}).items():
        try:
            code_int = int(code)
        except (TypeError, ValueError):
            continue
        counts[code_int] = counts.get(code_int, 0) + int(pixels)
    # 255 is the raster nodata value, not a mapped class.
    counts.pop(255, None)
    return counts


def _ag_share(counts: dict[int, int], season: str) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    agriculture = sum(pixels for code, pixels in counts.items() if code in MNC_AG_CODES[season])
    return agriculture / total


def _season_rows(
    *,
    field_id: str,
    year: int,
    season: str,
    counts: dict[int, int],
) -> list[dict[str, Any]]:
    legend = MNC_LEGENDS[season]
    total = sum(counts.values())
    rows: list[dict[str, Any]] = []
    if total <= 0:
        return [
            {
                "field_id": field_id,
                "year": year,
                "season": season,
                "crop_code": 0,
                "crop_name": "No Data",
                "pixel_count": 0,
                "pct": 0.0,
            }
        ]
    for code, pixels in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        raw_name = legend.get(code, "No Data" if code == 0 else f"Code_{code}")
        rows.append(
            {
                "field_id": field_id,
                "year": year,
                "season": season,
                "crop_code": code,
                "crop_name": MNC_TO_CDL_NAME.get(raw_name, raw_name),
                "pixel_count": int(pixels),
                "pct": round(float(pixels) / total * 100.0, 2),
            }
        )
    return rows


def _select_season(
    summer_counts: dict[int, int], winter_counts: dict[int, int]
) -> tuple[str, str]:
    """Return ``(season, reason)`` for the primary composition of a field."""

    summer_share = _ag_share(summer_counts, "summer")
    winter_share = _ag_share(winter_counts, "winter")
    if summer_share >= SUMMER_MIN_AG_SHARE:
        return "summer", f"summer crop share {summer_share:.0%} >= {SUMMER_MIN_AG_SHARE:.0%}"
    if winter_share > summer_share:
        return (
            "winter",
            f"summer masked/non-agricultural ({summer_share:.0%}); "
            f"winter crop share {winter_share:.0%}",
        )
    return "summer", f"summer kept; winter not more agricultural ({winter_share:.0%})"


def extract_mnc_crop_composition(
    fields: gpd.GeoDataFrame,
    year: int,
    *,
    seasonal_detail: list[dict[str, Any]] | None = None,
    force_download: bool = False,
) -> pd.DataFrame:
    """Return CDL-compatible crop composition rows from the MNC campaign.

    ``seasonal_detail`` is appended in place with one row per season, crop and
    field so callers can persist the audit trail.
    """

    if not fields.empty and "country" in fields.columns:
        ar_mask = fields["country"].astype(str).str.strip().str.upper().eq("AR")
        fields = fields.loc[ar_mask].copy()
    if fields.empty:
        return pd.DataFrame()

    summer_path = download_mnc_raster(year, "summer", force=force_download)
    winter_path = download_mnc_raster(year, "winter", force=force_download)
    fields_wgs84 = fields.to_crs("EPSG:4326")

    selected_rows: list[dict[str, Any]] = []
    for _, field in fields_wgs84.iterrows():
        field_id = str(field.get("field_id", "")).strip()
        if not field_id:
            continue
        summer_stats = zonal_stats(field.geometry, summer_path, categorical=True)
        winter_stats = zonal_stats(field.geometry, winter_path, categorical=True)
        summer_counts = _normalized_counts(summer_stats[0] if summer_stats else {})
        winter_counts = _normalized_counts(winter_stats[0] if winter_stats else {})
        season, reason = _select_season(summer_counts, winter_counts)

        summer_rows = _season_rows(
            field_id=field_id, year=year, season="summer", counts=summer_counts
        )
        winter_rows = _season_rows(
            field_id=field_id, year=year, season="winter", counts=winter_counts
        )
        if seasonal_detail is not None:
            for row in summer_rows + winter_rows:
                seasonal_detail.append(
                    {
                        **row,
                        "selected": row["season"] == season,
                        "selection_reason": reason,
                        "crop_source": SOURCE_NAME,
                        "campaign": campaign_metadata(year)["campaign"],
                    }
                )
        chosen = summer_rows if season == "summer" else winter_rows
        selected_rows.extend(
            {**row, "crop_source": SOURCE_NAME, "season": season} for row in chosen
        )
    return pd.DataFrame(selected_rows)


def campaign_provenance(years: list[int] | None = None) -> dict[str, Any]:
    """Machine-readable provenance for the MNC rasters used by a farm."""

    selected = sorted(set(years or MNC_YEARS))
    return {
        "source": SOURCE_NAME,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "zenodo_api": ZENODO_API,
        "season_rule": (
            "summer crop primary; winter used only when the summer map is masked or "
            f"non-agricultural (summer crop share < {SUMMER_MIN_AG_SHARE:.0%})"
        ),
        "campaigns": {
            str(year): {
                "campaign": MNC_CAMPAIGNS[year]["campaign"],
                "doi": MNC_CAMPAIGNS[year]["doi"],
                "summer": MNC_CAMPAIGNS[year]["summer"],
                "winter": MNC_CAMPAIGNS[year]["winter"],
            }
            for year in selected
        },
    }
