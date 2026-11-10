"""Resolve administrative region labels used by shared-data joins.

Field boundaries come from several providers (USDA CSB, GPKG imports, OSM
queries).  Not all of them carry a ``state_fips`` column, but downstream
steps need the FIPS code to pick the matching CDL raster.  This module keeps
one resolver so CDL downloads and NDVI cards never disagree — or silently
fall back to the Iowa raster (``19``).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

try:  # Support both package-style and top-level "lib" imports.
    from .paths import shared_geoadmin_states_dir
except ImportError:  # pragma: no cover - script import path
    from paths import shared_geoadmin_states_dir


# Compact USPS/FIPS table used when the shared geoadmin layer is unavailable.
# Format: <postal code> <FIPS> <state name>
_US_STATE_TABLE = """
AL 01 Alabama
AK 02 Alaska
AZ 04 Arizona
AR 05 Arkansas
CA 06 California
CO 08 Colorado
CT 09 Connecticut
DE 10 Delaware
DC 11 District of Columbia
FL 12 Florida
GA 13 Georgia
HI 15 Hawaii
ID 16 Idaho
IL 17 Illinois
IN 18 Indiana
IA 19 Iowa
KS 20 Kansas
KY 21 Kentucky
LA 22 Louisiana
ME 23 Maine
MD 24 Maryland
MA 25 Massachusetts
MI 26 Michigan
MN 27 Minnesota
MS 28 Mississippi
MO 29 Missouri
MT 30 Montana
NE 31 Nebraska
NV 32 Nevada
NH 33 New Hampshire
NJ 34 New Jersey
NM 35 New Mexico
NY 36 New York
NC 37 North Carolina
ND 38 North Dakota
OH 39 Ohio
OK 40 Oklahoma
OR 41 Oregon
PA 42 Pennsylvania
RI 44 Rhode Island
SC 45 South Carolina
SD 46 South Dakota
TN 47 Tennessee
TX 48 Texas
UT 49 Utah
VT 50 Vermont
VA 51 Virginia
WA 53 Washington
WV 54 West Virginia
WI 55 Wisconsin
WY 56 Wyoming
AS 60 American Samoa
GU 66 Guam
MP 69 Northern Mariana Islands
PR 72 Puerto Rico
VI 78 Virgin Islands
"""

_STATE_FIPS_CACHE: dict[str, str] | None = None


def _static_state_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for line in _US_STATE_TABLE.strip().splitlines():
        code, fips, name = line.split(" ", 2)
        lookup[code.lower()] = fips
        lookup[name.lower()] = fips
        lookup[fips] = fips
    return lookup


def _shared_state_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    states_dir = shared_geoadmin_states_dir()
    for filename in ("states_usa.geojson", "states_usa.parquet"):
        path: Path = states_dir / filename
        if not path.exists():
            continue
        try:
            states = gpd.read_file(path)
        except Exception:
            continue
        if "state_fips" not in states.columns:
            continue
        for _, row in states.iterrows():
            fips = str(row.get("state_fips", "")).strip().zfill(2)
            if not fips:
                continue
            lookup[fips] = fips
            for key in ("state_code", "state_name"):
                value = str(row.get(key, "")).strip().lower()
                if value:
                    lookup[value] = fips
        break
    return lookup


def state_fips_lookup() -> dict[str, str]:
    """Map state name, USPS code, or FIPS string to a zero-padded FIPS code."""

    global _STATE_FIPS_CACHE
    if _STATE_FIPS_CACHE is None:
        lookup = _static_state_lookup()
        # The shared geoadmin layer wins when present so metadata fixes there
        # propagate without touching this module.
        lookup.update(_shared_state_lookup())
        _STATE_FIPS_CACHE = lookup
    return _STATE_FIPS_CACHE


def resolve_state_fips(value: object) -> str | None:
    """Resolve a single state label to a two-digit FIPS code, or ``None``."""

    if value is None:
        return None
    key = str(value).strip()
    if not key or key.lower() in {"nan", "none"}:
        return None
    if key.isdigit():
        return key.zfill(2)
    return state_fips_lookup().get(key.lower())
