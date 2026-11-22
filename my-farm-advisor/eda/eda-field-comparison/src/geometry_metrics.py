"""Field-boundary geometry metrics and cross-grower comparisons.

Boundaries are a single snapshot, so this category is cross-sectional by
construction — there is no within-field time series to compare.  The one
temporal angle (2021-2025 crop history) belongs to the cropland category.

Shape is described with four numbers that survive projection changes:

* ``area_ha`` / ``perimeter_m`` — geodesic (WGS84 ellipsoid), so an Argentine
  field and an Illinois field are measured the same way;
* ``compactness`` — the isoperimetric quotient ``4*pi*A/P^2`` (1.0 = circle,
  ~0.8 = square, <0.4 = strongly elongated);
* ``aspect_ratio`` — long/short side of the minimum rotated rectangle in the
  field's own UTM zone, plus the bearing of the long edge.
"""

from __future__ import annotations

import math
from itertools import combinations

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from scipy import stats

_GEOD = Geod(ellps="WGS84")

GEOMETRY_METRICS: dict[str, str] = {
    "area_ha": "hectares",
    "perimeter_m": "m",
    "compactness": "4πA/P²",
    "aspect_ratio": "long/short side",
}

#: Below this many observations per group the pairwise test is still run but
#: the verdict column carries a small-sample caveat.
MIN_GROUP_N = 3


def _utm_epsg(lon: float, lat: float) -> int:
    zone = int((lon + 180.0) // 6.0) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _long_edge_bearing_deg(geom) -> float:
    """Bearing of the min-rect long edge, degrees clockwise from north."""
    pts = list(geom.minimum_rotated_rectangle.exterior.coords)[:5]
    edges = list(zip(pts, pts[1:]))
    (x1, y1), (x2, y2) = max(
        edges, key=lambda e: (e[1][0] - e[0][0]) ** 2 + (e[1][1] - e[0][1]) ** 2
    )
    theta = math.degrees(math.atan2(x2 - x1, y2 - y1))
    while theta <= -90.0:
        theta += 180.0
    while theta > 90.0:
        theta -= 180.0
    return theta


def field_geometry(farm) -> pd.DataFrame:
    """One row per field with geodesic area/perimeter and shape descriptors."""
    rows: list[dict[str, object]] = []
    for record in farm.boundaries.itertuples():
        geom = record.geometry
        if geom is None or geom.is_empty:
            continue
        area_m2, perimeter_m = _GEOD.geometry_area_perimeter(geom)
        area_m2 = abs(area_m2)
        if perimeter_m <= 0 or area_m2 <= 0:
            continue

        point = geom.representative_point()
        epsg = _utm_epsg(point.x, point.y)
        projected = gpd.GeoSeries([geom], crs=4326).to_crs(epsg).iloc[0]
        rect = projected.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)[:5]
        edges = [
            math.dist(a, b) for a, b in zip(coords, coords[1:])
        ]
        long_side = max(edges)
        short_side = max(min(edges), 1e-9)
        compactness = 4.0 * math.pi * area_m2 / (perimeter_m**2)

        rows.append(
            {
                "grower": farm.code,
                "grower_slug": farm.grower_slug,
                "farm_slug": farm.farm_slug,
                "field_id": record.field_id,
                "state": getattr(record, "state", None),
                "country": getattr(record, "country", None),
                "county": getattr(record, "county", None),
                "area_ha": area_m2 / 10_000.0,
                "perimeter_m": perimeter_m,
                "compactness": compactness,
                "long_side_m": long_side,
                "short_side_m": short_side,
                "aspect_ratio": long_side / short_side,
                "effective_width_m": area_m2 / long_side,
                "long_edge_bearing_deg": _long_edge_bearing_deg(projected),
                "centroid_lon": point.x,
                "centroid_lat": point.y,
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"{farm.grower_slug}/{farm.farm_slug}: no usable polygons")
    order = {"il": 0, "ia": 1, "ne": 2, "ar": 3}
    frame["_order"] = frame["grower"].map(lambda g: order.get(g, 99))
    frame = frame.sort_values(["_order", "grower", "field_id"]).drop(columns="_order")
    return frame.reset_index(drop=True)


def _cliffs_delta(u_stat: float, n_a: int, n_b: int) -> float:
    """Cliff's delta for group A relative to group B, in [-1, 1].

    Positive means group A tends to hold larger values than group B.
    """
    return float(2.0 * u_stat / (n_a * n_b) - 1.0)


def _holm(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, order preserved."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        value = min(1.0, (m - rank) * p_values[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def _fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def compare_geometry(geom: pd.DataFrame) -> pd.DataFrame:
    """Kruskal-Wallis + pairwise Mann-Whitney (Holm) + Spearman rows.

    Returned long-form so one CSV carries every test and its verdict:

    ``category, metric, comparison, n_a, n_b, test, statistic, p_value,
    p_value_adjusted, effect_size, effect_size_name, verdict, note``

    With four groups of ten, p-values are descriptive.  Effect sizes and the
    per-grower medians are what the figure captions cite.
    """
    rows: list[dict[str, object]] = []
    codes = list(dict.fromkeys(geom["grower"]))
    small = f"n<{MIN_GROUP_N} per group; treat as descriptive"

    for metric in GEOMETRY_METRICS:
        groups = {
            code: geom.loc[geom["grower"].eq(code), metric].dropna().to_numpy()
            for code in codes
        }
        groups = {code: values for code, values in groups.items() if len(values)}
        if len(groups) < 2:
            continue

        medians = {code: float(np.median(v)) for code, v in groups.items()}
        widest = max(medians, key=medians.get)
        narrowest = min(medians, key=medians.get)

        if len(groups) >= 3 and all(len(v) >= MIN_GROUP_N for v in groups.values()):
            h_stat, p_value = stats.kruskal(*groups.values())
            n_total = sum(len(v) for v in groups.values())
            k = len(groups)
            epsilon_sq = max(0.0, (h_stat - k + 1) / (n_total - k))
            rows.append(
                {
                    "category": "boundaries",
                    "metric": metric,
                    "comparison": " vs ".join(f"{c.upper()}" for c in groups),
                    "n_a": n_total,
                    "n_b": None,
                    "test": "kruskal-wallis",
                    "statistic": float(h_stat),
                    "p_value": float(p_value),
                    "p_value_adjusted": None,
                    "effect_size": float(epsilon_sq),
                    "effect_size_name": "epsilon_squared",
                    "verdict": (
                        f"{metric}: groups differ in rank (H={h_stat:.2f}, "
                        f"p={_fmt_p(p_value)}); widest median {widest.upper()}="
                        f"{medians[widest]:.3g}, narrowest {narrowest.upper()}="
                        f"{medians[narrowest]:.3g}"
                    ),
                    "note": "p is descriptive at n=4 growers",
                }
            )

        pair_rows: list[dict[str, object]] = []
        for code_a, code_b in combinations(groups, 2):
            values_a, values_b = groups[code_a], groups[code_b]
            if len(values_a) < MIN_GROUP_N or len(values_b) < MIN_GROUP_N:
                note = small
            else:
                note = ""
            u_stat, p_value = stats.mannwhitneyu(
                values_a, values_b, alternative="two-sided"
            )
            delta = _cliffs_delta(float(u_stat), len(values_a), len(values_b))
            direction = "larger" if delta > 0 else "smaller"
            pair_rows.append(
                {
                    "category": "boundaries",
                    "metric": metric,
                    "comparison": f"{code_a.upper()} vs {code_b.upper()}",
                    "n_a": len(values_a),
                    "n_b": len(values_b),
                    "test": "mann-whitney-u",
                    "statistic": float(u_stat),
                    "p_value": float(p_value),
                    "effect_size": delta,
                    "effect_size_name": "cliffs_delta",
                    "verdict": (
                        f"{metric}: {code_a.upper()} {direction} than {code_b.upper()} "
                        f"(median {np.median(values_a):.3g} vs "
                        f"{np.median(values_b):.3g}, delta={delta:+.2f})"
                    ),
                    "note": note,
                }
            )
        if pair_rows:
            adjusted = _holm([float(r["p_value"]) for r in pair_rows])
            for row, adj in zip(pair_rows, adjusted):
                row["p_value_adjusted"] = adj
                if adj >= 0.05:
                    row["verdict"] += "; not separable after Holm"
            rows.extend(pair_rows)

    # Is a smaller field a more elongated field?  Report overall and per grower.
    scopes = [("all fields", geom)] + [
        (f"{code.upper()} only", geom.loc[geom["grower"].eq(code)]) for code in codes
    ]
    for label, subset in scopes:
        data = subset[["area_ha", "compactness"]].dropna()
        if len(data) < 4 or data["area_ha"].nunique() < 2:
            continue
        rho, p_value = stats.spearmanr(data["area_ha"], data["compactness"])
        rows.append(
            {
                "category": "boundaries",
                "metric": "compactness vs area_ha",
                "comparison": label,
                "n_a": int(len(data)),
                "n_b": None,
                "test": "spearman",
                "statistic": float(rho),
                "p_value": float(p_value),
                "p_value_adjusted": None,
                "effect_size": float(rho),
                "effect_size_name": "spearman_rho",
                "verdict": (
                    f"{label}: rho={rho:+.2f} (p={_fmt_p(p_value)}) — "
                    + (
                        "larger fields are more compact"
                        if rho > 0.3
                        else "larger fields are more elongated"
                        if rho < -0.3
                        else "no clear size/shape trend"
                    )
                ),
                "note": "shape-vs-size coupling",
            }
        )
    return pd.DataFrame(rows)


def geometry_summary(geom: pd.DataFrame) -> pd.DataFrame:
    """Per-grower medians and ranges used by the cross-grower summary table."""
    grouped = geom.groupby("grower", dropna=False)
    summary = grouped.agg(
        fields=("field_id", "nunique"),
        area_ha_min=("area_ha", "min"),
        area_ha_median=("area_ha", "median"),
        area_ha_max=("area_ha", "max"),
        compactness_min=("compactness", "min"),
        compactness_median=("compactness", "median"),
        compactness_max=("compactness", "max"),
        aspect_ratio_median=("aspect_ratio", "median"),
        perimeter_m_median=("perimeter_m", "median"),
    ).reset_index()
    return summary
