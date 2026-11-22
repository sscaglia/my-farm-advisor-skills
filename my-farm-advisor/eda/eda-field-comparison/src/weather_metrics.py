"""Weather series identity, aggregation and correlation.

The critical fact this module exists to expose: **weather rows are written per
field, but the underlying grid cell is shared.**  In the Assignment 2 runtime
40 fields resolve to 10 distinct daily series — Illinois 4, Iowa 3, Nebraska 2,
Argentina **1**.  Treating ten Argentine fields as ten independent climate
observations produces pure noise, and summing the rows without de-duplicating
inflates annual precipitation and GDD ten-fold.

So the unit of weather analysis here is the *series*, not the field.  Field
identity is preserved in ``weather_series.csv`` so any field-level claim can be
traced back to the series that actually carries it.

Derived quantities:

* ``gdd10`` — daily ``max(T2M - 10, 0)`` summed over the year (base 10 °C, the
  conventional corn base).  ``T2M`` is the daily mean, not ``(max+min)/2``;
  the two differ slightly, so the definition is stated wherever GDD is cited.
* ``gs_precip_mm`` — precipitation summed over 1 April - 31 October.
* ``frost_days`` — days with ``T2M_MIN <= 0``.
* ``dry_days`` — days with ``PRECTOTCORR < 1 mm``.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from datasets import WEATHER_VALUE_COLUMNS

#: A field-year needs at least this share of the expected days to be trusted.
MIN_YEAR_COVERAGE = 0.9

_GROWING_SEASON_MONTHS = (4, 5, 6, 7, 8, 9, 10)


def _series_signature(frame: pd.DataFrame) -> str:
    ordered = frame.sort_values("date")
    values = ordered[list(WEATHER_VALUE_COLUMNS)].to_numpy(dtype="float64")
    values = np.round(values, 4)
    return hashlib.sha1(values.tobytes()).hexdigest()[:12]


def assign_series(weather: pd.DataFrame, farm) -> pd.DataFrame:
    """Attach a stable ``series_id`` to every weather row.

    Fields whose rounded daily values are identical share a series.  Labels
    are ``<grower>-S1``, ``-S2`` ... in order of first appearance, so the
    label is stable across re-runs on the same data.
    """
    if weather.empty:
        return weather.assign(series_id=pd.Series(dtype=str))
    signatures: dict[str, str] = {}
    for field_id, group in weather.groupby("field_id", sort=False):
        signatures[str(field_id)] = _series_signature(group)

    label_by_signature: dict[str, str] = {}
    for field_id in sorted(signatures, key=_natural):
        signature = signatures[field_id]
        if signature not in label_by_signature:
            label_by_signature[signature] = f"{farm.code}-S{len(label_by_signature) + 1}"

    mapping = {fid: label_by_signature[sig] for fid, sig in signatures.items()}
    frame = weather.copy()
    frame["series_id"] = frame["field_id"].map(mapping)
    return frame


def _natural(value: object) -> list[object]:
    import re

    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(value))
    ]


def field_series_table(weather: pd.DataFrame, farm) -> pd.DataFrame:
    """One row per field: which series it uses and how complete it is."""
    if weather.empty:
        return pd.DataFrame(
            columns=["grower", "field_id", "series_id", "days", "first_date", "last_date"]
        )
    grouped = weather.groupby(["field_id", "series_id"], as_index=False).agg(
        days=("date", "nunique"),
        first_date=("date", "min"),
        last_date=("date", "max"),
    )
    grouped.insert(0, "grower", farm.code)
    return grouped.sort_values(["field_id"], key=lambda s: s.map(_natural)).reset_index(
        drop=True
    )


def series_weather(weather: pd.DataFrame) -> pd.DataFrame:
    """Collapse field rows to one row per series-day (the de-duplication step)."""
    if weather.empty:
        return weather
    frame = (
        weather.sort_values(["series_id", "date"])
        .drop_duplicates(["series_id", "date"], keep="first")
        .reset_index(drop=True)
    )
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    frame["gdd10"] = (frame["T2M"] - 10.0).clip(lower=0.0)
    frame["frost_day"] = frame["T2M_MIN"] <= 0.0
    frame["dry_day"] = frame["PRECTOTCORR"] < 1.0
    frame["in_season"] = frame["month"].isin(_GROWING_SEASON_MONTHS)
    return frame


def annual_by_series(series: pd.DataFrame) -> pd.DataFrame:
    """Year x series aggregates — the basis for C1 and the audit."""
    if series.empty:
        return pd.DataFrame()
    rows = []
    for (series_id, year), group in series.groupby(["series_id", "year"], sort=True):
        expected_days = 366 if _leap(year) else 365
        rows.append(
            {
                "series_id": series_id,
                "year": int(year),
                "days": int(group["date"].nunique()),
                "coverage": group["date"].nunique() / expected_days,
                "precip_mm": float(group["PRECTOTCORR"].sum()),
                "gs_precip_mm": float(
                    group.loc[group["in_season"], "PRECTOTCORR"].sum()
                ),
                "gdd10": float(group["gdd10"].sum()),
                "tmean_c": float(group["T2M"].mean()),
                "tmax_mean_c": float(group["T2M_MAX"].mean()),
                "tmin_min_c": float(group["T2M_MIN"].min()),
                "frost_days": int(group["frost_day"].sum()),
                "dry_days": int(group["dry_day"].sum()),
            }
        )
    frame = pd.DataFrame(rows)
    frame["coverage_ok"] = frame["coverage"] >= MIN_YEAR_COVERAGE
    return frame


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def monthly_by_farm_year(series: pd.DataFrame, farm) -> pd.DataFrame:
    """Month x farm x year mean temperature (climatology envelope input)."""
    if series.empty:
        return pd.DataFrame(columns=["grower", "year", "month", "tmean_c", "precip_mm"])
    grouped = series.groupby(["year", "month"], as_index=False).agg(
        tmean_c=("T2M", "mean"),
        precip_mm=("PRECTOTCORR", "sum"),
        gdd10=("gdd10", "sum"),
    )
    grouped.insert(0, "grower", farm.code)
    return grouped


def correlation(series: pd.DataFrame, series_ids: list[str]) -> pd.DataFrame:
    """Pairwise daily Pearson r for temperature and precipitation."""
    if series.empty or len(series_ids) < 2:
        return pd.DataFrame(
            columns=[
                "series_a",
                "series_b",
                "n_days",
                "r_t2m",
                "p_t2m",
                "r_precip",
                "p_precip",
                "mean_abs_precip_diff_mm",
            ]
        )
    temp = series.pivot_table(index="date", columns="series_id", values="T2M")
    precip = series.pivot_table(
        index="date", columns="series_id", values="PRECTOTCORR"
    )
    rows = []
    for i, series_a in enumerate(series_ids):
        for series_b in series_ids[i + 1 :]:
            pair = pd.concat(
                [
                    temp[[series_a, series_b]].rename(columns={series_a: "a", series_b: "b"}),
                    precip[[series_a, series_b]].rename(
                        columns={series_a: "pa", series_b: "pb"}
                    ),
                ],
                axis=1,
            ).dropna()
            rows.append(
                {
                    "series_a": series_a,
                    "series_b": series_b,
                    "n_days": int(len(pair)),
                    "r_t2m": float(pair["a"].corr(pair["b"])),
                    "p_t2m": np.nan,
                    "r_precip": float(pair["pa"].corr(pair["pb"])),
                    "p_precip": np.nan,
                    "mean_abs_precip_diff_mm": float(
                        (pair["pa"] - pair["pb"]).abs().mean()
                    ),
                }
            )
    return pd.DataFrame(rows)


def audit(field_series: pd.DataFrame, annual: pd.DataFrame, corr: pd.DataFrame) -> pd.DataFrame:
    """Per-grower weather independence and spread — the C3 verdict table."""
    rows: list[dict[str, object]] = []
    for grower, subset in field_series.groupby("grower"):
        series_ids = sorted(subset["series_id"].unique(), key=_natural)
        per_series = annual.loc[annual["series_id"].isin(series_ids)]
        if per_series.empty:
            continue
        precip_by_year = per_series.groupby("year")["precip_mm"]
        series_spread = (precip_by_year.max() - precip_by_year.min()).max()
        corr_subset = corr.loc[
            corr["series_a"].isin(series_ids) & corr["series_b"].isin(series_ids)
        ]
        max_r_temp = (
            float(corr_subset["r_t2m"].abs().max()) if not corr_subset.empty else np.nan
        )
        max_r_precip = (
            float(corr_subset["r_precip"].abs().max())
            if not corr_subset.empty
            else np.nan
        )

        n_fields = int(subset["field_id"].nunique())
        n_series = len(series_ids)
        if n_series == 1:
            verdict = (
                f"{grower.upper()}: all {n_fields} fields share one weather series "
                "— within-grower weather comparison is null by construction"
            )
        elif n_series < n_fields:
            verdict = (
                f"{grower.upper()}: {n_fields} fields collapse into {n_series} series "
                "— fields are not independent climate replicates"
            )
        else:
            verdict = f"{grower.upper()}: every field has its own series"

        rows.append(
            {
                "category": "weather",
                "grower": grower,
                "fields": n_fields,
                "series_count": n_series,
                "series_ids": ", ".join(series_ids),
                "annual_precip_min_mm": float(per_series["precip_mm"].min()),
                "annual_precip_max_mm": float(per_series["precip_mm"].max()),
                "annual_precip_series_spread_mm": float(series_spread),
                "gdd10_min": float(per_series["gdd10"].min()),
                "gdd10_max": float(per_series["gdd10"].max()),
                "max_abs_r_t2m": max_r_temp,
                "max_abs_r_precip": max_r_precip,
                "min_daily_coverage": float(per_series["coverage"].min()),
                "verdict": verdict,
            }
        )
    return pd.DataFrame(rows)


def weather_summary(audit_table: pd.DataFrame, annual: pd.DataFrame, field_series: pd.DataFrame) -> pd.DataFrame:
    """Compact per-grower row for the cross-grower summary table."""
    if audit_table.empty:
        return pd.DataFrame()
    frame = audit_table[
        [
            "grower",
            "series_count",
            "annual_precip_min_mm",
            "annual_precip_max_mm",
            "gdd10_min",
            "gdd10_max",
        ]
    ].copy()
    frame = frame.rename(
        columns={
            "series_count": "weather_series",
            "annual_precip_min_mm": "precip_min_mm",
            "annual_precip_max_mm": "precip_max_mm",
        }
    )
    return frame
