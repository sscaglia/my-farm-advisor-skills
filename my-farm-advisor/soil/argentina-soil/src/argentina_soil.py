"""INTA Entre Ríos soil survey provider (Argentina).

Primary source
--------------
INTA GeoNode node 03, dataset 347 "Suelos de Entre Ríos Escala 1:100000":

    https://geo-nodo03.inta.gob.ar/catalogue/#/dataset/347
    WFS: https://geo-nodo03.inta.gob.ar/geoserver/ows
    Layer: geonode:carta_de_suelos_unocienmil_df05b067570a0dea80e67f5aa41aa5d6

The service is keyless and public domain.  Cite Bedendo DJ, Schulz GA,
Pausich GM, Tentor F. (2014), Cartas de Suelos de Entre Ríos.

The WFS carries one record per soil map unit (``ogc_fid``) with ``simb``,
``nombre``, ``depart``, up to seven component series (``serie_1..7``), their
percentages (``porc_1..7``), taxonomic classes (``t_1..7``), limitation notes
(``l_1..7``), erosion classes, and links to the series fact sheets.

Series fact sheets (GeoNode documents) carry the analytical profile used for
the SSURGO-schema horizon table:

====================  ===========  ==========================================
Series                Document     URL
====================  ===========  ==========================================
La Monona             201          https://geo-nodo03.inta.gob.ar/documents/201/download
Estancia Retiro       127          https://geo-nodo03.inta.gob.ar/documents/127/download
Larroque              215          https://geo-nodo03.inta.gob.ar/documents/215/download
La Laura              196          https://geo-nodo03.inta.gob.ar/documents/196/download
San Simón             304          https://geo-nodo03.inta.gob.ar/documents/304/download
====================  ===========  ==========================================

Every value in :data:`SERIES_PROFILES` below was transcribed from those PDFs
(accessed 2026-11-08).  Clay is the ``<2 µm`` fraction, silt the ``2-50 µm``
fraction, and sand the sum of the ``50-2000 µm`` fractions.  AWC is estimated
from the USDA texture class; measured moisture equivalent is retained in
:data:`SERIES_PROFILES` for audit but is not substituted for AWC.

The provider returns SSURGO-compatible rows so the existing soil reports,
posters, texture triangles, and farm HTML work unchanged.  ``soil_source`` is
set to ``inta_entre_rios_100k`` and ``mukey`` is namespaced (``AR-ER-<fid>``)
so it can never collide with a USDA MUKEY.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape

SOURCE_NAME = "inta_entre_rios_100k"
WFS_URL = "https://geo-nodo03.inta.gob.ar/geoserver/ows"
LAYER = "geonode:carta_de_suelos_unocienmil_df05b067570a0dea80e67f5aa41aa5d6"
DATASET_PAGE = "https://geo-nodo03.inta.gob.ar/catalogue/#/dataset/347"
LICENSE = "Public domain (INTA); cite Bedendo et al. (2014)"
ATTRIBUTION = (
    "INTA - Cartas de Suelos de Entre Ríos, escala 1:100.000 "
    "(Bedendo DJ, Schulz GA, Pausich GM, Tentor F., 2014)"
)
ACCESS_DATE = "2026-11-08"
SERIES_DOCUMENTS = {
    "La Monona": "https://geo-nodo03.inta.gob.ar/documents/201/download",
    "Estancia Retiro": "https://geo-nodo03.inta.gob.ar/documents/127/download",
    "Larroque": "https://geo-nodo03.inta.gob.ar/documents/215/download",
    "La Laura": "https://geo-nodo03.inta.gob.ar/documents/196/download",
    "San Simón": "https://geo-nodo03.inta.gob.ar/documents/304/download",
}

# USD texture class -> representative available water capacity (cm/cm).
# Source: standard FAO/USDA texture-class ranges.  This is a texture-class
# estimate; the series PDFs' measured moisture equivalent is kept separately.
AWC_BY_TEXTURE = {
    "sand": 0.05,
    "loamy sand": 0.07,
    "sandy loam": 0.11,
    "loam": 0.17,
    "silt loam": 0.20,
    "silt": 0.18,
    "sandy clay loam": 0.14,
    "clay loam": 0.18,
    "silty clay loam": 0.19,
    "sandy clay": 0.15,
    "silty clay": 0.18,
    "clay": 0.16,
}


def _horizon(
    name: str,
    top_cm: float,
    bottom_cm: float,
    om_pct: float,
    ph: float,
    cec: float,
    clay_pct: float,
    silt_pct: float,
    sand_pct: float,
    caco3_pct: float = 0.0,
    moisture_equivalent_pct: float | None = None,
) -> dict[str, Any]:
    total = clay_pct + silt_pct + sand_pct
    if total > 0 and abs(total - 100.0) > 0.5:
        clay_pct = clay_pct * 100.0 / total
        silt_pct = silt_pct * 100.0 / total
        sand_pct = sand_pct * 100.0 / total
    return {
        "name": name,
        "top_cm": float(top_cm),
        "bottom_cm": float(bottom_cm),
        "om_pct": float(om_pct),
        "ph": float(ph),
        "cec": float(cec),
        "caco3_pct": float(caco3_pct),
        "clay_pct": float(clay_pct),
        "silt_pct": float(silt_pct),
        "sand_pct": float(sand_pct),
        "moisture_equivalent_pct": (
            float(moisture_equivalent_pct) if moisture_equivalent_pct is not None else None
        ),
    }


# Transcribed from the "DATOS ANALITICOS DEL PERFIL TIPICO" page of each PDF.
SERIES_PROFILES: dict[str, dict[str, Any]] = {
    "La Monona": {
        "document": SERIES_DOCUMENTS["La Monona"],
        "symbol": "LMon",
        "family": "fina, montmorillonítica, térmica",
        "taxonomy": "Peluderte árgico",
        "drainage": "Moderately well drained",
        "horizons": [
            _horizon("A1", 2, 12, 4.93, 5.8, 32.20, 34.86, 58.98, 6.16, 0.0, 32.93),
            _horizon("B21t", 17, 45, 2.14, 6.9, 39.01, 47.70, 48.88, 3.42, 0.0, 49.95),
            _horizon("B22tca", 55, 80, 1.24, 8.3, 37.81, 45.01, 51.69, 3.30, 2.6, 47.09),
            _horizon("B31ca", 90, 110, 0.52, 8.6, 35.85, 40.01, 55.11, 4.88, 7.7, 42.03),
            _horizon("B32ca", 118, 130, 0.45, 8.2, 35.72, 39.88, 56.56, 3.56, 7.2, 41.59),
            _horizon("Cca", 140, 150, 0.15, 8.6, 35.58, 39.94, 56.41, 3.65, 6.0, 41.84),
        ],
    },
    "Estancia Retiro": {
        "document": SERIES_DOCUMENTS["Estancia Retiro"],
        "symbol": "Re",
        "family": "limosa fina, mixta, térmica",
        "taxonomy": "Argiudol ácuico",
        "drainage": "Well drained",
        "horizons": [
            _horizon("Ap", 5, 17, 2.91, 6.4, 25.9, 23.10, 66.50, 10.40, 0.0, 26.77),
            _horizon("B1", 23, 30, 2.12, 6.5, 29.3, 34.60, 56.47, 8.94, 0.0, 31.87),
            _horizon("B21t", 33, 44, 1.28, 6.5, 33.5, 36.66, 55.99, 7.36, 0.0, 33.69),
            _horizon("B22t", 50, 63, 0.96, 6.9, 30.0, 30.02, 59.95, 10.03, 0.0, 29.49),
            _horizon("B23t", 70, 80, 0.67, 6.9, 29.2, 29.78, 59.89, 10.11, 0.0, 29.32),
            _horizon("B3", 88, 100, 0.51, 6.8, 26.1, 25.13, 61.32, 13.56, 0.0, 26.96),
            _horizon("C", 120, 125, 0.22, 6.8, 24.8, 17.44, 69.95, 12.93, 0.0, 23.43),
        ],
    },
    "Larroque": {
        "document": SERIES_DOCUMENTS["Larroque"],
        "symbol": "LRq",
        "family": "fina, montmorillonítica, térmica",
        "taxonomy": "Argiudol vértico",
        "drainage": "Moderately well drained",
        "horizons": [
            _horizon("A1", 2, 10, 3.68, 6.7, 26.56, 27.98, 48.24, 23.78, 0.0, 27.36),
            _horizon("B1", 11, 20, 3.68, 6.8, 31.14, 32.43, 48.42, 19.15, 0.0, 30.33),
            _horizon("B21t", 23, 40, 2.41, 7.1, 39.79, 41.90, 39.39, 18.71, 0.0, 39.17),
            _horizon("B22t", 50, 80, 1.12, 8.4, 36.37, 39.84, 41.77, 18.39, 3.43, 37.34),
            _horizon("B3ca", 90, 110, 0.89, 8.6, 29.04, 37.20, 46.76, 16.04, 18.09, 35.17),
            _horizon("Cca", 145, 160, 0.29, 8.7, 30.48, 36.41, 48.07, 15.52, 14.77, 34.79),
        ],
    },
    "La Laura": {
        "document": SERIES_DOCUMENTS["La Laura"],
        "symbol": "LLau",
        "family": "fina, montmorillonítica, térmica",
        "taxonomy": "Peluderte argiudólico",
        "drainage": "Moderately well drained",
        "horizons": [
            _horizon("A1", 5, 12, 7.51, 6.3, 34.32, 29.81, 61.16, 9.03, 0.0, 30.97),
            _horizon("B1", 15, 25, 7.06, 6.7, 37.24, 36.70, 55.94, 7.36, 0.0, 36.02),
            _horizon("B21t", 35, 50, 2.67, 7.6, 38.38, 42.77, 50.61, 6.62, 0.0, 44.38),
            _horizon("B22tca", 65, 85, 1.51, 8.3, 33.36, 45.25, 48.81, 5.94, 2.09, 43.15),
            _horizon("B3ca", 95, 110, 1.50, 8.6, 31.53, 43.22, 51.61, 5.17, 8.45, 41.71),
            _horizon("Cca", 135, 145, 0.52, 8.5, 32.44, 43.00, 52.29, 4.71, 9.92, 41.28),
        ],
    },
    "San Simón": {
        "document": SERIES_DOCUMENTS["San Simón"],
        "symbol": "SSim",
        "family": "fina, montmorillonítica, térmica",
        "taxonomy": "Peluderte argiudólico",
        "drainage": "Moderately well drained",
        "horizons": [
            _horizon("A1", 5, 17, 3.01, 7.2, 26.82, 29.53, 60.71, 9.76, 0.0, 31.94),
            _horizon("B21t", 25, 40, 3.29, 7.4, 39.25, 45.24, 48.51, 6.25, 0.0, 47.17),
            _horizon("B22t", 50, 70, 1.66, 8.4, 40.03, 42.51, 50.53, 6.96, 0.0, 44.97),
            _horizon("B23t", 78, 90, 1.59, 8.9, 39.77, 42.11, 51.65, 6.24, 5.5, 44.49),
            _horizon("B3ca", 100, 115, 0.76, 9.0, 30.48, 40.01, 54.86, 5.13, 15.70, 41.87),
            _horizon("Cca", 135, 145, 0.74, 8.9, 27.08, 39.02, 56.46, 4.52, 16.20, 38.68),
        ],
    },
}


def _usda_texture(clay_pct: float, sand_pct: float, silt_pct: float) -> str:
    clay, sand, silt = float(clay_pct), float(sand_pct), float(silt_pct)
    if clay >= 40.0:
        if silt >= 40.0:
            return "silty clay"
        if sand >= 45.0:
            return "sandy clay"
        return "clay"
    if clay >= 27.0:
        if sand >= 45.0:
            return "sandy clay loam"
        if silt >= 40.0:
            return "silty clay loam"
        return "clay loam"
    if clay >= 20.0:
        if sand >= 45.0:
            return "sandy loam"
        if silt >= 50.0:
            return "silt loam"
        return "loam"
    if clay >= 12.0:
        if silt >= 50.0:
            return "silt loam"
        if sand >= 45.0:
            return "sandy loam"
        return "loam"
    if silt >= 80.0:
        return "silt"
    if sand >= 70.0:
        return "loamy sand"
    if sand >= 50.0:
        return "sandy loam"
    return "loam"


def awc_cm_per_cm(clay_pct: float, sand_pct: float, silt_pct: float) -> float:
    """Texture-class available water capacity (cm/cm)."""

    return AWC_BY_TEXTURE[_usda_texture(clay_pct, sand_pct, silt_pct)]


def _texture_estimate(
    *,
    clay_pct: float,
    sand_pct: float,
    silt_pct: float,
    om_pct: float,
    ph: float,
    cec: float,
    top_cm: float,
) -> dict[str, float]:
    return {
        "claytotal_r": round(float(clay_pct), 2),
        "sandtotal_r": round(float(sand_pct), 2),
        "silttotal_r": round(float(silt_pct), 2),
        "om_r": round(float(om_pct), 2),
        "ph1to1h2o_r": round(float(ph), 2),
        "cec7_r": round(float(cec), 2),
        "awc_r": round(awc_cm_per_cm(clay_pct, sand_pct, silt_pct), 4),
        "dbthirdbar_r": 1.35 if top_cm < 30.0 else 1.45,
    }


def _wfs_query(params: dict[str, Any], *, timeout: float = 120.0, retries: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(WFS_URL, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - network retry loop
            last_error = exc
            if attempt == retries - 1:
                break
    raise RuntimeError(f"INTA WFS request failed: {last_error}") from last_error


def _bbox_param(field: Any, buffer_degrees: float = 0.01) -> str:
    minx, miny, maxx, maxy = field.bounds
    return f"{minx - buffer_degrees},{miny - buffer_degrees},{maxx + buffer_degrees},{maxy + buffer_degrees},EPSG:4326"


def query_map_units(
    field: Any,
    *,
    cache_dir: Path | None = None,
    force: bool = False,
    buffer_degrees: float = 0.01,
) -> gpd.GeoDataFrame:
    """Return the INTA soil map units intersecting ``field`` (EPSG:4326)."""

    cache_path = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_path = cache_dir / f"{SOURCE_NAME}_map_units.json"
    # Cache is keyed by the actual bbox so it is safe for a single field.
    if cache_path is not None:
        cache_path = cache_dir / f"{SOURCE_NAME}_bbox_{_bbox_hash(field, buffer_degrees)}.json"
        if cache_path.exists() and not force:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            payload = _wfs_query(
                {
                    "service": "WFS",
                    "version": "2.0.0",
                    "request": "GetFeature",
                    "typeName": LAYER,
                    "outputFormat": "application/json",
                    "srsName": "EPSG:4326",
                    "bbox": _bbox_param(field, buffer_degrees),
                    "count": 200,
                }
            )
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        payload = _wfs_query(
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": LAYER,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "bbox": _bbox_param(field, buffer_degrees),
                "count": 200,
            }
        )

    features = payload.get("features") or []
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    frame["geometry"] = frame.geometry.make_valid()
    return frame


def _bbox_hash(field: Any, buffer_degrees: float) -> str:
    minx, miny, maxx, maxy = field.bounds
    return f"{minx - buffer_degrees:.5f}_{miny - buffer_degrees:.5f}_{maxx + buffer_degrees:.5f}_{maxy + buffer_degrees:.5f}".replace(
        "-", "m"
    ).replace(".", "p")


def _components(props: dict[str, Any]) -> list[tuple[str, float]]:
    components: list[tuple[str, float]] = []
    for index in range(1, 8):
        series = props.get(f"serie_{index}")
        percentage = props.get(f"porc_{index}")
        if series and percentage is not None:
            components.append((str(series), float(percentage)))
    return components


def _series_profile(series: str) -> dict[str, Any] | None:
    return SERIES_PROFILES.get(series)


def _dominant_component(components: list[tuple[str, float]]) -> tuple[str, float]:
    if not components:
        return ("Unknown", 100.0)
    return max(components, key=lambda item: item[1])


def topsoil_properties(components: list[tuple[str, float]], max_depth_cm: float = 30.0) -> dict[str, Any]:
    """Component-weighted 0-30 cm properties for a map unit."""

    totals = {
        "claytotal_r": 0.0,
        "sandtotal_r": 0.0,
        "silttotal_r": 0.0,
        "om_r": 0.0,
        "ph1to1h2o_r": 0.0,
        "cec7_r": 0.0,
        "awc_r": 0.0,
    }
    weight_sum = 0.0
    for series, percentage in components:
        profile = _series_profile(series)
        if not profile:
            continue
        overlap_sum = 0.0
        local = {key: 0.0 for key in totals}
        for horizon in profile["horizons"]:
            top = max(0.0, float(horizon["top_cm"]))
            bottom = min(max_depth_cm, float(horizon["bottom_cm"]))
            thickness = max(0.0, bottom - top)
            if thickness <= 0:
                continue
            overlap_sum += thickness
            local["claytotal_r"] += float(horizon["clay_pct"]) * thickness
            local["sandtotal_r"] += float(horizon["sand_pct"]) * thickness
            local["silttotal_r"] += float(horizon["silt_pct"]) * thickness
            local["om_r"] += float(horizon["om_pct"]) * thickness
            local["ph1to1h2o_r"] += float(horizon["ph"]) * thickness
            local["cec7_r"] += float(horizon["cec"]) * thickness
            local["awc_r"] += (
                awc_cm_per_cm(
                    float(horizon["clay_pct"]),
                    float(horizon["sand_pct"]),
                    float(horizon["silt_pct"]),
                )
                * thickness
            )
        if overlap_sum <= 0:
            continue
        for key in totals:
            totals[key] += (local[key] / overlap_sum) * percentage
        weight_sum += percentage
    if weight_sum <= 0:
        return {}
    result = {key: round(value / weight_sum, 4) for key, value in totals.items()}
    result["dbthirdbar_r"] = 1.35
    return result


def _dominant_drainage(components: list[tuple[str, float]]) -> str:
    if not components:
        return "Unknown"
    series, _ = max(components, key=lambda item: item[1])
    profile = _series_profile(series)
    return str(profile.get("drainage", "Unknown")) if profile else "Unknown"


def field_polygon_intersections(
    fields: gpd.GeoDataFrame,
    *,
    cache_dir: Path | None = None,
    force: bool = False,
) -> gpd.GeoDataFrame:
    """Per-field clipped INTA map units with component and property columns."""

    fields_wgs84 = fields.to_crs("EPSG:4326")
    rows: list[gpd.GeoDataFrame] = []
    for _, field in fields_wgs84.iterrows():
        field_id = str(field.get("field_id", "")).strip()
        if not field_id:
            continue
        units = query_map_units(field.geometry, cache_dir=cache_dir, force=force)
        if units.empty:
            continue
        field_frame = gpd.GeoDataFrame(
            [{"field_id": field_id, "geometry": field.geometry}],
            geometry="geometry",
            crs="EPSG:4326",
        )
        try:
            clipped = gpd.overlay(units, field_frame, how="intersection")
        except Exception:  # noqa: BLE001 - invalid source geometry
            clipped = gpd.overlay(
                units.assign(geometry=units.geometry.buffer(0)),
                field_frame,
                how="intersection",
            )
        if clipped.empty:
            continue
        clipped = clipped[~clipped.geometry.is_empty].copy()
        if clipped.empty:
            continue
        metric_crs = field_frame.estimate_utm_crs()
        clipped_metric = clipped.to_crs(metric_crs)
        field_area = field_frame.to_crs(metric_crs).geometry.area.iloc[0]
        clipped["intersection_m2"] = clipped_metric.geometry.area
        clipped["field_area_m2"] = float(field_area)
        clipped["map_unit_share_pct"] = (
            clipped["intersection_m2"] / float(field_area) * 100.0
        ).round(3)
        clipped["field_id"] = field_id
        clipped["mukey"] = clipped["ogc_fid"].map(lambda value: f"AR-ER-{int(value)}")
        clipped["muname"] = clipped["nombre"].fillna(clipped["simb"]).astype(str)
        dominant = clipped.apply(lambda row: _dominant_component(_components(row.to_dict())), axis=1)
        clipped["compname"] = [item[0] for item in dominant]
        clipped["comppct_r"] = [round(float(item[1]), 2) for item in dominant]
        clipped["soil_source"] = SOURCE_NAME
        property_rows = clipped.apply(
            lambda row: topsoil_properties(_components(row.to_dict())), axis=1
        )
        property_frame = pd.DataFrame(list(property_rows))
        for column in property_frame.columns:
            clipped[column] = property_frame[column].values
        clipped["drainagecl"] = clipped.apply(
            lambda row: _dominant_drainage(_components(row.to_dict())), axis=1
        )
        rows.append(clipped)
    if not rows:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    result = gpd.GeoDataFrame(pd.concat(rows, ignore_index=True), geometry="geometry", crs="EPSG:4326")
    return result


def download_soil_argentina(
    fields: gpd.GeoDataFrame,
    *,
    cache_dir: Path | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return SSURGO-schema horizon rows for Argentine fields."""

    polygons = field_polygon_intersections(fields, cache_dir=cache_dir, force=force)
    if polygons.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, unit in polygons.iterrows():
        props = unit.to_dict()
        components = _components(props)
        map_unit_share = float(props.get("map_unit_share_pct", 0.0)) / 100.0
        for series, percentage in components:
            profile = _series_profile(series)
            if not profile:
                continue
            component_share = map_unit_share * percentage / 100.0
            for horizon in profile["horizons"]:
                top = float(horizon["top_cm"])
                metrics = _texture_estimate(
                    clay_pct=horizon["clay_pct"],
                    sand_pct=horizon["sand_pct"],
                    silt_pct=horizon["silt_pct"],
                    om_pct=horizon["om_pct"],
                    ph=horizon["ph"],
                    cec=horizon["cec"],
                    top_cm=top,
                )
                rows.append(
                    {
                        "field_id": str(props["field_id"]),
                        "mukey": str(props["mukey"]),
                        "muname": str(props["muname"]),
                        "compname": series,
                        "comppct_r": round(float(percentage), 2),
                        "drainagecl": str(profile.get("drainage", "Unknown")),
                        "hzdept_r": top,
                        "hzdepb_r": float(horizon["bottom_cm"]),
                        "om_r": metrics["om_r"],
                        "ph1to1h2o_r": metrics["ph1to1h2o_r"],
                        "awc_r": metrics["awc_r"],
                        "claytotal_r": metrics["claytotal_r"],
                        "sandtotal_r": metrics["sandtotal_r"],
                        "silttotal_r": metrics["silttotal_r"],
                        "dbthirdbar_r": metrics["dbthirdbar_r"],
                        "cec7_r": metrics["cec7_r"],
                        "caco3_pct": float(horizon.get("caco3_pct", 0.0)),
                        "soil_area_share": round(component_share, 6),
                        "soil_source": SOURCE_NAME,
                    }
                )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fields_with_survey_coverage(
    fields: gpd.GeoDataFrame,
    *,
    cache_dir: Path | None = None,
) -> list[str]:
    """Return the field IDs that intersect the INTA Entre Ríos soil layer."""

    fields_wgs84 = fields.to_crs("EPSG:4326")
    covered: list[str] = []
    for _, field in fields_wgs84.iterrows():
        field_id = str(field.get("field_id", "")).strip()
        if not field_id:
            continue
        try:
            units = query_map_units(field.geometry, cache_dir=cache_dir)
        except Exception:  # noqa: BLE001 - coverage probe should not fail the run
            continue
        if units.empty:
            continue
        if bool(units.geometry.intersects(field.geometry).any()):
            covered.append(field_id)
    return covered


def provenance() -> dict[str, Any]:
    """Machine-readable provenance for the provider outputs."""

    return {
        "source": SOURCE_NAME,
        "dataset_page": DATASET_PAGE,
        "wfs_url": WFS_URL,
        "layer": LAYER,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "accessed_at": ACCESS_DATE,
        "series_documents": SERIES_DOCUMENTS,
        "series_profiles": {
            name: {
                "document": profile["document"],
                "symbol": profile["symbol"],
                "family": profile["family"],
                "taxonomy": profile["taxonomy"],
                "drainage": profile["drainage"],
                "horizon_count": len(profile["horizons"]),
            }
            for name, profile in SERIES_PROFILES.items()
        },
        "awc_method": "USDA texture-class lookup (cm/cm); measured moisture equivalent retained for audit",
        "written_at": datetime.now(UTC).isoformat(),
    }


def write_provenance(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(provenance(), indent=2, ensure_ascii=False), encoding="utf-8")
    return target
