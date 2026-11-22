"""Non-map figures: two statistical views per category.

Every function takes tidy frames from the metric modules, writes one PNG and
returns its path.  Figures are static, deterministic (no RNG — strip points use
a fixed offset ladder) and sized to stay legible at README width.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from cropland_metrics import crop_color, ordered_crops  # noqa: E402

#: Farm identity colours, one per grower, reused by every panel.
GROWER_COLORS: dict[str, str] = {
    "il": "#0072B2",
    "ia": "#009E73",
    "ne": "#E69F00",
    "ar": "#CC79A7",
}
_FALLBACK = ("#56B4E9", "#D55E0E", "#333333")


def grower_color(code: str) -> str:
    if code in GROWER_COLORS:
        return GROWER_COLORS[code]
    known = [c for c in GROWER_COLORS if c in GROWER_COLORS]
    index = known.index(code) if code in known else len(known)
    return _FALLBACK[index % len(_FALLBACK)]


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelsize": 9,
            "axes.edgecolor": "#4B5563",
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": "#E5E7EB",
            "grid.linewidth": 0.7,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
        }
    )


def _save(fig, out: Path, note: str | None = None) -> Path:
    if note:
        # Negative y keeps the footnote below the tick labels; bbox_inches="tight"
        # expands the saved canvas to include it.
        fig.text(0.0, -0.012, note, ha="left", va="top", fontsize=6.4,
                 color="#6B7280")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def _p_text(p: float) -> str:
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"


def _title(ax, title: str, subtitle: str | None = None) -> None:
    """Main title plus a smaller grey subtitle beneath it (no overlap)."""
    ax.set_title(title, pad=21 if subtitle else 8)
    if subtitle:
        ax.text(
            0.0,
            1.004,
            subtitle,
            transform=ax.transAxes,
            fontsize=8.2,
            color="#4B5563",
            ha="left",
            va="bottom",
        )


# --------------------------------------------------------------- boundaries


def plot_area_distribution(geom: pd.DataFrame, tests: pd.DataFrame, labels: dict[str, str], out: Path) -> Path:
    """Strip + box: is field size comparable across growers?"""
    _style()
    order = (
        geom.groupby("grower")["area_ha"].median().sort_values().index.tolist()
    )
    fig, ax = plt.subplots(figsize=(7.6, 4.4))

    medians = {
        grower: float(geom.loc[geom["grower"].eq(grower), "area_ha"].median())
        for grower in order
    }
    for position, grower in enumerate(order):
        values = geom.loc[geom["grower"].eq(grower), "area_ha"].dropna().to_numpy()
        color = grower_color(grower)
        ax.boxplot(
            [values],
            positions=[position],
            widths=0.46,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": "#111827", "linewidth": 1.6},
            boxprops={"facecolor": "white", "edgecolor": color, "linewidth": 1.4},
            whiskerprops={"color": color, "linewidth": 1.1},
            capprops={"color": color, "linewidth": 1.1},
            zorder=2,
        )
        offsets = np.linspace(-0.15, 0.15, len(values)) if len(values) > 1 else np.zeros(1)
        ax.scatter(
            np.full(len(values), position) + offsets,
            values,
            s=26,
            color=color,
            edgecolor="white",
            linewidth=0.6,
            alpha=0.95,
            zorder=3,
        )

    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(
        [
            f"{g.upper()}\nmedian {medians[g]:,.0f} ha"
            for g in order
        ],
        fontsize=7.6,
    )
    ax.set_yscale("log")
    ax.set_yticks([60, 80, 100, 140, 180, 240, 300, 400])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:,.0f}"))
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_ylim(52, 430)
    ax.set_ylabel("field area (ha, log scale)")
    ax.set_xlim(-0.55, len(order) - 0.35)
    ax.grid(axis="x", visible=False)

    kruskal_row = tests.loc[
        tests["metric"].eq("area_ha") & tests["test"].eq("kruskal-wallis")
    ]
    detail = (
        f"Kruskal-Wallis {_p_text(float(kruskal_row['p_value'].iloc[0]))} · "
        f"{len(geom)} fields, {len(order)} growers (descriptive)"
        if not kruskal_row.empty
        else f"{len(geom)} fields, {len(order)} growers"
    )
    _title(
        ax,
        "Field size separates the growers before agronomy enters the picture",
        detail,
    )
    note = (
        "Geodesic area (WGS84 ellipsoid); log axis because the groups can differ "
        "by an order of magnitude."
    )
    return _save(fig, out, note)


def plot_compactness_vs_area(geom: pd.DataFrame, tests: pd.DataFrame, labels: dict[str, str], out: Path) -> Path:
    """Scatter + binned medians: does size explain shape?"""
    _style()
    fig, ax = plt.subplots(figsize=(7.6, 4.6))

    codes = [
        code
        for code in geom["grower"].drop_duplicates().tolist()
    ]
    rho_by_grower: dict[str, float] = {}
    for code in codes:
        subset = geom.loc[geom["grower"].eq(code)]
        row = tests.loc[
            tests["comparison"].eq(f"{code.upper()} only")
            & tests["metric"].eq("compactness vs area_ha")
        ]
        if not row.empty:
            rho_by_grower[code] = float(row["statistic"].iloc[0])
        rho_text = (
            f", rho={rho_by_grower[code]:+.2f}" if code in rho_by_grower else ""
        )
        ax.scatter(
            subset["area_ha"],
            subset["compactness"],
            s=48,
            color=grower_color(code),
            edgecolor="white",
            linewidth=0.7,
            alpha=0.92,
            label=f"{labels.get(code, code.upper())} (n={len(subset)}{rho_text})",
            zorder=3,
        )

    # Binned median curve: honest shape summary without fitting a model.
    ordered = geom[["area_ha", "compactness"]].dropna().sort_values("area_ha")
    if len(ordered) >= 12:
        k = min(5, len(ordered) // 8 or 1)
        xs, ys = [], []
        for indices in np.array_split(np.arange(len(ordered)), k):
            chunk = ordered.iloc[indices]
            if chunk.empty:
                continue
            xs.append(float(np.median(chunk["area_ha"])))
            ys.append(float(np.median(chunk["compactness"])))
        ax.plot(xs, ys, color="#111827", linewidth=1.6, marker="o", markersize=4,
                zorder=2, label="binned median (all fields)")

    overall = tests.loc[
        tests["comparison"].eq("all fields")
        & tests["metric"].eq("compactness vs area_ha")
    ]
    if not overall.empty:
        rho = float(overall["statistic"].iloc[0])
        p_value = float(overall["p_value"].iloc[0])
        ax.annotate(
            f"Spearman rho = {rho:+.2f}  ({_p_text(p_value)})\nall {len(geom)} fields",
            xy=(0.03, 0.96),
            xycoords="axes fraction",
            va="top",
            fontsize=7.6,
            color="#111827",
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#9CA3AF", lw=0.7),
        )

    ax.set_xscale("log")
    ax.set_xticks([60, 80, 100, 150, 200, 250, 300, 400])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:,.0f}"))
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_xlabel("field area (ha, log scale)")
    ax.set_ylabel("compactness  4πA/P²")
    ax.set_ylim(0, max(0.85, float(geom["compactness"].max()) + 0.05))
    ax.legend(loc="lower left", fontsize=7, ncol=2, columnspacing=1.0,
              handletextpad=0.4)
    _title(
        ax,
        "Small fields are also elongated — shape is not just size",
        "Compactness 1.0 = circle, ~0.79 = square, <0.4 = strongly elongated",
    )
    note = (
        "Compactness from geodesic area/perimeter; aspect ratio from the "
        "minimum rotated rectangle in the field's own UTM zone."
    )
    return _save(fig, out, note)


# ----------------------------------------------------------------- cropland


def plot_crop_composition(composition: pd.DataFrame, labels: dict[str, str], out: Path) -> Path:
    """100% stacked bars: what share of each grower's fields is in which class?"""
    _style()
    if composition.empty:
        raise ValueError("crop composition is empty; run the crop ingest first")

    crops = ordered_crops(composition["crop_name"].unique())
    rows = (
        composition[["grower", "year"]]
        .drop_duplicates()
        .sort_values(["grower", "year"])
    )
    grower_order = {"il": 0, "ia": 1, "ne": 2, "ar": 3}
    rows = rows.assign(
        _o=rows["grower"].map(lambda g: grower_order.get(g, 99))
    ).sort_values(["_o", "grower", "year"])
    lookup = {
        (r.grower, int(r.year), r.crop_name): float(r.share)
        for r in composition.itertuples()
    }

    fig, ax = plt.subplots(figsize=(8.6, 5.6))
    fig.subplots_adjust(left=0.22, right=0.78, top=0.86, bottom=0.12)

    y_positions = np.arange(len(rows))
    for position, row in enumerate(rows.itertuples()):
        left = 0.0
        for crop in crops:
            share = lookup.get((row.grower, int(row.year), crop), 0.0)
            if share <= 0:
                continue
            ax.barh(
                position,
                share,
                left=left,
                color=crop_color(crop),
                edgecolor="white",
                linewidth=0.6,
                height=0.76,
            )
            if share >= 0.085:
                text_color = "#111827"
                ax.text(
                    left + share / 2,
                    position,
                    f"{share:.0%}",
                    ha="center",
                    va="center",
                    fontsize=6.8,
                    color=text_color,
                )
            left += share

    # Grower bands and separators so the 20 rows read as four groups of five.
    # The grower name rides on the first tick label of its group, in its colour.
    previous = None
    first_row = set()
    for position, row in enumerate(rows.itertuples()):
        if previous is not None and row.grower != previous:
            ax.axhline(position - 0.5, color="#9CA3AF", linewidth=0.9)
        if row.grower != previous:
            first_row.add(position)
        previous = row.grower

    tick_labels = []
    for position, row in enumerate(rows.itertuples()):
        if position in first_row:
            tick_labels.append(f"{labels.get(row.grower, row.grower.upper())} {int(row.year)}")
        else:
            tick_labels.append(str(int(row.year)))

    ax.set_yticks(y_positions)
    ax.set_yticklabels(tick_labels, fontsize=7.4)
    for position, tick in enumerate(ax.get_yticklabels()):
        row = rows.iloc[position]
        if position in first_row:
            tick.set_color(grower_color(row["grower"]))
            tick.set_fontweight("bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.0%}"))
    ax.set_xlabel("share of field-years (dominant class)")
    ax.grid(axis="y", visible=False)

    handles = [Patch(facecolor=crop_color(c), edgecolor="white", label=c) for c in crops]
    ax.legend(
        handles=handles,
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        fontsize=7.2,
        title="dominant class",
        title_fontsize=7.6,
    )
    _title(
        ax,
        "Crop mix is grower identity: corn-soy rotation, corn-heavy, pasture",
        "Each field-year counted once, by its dominant class (CDL for US, MNC for AR)",
    )
    note = (
        "Argentina's 'Non-agricultural' is MNC class 22 (pasture/natural land), "
        "not an 'other crop'."
    )
    return _save(fig, out, note)


def plot_crop_sequence(sequence: pd.DataFrame, dominant: pd.DataFrame, labels: dict[str, str], out: Path) -> Path:
    """40-field x 5-year categorical heatmap — the within-field time story."""
    _style()
    if sequence.empty:
        raise ValueError("crop sequence is empty; run the crop ingest first")

    years = sorted(int(year) for year in dominant["year"].dropna().unique())
    crops = ordered_crops(dominant["crop_name"].unique())
    color_by_crop = {crop: crop_color(crop) for crop in crops}
    index_by_crop = {crop: i for i, crop in enumerate(crops)}

    grower_order = {"il": 0, "ia": 1, "ne": 2, "ar": 3}
    sequence = sequence.copy()
    sequence["_o"] = sequence["grower"].map(lambda g: grower_order.get(g, 99))
    sequence["_f"] = sequence["field_id"].map(_natural_str)
    sequence = sequence.sort_values(["_o", "grower", "_f"]).reset_index(drop=True)

    grid = np.full((len(sequence), len(years)), np.nan)
    purity = {}
    for row_index, row in sequence.iterrows():
        for column_index, year in enumerate(years):
            crop = row.get(year)
            if isinstance(crop, str) and crop in index_by_crop:
                grid[row_index, column_index] = index_by_crop[crop]
    for record in dominant.itertuples():
        purity[(record.field_id, int(record.year))] = (
            float(record.purity_pct),
            bool(record.is_split),
        )

    cmap = matplotlib.colors.ListedColormap([color_by_crop[c] for c in crops])
    cmap.set_bad("#F3F4F6")

    fig_height = max(7.0, 0.235 * len(sequence) + 2.4)
    fig, ax = plt.subplots(figsize=(7.4, fig_height))
    fig.subplots_adjust(left=0.24, right=0.98, top=0.93, bottom=0.06)

    ax.imshow(
        np.ma.masked_invalid(grid),
        aspect="auto",
        cmap=cmap,
        vmin=-0.5,
        vmax=len(crops) - 0.5,
        interpolation="nearest",
    )
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(year) for year in years])
    ax.set_yticks(range(len(sequence)))
    ax.set_yticklabels(sequence["field_id"], fontsize=6.4)
    ax.set_xticks(np.arange(-0.5, len(years), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(sequence), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", length=0)
    ax.grid(which="major", visible=False)

    for row_index, row in sequence.iterrows():
        for column_index, year in enumerate(years):
            key = (row["field_id"], year)
            if key not in purity:
                continue
            value, is_split = purity[key]
            if is_split:
                ax.text(
                    column_index,
                    row_index,
                    f"{value:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=5.8,
                    color="#111827",
                    fontweight="bold",
                )

    previous = None
    for row_index, row in sequence.iterrows():
        if previous is not None and row["grower"] != previous:
            ax.axhline(row_index - 0.5, color="#111827", linewidth=1.1)
        previous = row["grower"]
    for grower, subset in sequence.groupby("grower", sort=False):
        positions = subset.index.tolist()
        centre = (min(positions) + max(positions)) / 2
        ax.text(
            -0.085,
            centre,
            labels.get(grower, grower.upper()),
            transform=ax.get_yaxis_transform(),
            ha="right",
            va="center",
            fontsize=8.4,
            fontweight="bold",
            color=grower_color(grower),
        )

    handles = [Patch(facecolor=color_by_crop[c], edgecolor="white", label=c) for c in crops]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.035),
        ncol=min(5, len(crops)),
        fontsize=7,
    )
    _title(
        ax,
        "Five years per field: rotation, monoculture, and the AR conversion",
        "Rows grouped by grower; a bold percentage marks a split field-year "
        "(dominant class <60%)",
    )
    note = (
        "Dominant class per field-year. Missing years stay blank; the AR "
        "pasture block (ar-o1..o3) is non-agricultural in all five years."
    )
    return _save(fig, out, note)


def _natural_key(value: object) -> list[object]:
    import re

    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(value))
    ]


def _natural_str(value: object) -> str:
    """Zero-padded natural sort key that is hashable (DataFrame sort_values)."""
    import re

    return "".join(
        part.rjust(9, "0") if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(value))
    )


# ------------------------------------------------------------------ weather


def plot_annual_precip(
    annual: pd.DataFrame,
    field_series: pd.DataFrame,
    labels: dict[str, str],
    out: Path,
) -> Path:
    """Annual precipitation per distinct weather series."""
    _style()
    if annual.empty:
        raise ValueError("weather aggregates are empty")

    series_grower = (
        field_series.drop_duplicates("series_id")
        .set_index("series_id")["grower"]
        .to_dict()
    )
    counts = field_series.groupby("grower")["series_id"].nunique().to_dict()
    grower_order = {"il": 0, "ia": 1, "ne": 2, "ar": 3}

    fig, ax = plt.subplots(figsize=(9.2, 4.5))
    fig.subplots_adjust(left=0.075, right=0.70, top=0.83, bottom=0.14)
    handles = []
    for grower in sorted(counts, key=lambda g: grower_order.get(g, 99)):
        series_ids = sorted(
            [s for s, g in series_grower.items() if g == grower], key=_natural_key
        )
        color = grower_color(grower)
        for series_id in series_ids:
            subset = annual.loc[annual["series_id"].eq(series_id)].sort_values("year")
            ax.plot(
                subset["year"],
                subset["precip_mm"],
                color=color,
                linewidth=1.0 if len(series_ids) > 1 else 2.0,
                alpha=0.45 if len(series_ids) > 1 else 0.95,
                marker="o",
                markersize=2.6 if len(series_ids) > 1 else 4.5,
                zorder=2,
            )
        mean = (
            annual.loc[annual["series_id"].isin(series_ids)]
            .groupby("year")["precip_mm"]
            .mean()
        )
        if len(series_ids) > 1:
            ax.plot(
                mean.index,
                mean.to_numpy(),
                color=color,
                linewidth=2.2,
                marker="o",
                markersize=4.2,
                zorder=3,
            )
        handles.append(
            Line2D(
                [], [], color=color, linewidth=2.2,
                label=f"{labels.get(grower, grower.upper())} "
                      f"({counts[grower]} series / {int(field_series.loc[field_series.grower.eq(grower), 'field_id'].nunique())} fields)",
            )
        )

    ax.set_xticks(sorted(annual["year"].unique()))
    ax.set_xlabel("year")
    ax.set_ylabel("annual precipitation (mm)")
    ax.set_xlim(annual["year"].min() - 0.25, annual["year"].max() + 0.25)
    ax.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        fontsize=7.4,
        title="annual total by series",
        title_fontsize=7.6,
    )
    _title(
        ax,
        "Water supply: Argentina is wettest and most volatile, Nebraska driest",
        "Thin lines = distinct series, thick line = series mean; fields that share "
        "a series are one observation, not many",
    )
    note = (
        "NASA POWER PRECTOTCORR summed per series-year; series are de-duplicated "
        "across fields before aggregation."
    )
    return _save(fig, out, note)


def plot_monthly_temperature(
    monthly: pd.DataFrame,
    gdd_note: str,
    labels: dict[str, str],
    out: Path,
) -> Path:
    """Monthly temperature climatology with a year-to-year envelope."""
    _style()
    if monthly.empty:
        raise ValueError("monthly weather aggregates are empty")

    grower_order = {"il": 0, "ia": 1, "ne": 2, "ar": 3}
    growers = sorted(monthly["grower"].unique(), key=lambda g: grower_order.get(g, 99))
    months = list(range(1, 13))
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                    "Sep", "Oct", "Nov", "Dec"]

    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    ax.axhline(10.0, color="#9CA3AF", linewidth=0.9, linestyle="--", zorder=1)
    ax.annotate(
        "GDD base 10 °C",
        xy=(0.008, 10.0),
        xycoords=("axes fraction", "data"),
        fontsize=6.8,
        color="#6B7280",
        va="bottom",
        ha="left",
    )

    for grower in growers:
        subset = monthly.loc[monthly["grower"].eq(grower)]
        stats = (
            subset.groupby("month")["tmean_c"]
            .agg(["mean", "min", "max"])
            .reindex(months)
        )
        color = grower_color(grower)
        ax.fill_between(
            months,
            stats["min"],
            stats["max"],
            color=color,
            alpha=0.13,
            linewidth=0,
            zorder=2,
        )
        ax.plot(
            months,
            stats["mean"],
            color=color,
            linewidth=2.0,
            marker="o",
            markersize=3.6,
            label=labels.get(grower, grower.upper()),
            zorder=3,
        )

    ax.set_xticks(months)
    ax.set_xticklabels(month_labels)
    ax.set_xlim(0.6, 12.4)
    ax.set_ylabel("monthly mean temperature (°C)")
    ax.set_xlabel("month")
    ax.legend(loc="upper left", fontsize=7.6, ncol=2)
    _title(
        ax,
        "Season length, not just rainfall, separates the four growers",
        gdd_note,
    )
    note = (
        "Lines = farm mean across years and series; bands = min-max across years. "
        "GDD10 is the sum of max(T2M-10, 0) over the year."
    )
    return _save(fig, out, note)
