"""Cropland (CDL / MNC) composition, sequences and transitions.

This is the only category with a real within-field time axis: five annual
crop maps, 2021-2025.  Everything is derived from the per-field zonal tables
the ingest writes — never from the boundary ``crop`` attribute, which is a
human/OSM hint (Argentina's OSM fields carry ``"Unknown"``).

Two source-specific rules:

* **US (CDL)** class shares come from ``pct``; a field-year is a *split* when
  the dominant class is below :data:`SPLIT_DOMINANCE_PCT`.
* **Argentina (MNC)** adds ``agricultural_share`` and ``cropland_status``.
  ``Non-agricultural`` is a land-cover class (pasture/natural), **not** an
  "other crop"; a parcel whose five years are all non-agricultural is
  pasture, and reporting a rotation for it is meaningless
  (``cdl_reporting.build_crop_rotation_outlook`` already returns
  ``not_applicable`` for those parcels).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

#: A field-year is "split" when its dominant class holds less than this share.
#: 60 % is the threshold the CDL reporting layer already uses to flag a
#: split field, so the EDA does not invent a second convention.
SPLIT_DOMINANCE_PCT = 60.0

#: Fixed display order so the same class keeps the same colour and position
#: in every panel.  Classes absent from a dataset are simply skipped.
CROP_ORDER: tuple[str, ...] = (
    "Corn",
    "Soybeans",
    "Winter Wheat",
    "Alfalfa",
    "Other crops",
    "Other",
    "Fallow/Idle",
    "Grass/Pasture",
    "Grassland",
    "Forest",
    "Non-agricultural",
    "Open Water",
)

#: Colour-blind-safe, semantically stable class colours.  Corn/soy carry the
#: canonical yellow/green pairing; non-crop land is muted so managed crops
#: dominate the eye in a stacked bar.
CROP_COLORS: dict[str, str] = {
    "Corn": "#E69F00",
    "Soybeans": "#009E73",
    "Winter Wheat": "#F0E442",
    "Alfalfa": "#56B4E9",
    "Other crops": "#D55E0E",
    "Other": "#8C8C8C",
    "Fallow/Idle": "#CC79A7",
    "Grass/Pasture": "#B2DF8A",
    "Grassland": "#66A61E",
    "Forest": "#1B5E20",
    "Non-agricultural": "#C8C8C8",
    "Open Water": "#6BAED6",
}

_FALLBACK_COLORS = (
    "#0072B2",
    "#F0E442",
    "#CC79A7",
    "#56B4E9",
    "#D55E0E",
    "#333333",
)


def _load_non_crop_labels() -> frozenset[str]:
    """Reuse the CDL reporting vocabulary instead of redefining it.

    Imported lazily from the sibling ``soil/cdl-cropland`` skill so the two
    layers cannot drift apart.  The literal fallback keeps the subskill
    importable when the repository layout is not present (installed copy).
    """
    skill_root = Path(__file__).resolve().parents[3]
    candidate = skill_root / "soil" / "cdl-cropland" / "src"
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    try:
        from cdl_reporting import NON_CROP_LABELS  # type: ignore

        return frozenset(NON_CROP_LABELS)
    except Exception:  # noqa: BLE001 — cosmetic semantics, never fatal
        return frozenset(
            {
                "Non-agricultural",
                "Fallow/Idle",
                "Forest",
                "Grassland",
                "Grass/Pasture",
                "Open Water",
            }
        )


NON_CROP_LABELS: frozenset[str] = _load_non_crop_labels()


def crop_color(name: str) -> str:
    if name in CROP_COLORS:
        return CROP_COLORS[name]
    known = [n for n in CROP_ORDER if n in CROP_COLORS]
    index = known.index(name) if name in known else len(known)
    return _FALLBACK_COLORS[index % len(_FALLBACK_COLORS)]


def ordered_crops(names) -> list[str]:
    """Fixed order first, then any unexpected class alphabetically."""
    present = {str(n) for n in names}
    head = [n for n in CROP_ORDER if n in present]
    tail = sorted(present - set(head))
    return head + tail


def _prefer_primary_season(crop: pd.DataFrame) -> pd.DataFrame:
    """Keep one season per field-year (the one that covers the most pixels).

    Argentina's MNC ships a summer and a winter raster that can both be
    extracted for the same campaign.  Summing both would double-count area;
    the ingest resolves the substitution, but the EDA guard keeps a mixed
    runtime honest.
    """
    if "season" not in crop.columns or crop["season"].isna().all():
        return crop
    frame = crop.copy()
    frame["season"] = frame["season"].fillna("").astype(str)
    totals = (
        frame.groupby(["field_id", "year", "season"], as_index=False)["pct"]
        .sum()
        .sort_values(["field_id", "year", "pct", "season"])
    )
    best = totals.drop_duplicates(["field_id", "year"], keep="last")
    keys = set(zip(best["field_id"], best["year"], best["season"]))
    keep = [
        (fid, year, season) in keys
        for fid, year, season in zip(frame["field_id"], frame["year"], frame["season"])
    ]
    return frame.loc[keep].copy()


def dominant_crop(crop: pd.DataFrame) -> pd.DataFrame:
    """One row per (field, year): dominant class, purity, land status."""
    if crop.empty:
        return pd.DataFrame(
            columns=[
                "grower",
                "grower_slug",
                "farm_slug",
                "field_id",
                "year",
                "crop_name",
                "purity_pct",
                "is_split",
                "n_classes",
                "pct_sum",
                "agricultural_share",
                "cropland_status",
                "is_managed_crop",
            ]
        )
    frame = _prefer_primary_season(crop)
    # MNC repeats the field-year land status on every class row; keep it once.
    status_columns = [
        column
        for column in ("agricultural_share", "cropland_status")
        if column in frame.columns
    ]
    status = (
        frame.groupby(["field_id", "year"], as_index=False)[status_columns].max()
        if status_columns
        else None
    )
    frame = (
        frame.groupby(["field_id", "year", "crop_name"], as_index=False)
        .agg(pct=("pct", "sum"), pixel_count=("pixel_count", "sum"))
    )
    frame = frame.sort_values(["field_id", "year", "pct", "crop_name"])
    dominant = frame.drop_duplicates(["field_id", "year"], keep="last").copy()
    counts = (
        frame.groupby(["field_id", "year"], as_index=False)
        .agg(n_classes=("crop_name", "nunique"), pct_sum=("pct", "sum"))
    )
    dominant = dominant.merge(counts, on=["field_id", "year"], how="left")
    if status is not None:
        dominant = dominant.merge(status, on=["field_id", "year"], how="left")
    dominant = dominant.rename(columns={"pct": "purity_pct"})
    dominant["is_split"] = dominant["purity_pct"] < SPLIT_DOMINANCE_PCT
    dominant["is_managed_crop"] = ~dominant["crop_name"].isin(NON_CROP_LABELS)

    for column in ("agricultural_share", "cropland_status"):
        if column not in dominant.columns:
            dominant[column] = np.nan

    ordered = ["field_id", "year", "crop_name", "purity_pct", "is_split",
               "n_classes", "pct_sum", "agricultural_share", "cropland_status",
               "is_managed_crop"]
    return dominant[ordered].sort_values(["field_id", "year"]).reset_index(drop=True)


def add_identity(dominant: pd.DataFrame, farm) -> pd.DataFrame:
    frame = dominant.copy()
    frame.insert(0, "grower", farm.code)
    frame.insert(1, "grower_slug", farm.grower_slug)
    frame.insert(2, "farm_slug", farm.farm_slug)
    return frame


def composition(dominant: pd.DataFrame) -> pd.DataFrame:
    """Share of field-years per grower x year x class (stacked-bar input)."""
    if dominant.empty:
        return pd.DataFrame(columns=["grower", "year", "crop_name", "field_years", "share"])
    frame = (
        dominant.groupby(["grower", "year", "crop_name"])
        .size()
        .reset_index(name="field_years")
    )
    frame["share"] = frame["field_years"] / frame.groupby(["grower", "year"])[
        "field_years"
    ].transform("sum")
    return frame.sort_values(["grower", "year", "crop_name"]).reset_index(drop=True)


def sequence_matrix(dominant: pd.DataFrame) -> pd.DataFrame:
    """Field x year grid of dominant class names (the heatmap input)."""
    if dominant.empty:
        return pd.DataFrame()
    return (
        dominant.pivot_table(
            index=["grower", "field_id"],
            columns="year",
            values="crop_name",
            aggfunc="first",
        )
        .sort_index()
        .reset_index()
    )


def transitions(dominant: pd.DataFrame) -> pd.DataFrame:
    """Count consecutive-year class changes per grower."""
    if dominant.empty:
        return pd.DataFrame(
            columns=["grower", "from_crop", "to_crop", "field_years", "share"]
        )
    frame = dominant.sort_values(["field_id", "year"]).copy()
    grouped = frame.groupby("field_id", sort=False)
    frame["to_crop"] = grouped["crop_name"].shift(-1)
    frame["to_year"] = grouped["year"].shift(-1)
    pairs = frame.loc[
        frame["to_crop"].notna() & (frame["to_year"] == frame["year"] + 1)
    ].copy()
    if pairs.empty:
        return pd.DataFrame(
            columns=["grower", "from_crop", "to_crop", "field_years", "share"]
        )
    pairs["changed"] = pairs["crop_name"].ne(pairs["to_crop"])
    table = (
        pairs.groupby(["grower", "crop_name", "to_crop"])
        .size()
        .reset_index(name="field_years")
        .rename(columns={"crop_name": "from_crop"})
    )
    table["share"] = table["field_years"] / table.groupby("grower")[
        "field_years"
    ].transform("sum")
    return table.sort_values(
        ["grower", "field_years"], ascending=[True, False]
    ).reset_index(drop=True)


def _cramers_v(table: pd.DataFrame) -> tuple[float, float, float, float]:
    """chi2, p, Cramer's V, minimum expected count for a contingency table."""
    observed = table.to_numpy(dtype=float)
    chi2, p_value, _, expected = stats.chi2_contingency(observed)
    n = observed.sum()
    k = min(observed.shape) - 1
    v = math.sqrt(chi2 / (n * k)) if n > 0 and k > 0 else float("nan")
    return float(chi2), float(p_value), float(v), float(np.min(expected))


def _fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def crop_tests(dominant: pd.DataFrame, transition_table: pd.DataFrame) -> pd.DataFrame:
    """Chi-square comparisons and rotation-style descriptors per grower."""
    rows: list[dict[str, object]] = []
    if dominant.empty:
        return pd.DataFrame(rows)

    # 1. Does the crop mix differ by grower?  grower x dominant class counts.
    mix = pd.crosstab(dominant["grower"], dominant["crop_name"])
    if mix.shape[0] >= 2 and mix.shape[1] >= 2:
        chi2, p_value, v, min_expected = _cramers_v(mix)
        rows.append(
            {
                "category": "cropland",
                "test": "chi-square",
                "comparison": "grower x dominant crop (all field-years)",
                "statistic": chi2,
                "p_value": p_value,
                "effect_size": v,
                "effect_size_name": "cramers_v",
                "min_expected_count": min_expected,
                "verdict": (
                    f"crop mix is grower-specific (chi2={chi2:.1f}, "
                    f"p={_fmt_p(p_value)}, V={v:.2f})"
                ),
                "note": (
                    "expected counts <5 present — interpret descriptively"
                    if min_expected < 5
                    else "expected counts adequate"
                ),
            }
        )

    # 2. Does rotation rigidity differ by grower?  grower x changed/stayed.
    if not transition_table.empty:
        frame = dominant.sort_values(["field_id", "year"]).copy()
        grouped = frame.groupby("field_id", sort=False)
        frame["to_crop"] = grouped["crop_name"].shift(-1)
        frame["to_year"] = grouped["year"].shift(-1)
        pairs = frame.loc[
            frame["to_crop"].notna() & (frame["to_year"] == frame["year"] + 1)
        ].copy()
        pairs["changed"] = pairs["crop_name"].ne(pairs["to_crop"])
        table = pd.crosstab(pairs["grower"], pairs["changed"])
        if table.shape[0] >= 2 and table.shape[1] >= 2:
            chi2, p_value, v, min_expected = _cramers_v(table)
            rows.append(
                {
                    "category": "cropland",
                    "test": "chi-square",
                    "comparison": "grower x crop-change (consecutive years)",
                    "statistic": chi2,
                    "p_value": p_value,
                    "effect_size": v,
                    "effect_size_name": "cramers_v",
                    "min_expected_count": min_expected,
                    "verdict": (
                        f"rotation rigidity differs by grower (chi2={chi2:.1f}, "
                        f"p={_fmt_p(p_value)}, V={v:.2f})"
                    ),
                    "note": (
                        "expected counts <5 present — interpret descriptively"
                        if min_expected < 5
                        else "expected counts adequate"
                    ),
                }
            )

    # 3. Per-grower descriptors: diversity, change rate, distinct crops/field.
    for grower, subset in dominant.groupby("grower"):
        counts = subset["crop_name"].value_counts()
        shares = counts / counts.sum()
        shannon = float(-(shares * np.log(shares)).sum())
        effective = float(math.exp(shannon))

        frame = subset.sort_values(["field_id", "year"])
        grouped = frame.groupby("field_id", sort=False)["crop_name"]
        changes = 0
        pairs_total = 0
        for _, series in grouped:
            values = series.tolist()
            pairs_total += max(len(values) - 1, 0)
            changes += sum(1 for a, b in zip(values, values[1:]) if a != b)
        change_rate = changes / pairs_total if pairs_total else float("nan")
        distinct_per_field = grouped.nunique().median()

        if effective <= 1.2:
            style = "monoculture"
        elif change_rate >= 0.8 and effective <= 2.2:
            style = "strict alternation"
        else:
            style = "mixed sequence"
        rows.append(
            {
                "category": "cropland",
                "test": "descriptor",
                "comparison": f"{grower.upper()} crop sequence",
                "statistic": change_rate,
                "p_value": np.nan,
                "effect_size": effective,
                "effect_size_name": "effective_crop_count",
                "min_expected_count": np.nan,
                "verdict": (
                    f"{grower.upper()}: {style} — {effective:.1f} effective crops, "
                    f"{change_rate:.0%} of year pairs change class, "
                    f"{distinct_per_field:.0f} distinct class(es) per field"
                ),
                "note": "Shannon diversity over dominant classes",
            }
        )
    return pd.DataFrame(rows)


def cropland_summary(dominant: pd.DataFrame) -> pd.DataFrame:
    """Per-grower crop descriptors for the cross-grower summary table."""
    if dominant.empty:
        return pd.DataFrame()
    rows = []
    for grower, subset in dominant.groupby("grower"):
        managed = subset.loc[subset["is_managed_crop"]]
        top = (
            managed["crop_name"].value_counts(normalize=True).head(2)
            if not managed.empty
            else pd.Series(dtype=float)
        )
        rows.append(
            {
                "grower": grower,
                "crop_mix_top": ", ".join(f"{name} {share:.0%}" for name, share in top.items()),
                "split_field_years": int(subset["is_split"].sum()),
                "managed_field_years": int(subset["is_managed_crop"].sum()),
                "field_years": int(len(subset)),
            }
        )
    return pd.DataFrame(rows)
