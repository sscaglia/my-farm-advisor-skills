"""Grower-level multi-field maps (boundaries, 2025 crops, weather series).

These are *not* single-field field-local frames: each panel shows all ten
fields of one grower, so the frame is fitted to the farm union.  The contract
from ``data-pipeline/references/field-map-frame.md`` still applies where it
makes sense:

* metre axes stay visible and honest — x/y are metres from the SW corner of
  the rotated farm union, and the axis label names the rotation;
* a boxed true-north arrow is drawn (``field_frame.decorate``);
* the keyless Esri World Imagery underlay is drawn first, warped into the same
  frame, and covers the padded viewport so no white ring appears;
* **no scale bar** — the tick axes carry distance on every panel, which is
  the repo default.

The one deliberate deviation: the rotation callout says "frame rotated", not
"field rotated", because the tilt belongs to the farm union rather than to any
single field polygon.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colors as mcolors  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from datasets import ensure_runtime_libs  # noqa: E402

ensure_runtime_libs()

from lib import basemap as bm  # noqa: E402
from lib import field_frame as ff  # noqa: E402

from cropland_metrics import crop_color, ordered_crops  # noqa: E402
from figures import grower_color  # noqa: E402

_PANEL_H_IN = 4.0
_PANEL_W_IN = 6.4
_MAX_PIXELS = 1100
_MAP_DPI = 100
_HEADER_IN = 0.95
_FOOTER_IN = 0.95
_ROW_GAP_IN = 0.95
_WSPACE = 0.10
_LEFT = 0.05
_RIGHT = 0.99


def shade(hex_color: str, factor: float) -> str:
    """Darken (factor < 1) or lighten (factor > 1) toward the extremes."""
    red, green, blue = mcolors.to_rgb(hex_color)
    if factor <= 1.0:
        # blend toward black
        rgb = (red * factor, green * factor, blue * factor)
    else:
        weight = min(factor - 1.0, 1.0)
        rgb = (
            red + (1.0 - red) * weight,
            green + (1.0 - green) * weight,
            blue + (1.0 - blue) * weight,
        )
    return mcolors.to_hex(rgb)


def series_colors(field_series) -> dict[str, str]:
    """One colour family per grower, one shade per series."""
    mapping: dict[str, str] = {}
    for grower, subset in field_series.groupby("grower"):
        series_ids = sorted(subset["series_id"].unique())
        count = len(series_ids)
        base = grower_color(grower)
        factors = (
            [0.45]
            if count == 1
            else list(np.linspace(0.40, 1.30, count))
        )
        for series_id, factor in zip(series_ids, factors):
            mapping[series_id] = shade(base, float(factor))
    return mapping


def _farm_frames(farms) -> dict[str, object]:
    """One rotated farm frame per grower, computed once per map."""
    return {
        code: ff.frame_for(
            farm.boundaries, panel_h_in=_PANEL_H_IN, panel_w_in=_PANEL_W_IN
        )
        for code, farm in farms.items()
    }


def _grid(codes, frames):
    """Panel grid sized to the content, so equal-aspect axes fill their box.

    A fixed panel box wastes vertical space whenever the farm union is wider
    than the box's aspect (Argentina and Iowa are ~2:1, Illinois ~1.5:1) —
    ``set_aspect("equal")`` then letterboxes each panel and the figure grows a
    dead band between the rows.  Instead each row is allotted the height its
    own panels need, from the content aspect.
    """
    count = len(codes)
    columns = 2 if count > 1 else 1
    rows = math.ceil(count / columns)
    figure_width = _PANEL_W_IN * columns + 1.2
    panel_width = (_RIGHT - _LEFT) * figure_width / (columns + _WSPACE * (columns - 1))

    row_heights: list[float] = []
    for row in range(rows):
        row_codes = codes[row * columns : (row + 1) * columns]
        aspects = []
        for code in row_codes:
            bounds = frames[code].geometry.total_bounds
            width = max(float(bounds[2] - bounds[0]), 1.0)
            height = max(float(bounds[3] - bounds[1]), 1.0)
            aspects.append(width / height)
        row_heights.append(panel_width / min(aspects))

    row_gap = _ROW_GAP_IN * (rows - 1)
    figure_height = sum(row_heights) + row_gap + _HEADER_IN + _FOOTER_IN
    hspace = row_gap / (sum(row_heights) / rows) if rows > 1 else 0.0
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(figure_width, figure_height),
        gridspec_kw={"height_ratios": row_heights},
    )
    fig.subplots_adjust(
        left=_LEFT,
        right=_RIGHT,
        top=1.0 - _HEADER_IN / figure_height,
        bottom=_FOOTER_IN / figure_height,
        wspace=_WSPACE,
        hspace=hspace,
    )
    flat = np.atleast_1d(axes).ravel().tolist()
    for ax in flat[count:]:
        ax.set_visible(False)
    return fig, flat[:count]


def _arrow_place(
    frame, extent: tuple[float, float, float, float]
) -> tuple[float, float, float]:
    """Axes-fraction anchor and radius for the north arrow.

    Picks the corner with the fewest parcel centroids inside its footprint, so
    the arrow never sits on top of a field (Nebraska's ne-r4 is exactly in the
    default top-right corner).  The anchor is then pulled back along the arrow's
    own direction so the boxed "N" stays inside the axes.
    """
    left, right, bottom, top = extent
    span_x = max(right - left, 1e-9)
    span_y = max(top - bottom, 1e-9)
    points = frame.geometry.geometry.representative_point()
    fx = np.clip((points.x.to_numpy() - left) / span_x, -0.5, 1.5)
    fy = np.clip((points.y.to_numpy() - bottom) / span_y, -0.5, 1.5)

    corners = [(0.93, 0.93), (0.07, 0.93), (0.93, 0.07), (0.07, 0.07)]
    best = corners[0]
    best_score = None
    for cx, cy in corners:
        score = int(np.sum(np.abs(fx - cx) < 0.22) + np.sum(np.abs(fy - cy) < 0.18))
        if best_score is None or score < best_score:
            best, best_score = (cx, cy), score

    adx, ady = float(frame.adx), float(frame.ady)
    reach = 0.19  # arrow tip plus the boxed "N" beyond it
    x = min(max(best[0], reach * max(-adx, 0.0) + 0.01),
            1.0 - reach * max(adx, 0.0) - 0.01)
    y = min(max(best[1], reach * max(-ady, 0.0) + 0.01),
            1.0 - reach * max(ady, 0.0) - 0.01)
    return float(x), float(y), 0.105


def _panel(
    ax,
    farm,
    frame,
    color_by_field: dict[str, str],
    panel_title: str,
) -> None:
    width = float(frame.geometry.total_bounds[2])
    height = float(frame.geometry.total_bounds[3])
    left, right, bottom, top = ff.view_extent(0.0, width, 0.0, height)
    extended = (left, right, bottom, top)
    pixels_x = int(np.clip((right - left) / 6.0, 400, _MAX_PIXELS))
    pixels_y = int(np.clip((top - bottom) / 6.0, 400, _MAX_PIXELS))

    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    bm.draw(ax, frame, extended, pixels_y, pixels_x)

    coloured = frame.geometry.copy()
    coloured["_color"] = [
        color_by_field.get(str(field_id), "#9CA3AF")
        for field_id in coloured["field_id"]
    ]
    coloured.plot(
        ax=ax,
        color=coloured["_color"],
        edgecolor="white",
        linewidth=1.7,
        alpha=0.82,
        zorder=2,
    )

    # Park the arrow in the quietest corner, pulled back along its own
    # direction so the boxed "N" stays inside the axes (Nebraska points almost
    # due east and would otherwise push the label into the next panel).
    arrow_x, arrow_y, arrow_r = _arrow_place(frame, (left, right, bottom, top))
    ff.decorate(
        ax,
        frame,
        arrow_r=arrow_r,
        arrow_fs=13.0,
        arrow_xy=(arrow_x, arrow_y),
        callout=False,
    )
    ax.set_aspect("equal")
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)
    ax.xaxis.set_major_locator(MaxNLocator(4))
    ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.tick_params(labelsize=6.2, length=2.5)
    rotation = (
        f" (frame rotated {frame.rot:+.0f}°)" if abs(frame.rot) >= 0.5 else ""
    )
    ax.set_xlabel(f"m from SW corner{rotation}", fontsize=6.4)
    ax.set_ylabel("grower-local m", fontsize=6.4)
    ax.set_title(panel_title, loc="left", fontsize=9.2)


def _finish(fig, axes, out: Path, title: str, subtitle: str,
            legend_handles, legend_title: str | None) -> Path:
    # A single imagery credit, not one per panel.
    for ax in axes:
        for text in list(ax.texts):
            if text.get_text().startswith("Imagery"):
                text.remove()
    height_in = fig.get_size_inches()[1]
    fig.suptitle(title, fontsize=11.5, x=0.012, ha="left", y=1.0 - 0.20 / height_in)
    fig.text(
        0.012,
        1.0 - 0.42 / height_in,
        subtitle,
        fontsize=8.2,
        color="#4B5563",
        ha="left",
        va="top",
    )

    if legend_handles:
        fig.legend(
            handles=legend_handles,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.010),
            ncol=min(len(legend_handles), 10),
            fontsize=7.0,
            title=legend_title,
            title_fontsize=7.4,
        )
    fig.text(0.995, 0.004, "Imagery © Esri", ha="right", va="bottom",
             fontsize=5.6, color="#6B7280")

    out.parent.mkdir(parents=True, exist_ok=True)
    # Imagery-heavy plates: 100 dpi keeps four aerial-tile panels at ~1.7 MB,
    # in line with the repo's other committed map examples.
    fig.savefig(out, dpi=_MAP_DPI, bbox_inches="tight")
    plt.close(fig)
    return out


def boundaries_map(farms, geom, out: Path) -> Path:
    """A4 — where each grower's land sits and how it is arranged."""
    codes = list(farms)
    frames = _farm_frames(farms)
    fig, axes = _grid(codes, frames)
    for ax, code in zip(axes, codes):
        farm = farms[code]
        subset = geom.loc[geom["grower"].eq(code)]
        color = grower_color(code)
        colors = {field_id: color for field_id in subset["field_id"]}
        title = (
            f"{farm.display_name} — {len(subset)} fields, "
            f"{subset['area_ha'].sum():,.0f} ha"
        )
        _panel(ax, farm, frames[code], colors, title)

    return _finish(
        fig,
        axes,
        out,
        "County-scale footprints: ten dispersed parcels per grower, not one block",
        "True-scale parcels in a grower-local metre frame; ids and measurements "
        "are in field_geometry.csv, per-field history in the crop-sequence plate",
        legend_handles=[],
        legend_title=None,
    )


def latest_crop_map(farms, dominant, year: int, out: Path) -> Path:
    """B4 — what is on the ground in the latest mapped year."""
    latest = dominant.loc[dominant["year"].eq(year)]
    crops = ordered_crops(latest["crop_name"].drop_duplicates().tolist())

    codes = list(farms)
    frames = _farm_frames(farms)
    fig, axes = _grid(codes, frames)
    for ax, code in zip(axes, codes):
        farm = farms[code]
        subset = latest.loc[latest["grower"].eq(code)]
        color_by_field = {
            row.field_id: crop_color(row.crop_name) for row in subset.itertuples()
        }
        # No field ids here: ten labels on a 50 km panel collapse into noise,
        # and the id cannot be read at README size anyway.  Class is the story;
        # per-field identity lives in the sequence plate and the CSVs.
        title = f"{farm.display_name} — {len(subset)} fields, {year}"
        _panel(ax, farm, frames[code], color_by_field, title)

    handles = [Patch(facecolor=crop_color(c), edgecolor="white", label=c) for c in crops]
    return _finish(
        fig,
        axes,
        out,
        f"Latest mapped crops ({year}): corn-soy rotation, corn-heavy, pasture",
        "Dominant CDL/MNC class per field, coloured at true footprint; a split field "
        "takes its majority class",
        legend_handles=handles,
        legend_title="dominant class",
    )


def weather_series_map(farms, field_series, out: Path) -> Path:
    """C4 — which fields actually share a weather series."""
    palette = series_colors(field_series)
    series_to_grower = (
        field_series.drop_duplicates("series_id")
        .set_index("series_id")["grower"]
        .to_dict()
    )
    codes = list(farms)
    frames = _farm_frames(farms)
    fig, axes = _grid(codes, frames)
    for ax, code in zip(axes, codes):
        farm = farms[code]
        subset = field_series.loc[field_series["grower"].eq(code)]
        field_to_series = dict(zip(subset["field_id"], subset["series_id"]))
        color_by_field = {
            field_id: palette.get(series_id, "#9CA3AF")
            for field_id, series_id in field_to_series.items()
        }
        count = subset["series_id"].nunique()
        title = (
            f"{farm.display_name} — {len(subset)} fields, "
            f"{count} weather series"
        )
        # Identical fill = identical series, which is the whole point: the
        # legend maps colour to series_id, and weather_series.csv maps series to
        # field.
        _panel(ax, farm, frames[code], color_by_field, title)

    handles = []
    for series_id in sorted(palette):
        grower = series_to_grower.get(series_id, "")
        handles.append(
            Patch(
                facecolor=palette[series_id],
                edgecolor="white",
                label=f"{series_id} ({grower.upper()})",
            )
        )
    return _finish(
        fig,
        axes,
        out,
        "The weather grid is not the field grid: 40 fields resolve to 10 series",
        "Identical fill = identical daily weather; Argentina's ten fields share one series",
        legend_handles=handles,
        legend_title="weather series",
    )
