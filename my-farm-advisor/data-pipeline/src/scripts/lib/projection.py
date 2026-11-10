"""Projection helpers for field-level reporting.

The reporting stack used to hardcode northern-hemisphere UTM zones
(``EPSG:32615`` / ``EPSG:32616``).  That silently distorts areas, headland
widths, and map extents for southern-hemisphere farms.  Use
:func:`utm_epsg` (or :func:`utm_crs_for_geometry`) instead.
"""

from __future__ import annotations

from typing import Any

__all__ = ["utm_epsg", "utm_crs_for_geometry"]


def utm_epsg(lon: float, lat: float) -> str:
    """Return the WGS84 UTM CRS string for a longitude/latitude pair.

    ``lon``/``lat`` are decimal degrees.  Zone 1 spans 180°W to 174°W and
    zone 60 spans 174°E to 180°E.  Southern latitudes use the ``327xx``
    family, northern latitudes the ``326xx`` family.
    """

    zone = int((float(lon) + 180.0) // 6.0) + 1
    zone = min(60, max(1, zone))
    base = 32600 if float(lat) >= 0.0 else 32700
    return f"EPSG:{base + zone}"


def utm_crs_for_geometry(geometry: Any) -> str:
    """Return the UTM CRS string for a Shapely geometry's centroid.

    The geometry must already be in EPSG:4326.
    """

    centroid = geometry.centroid
    return utm_epsg(float(centroid.x), float(centroid.y))
