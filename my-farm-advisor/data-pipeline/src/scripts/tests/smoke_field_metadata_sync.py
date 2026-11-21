#!/usr/bin/env python3
"""Offline smoke: canonical field metadata identity and boundary sync.

Regression guards for the Assignment 2 defects:

* ``field.json.field_id`` used to be an uppercase scaffold value
  (``IL_R1``) that no other artifact used, so joining on it silently
  dropped rows.  The canonical id is now the lowercase ``field_slug``.
* ``field.json`` was a bare scaffold (no state/county/area).  Stable
  attributes are now copied from the authoritative farm boundary file by
  ``sync_field_metadata_from_boundary`` while ``crop`` / ``crop_name`` stay
  the human override slot.

Each case runs in a subprocess because ``reporting_bootstrap`` resolves
``DATA_PIPELINE_DATA_ROOT`` at import time.

Run: DATA_PIPELINE_DATA_ROOT is set per case; no network, no installs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


class SmokeFailure(AssertionError):
    """Raised when a smoke check fails."""


def _assert_equal(actual: object, expected: object, context: object) -> None:
    if actual != expected:
        raise SmokeFailure(f"expected {expected!r}, got {actual!r}; context={context!r}")


# One subprocess that builds a synthetic farm, then scaffolds + syncs it.
_SYNC_CASE = r"""
import json
from pathlib import Path

from reporting_bootstrap import (
    ensure_canonical_data_tree,
    farm_root,
    sync_field_metadata_from_boundary,
)

grower, farm = "g", "f"
root = farm_root(grower, farm)
(root / "manifests").mkdir(parents=True, exist_ok=True)
(root / "boundary").mkdir(parents=True, exist_ok=True)
(root / "manifests" / "field-inventory.csv").write_text(
    "field_id,field_slug\nus-1,us-1\nar-9,ar-9\n", encoding="utf-8"
)
ensure_canonical_data_tree(
    grower_slug=grower,
    farm_slug=farm,
    inventory_path=root / "manifests" / "field-inventory.csv",
)

# Manual crop override written before the sync must survive untouched.
override_path = root / "fields" / "us-1" / "field.json"
payload = json.loads(override_path.read_text(encoding="utf-8"))
payload["crop"] = "Corn"
payload["crop_name"] = "Corn"
override_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

boundary = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-88.0, 41.0], [-88.0, 41.01], [-87.99, 41.01], [-88.0, 41.0]]],
            },
            "properties": {
                "field_id": "us-1",
                "country": "US",
                "state": "Illinois",
                "county": "Iroquois",
                "area_acres": 100.0,
                "area_ha_est": 40.47,
                "source": "usda_csb_fiboa",
                "crop": "Corn",
            },
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-58.8, -33.1], [-58.8, -33.09], [-58.79, -33.09], [-58.8, -33.1]]],
            },
            "properties": {
                "field_id": "ar-9",
                "country": "AR",
                "state": "Entre Ríos",
                "area_acres": 247.1053814671653,
                "source": "osm_farmland",
                "crop": "",
            },
        },
    ],
}
boundary_path = root / "boundary" / "field_boundaries.geojson"
boundary_path.write_text(json.dumps(boundary), encoding="utf-8")

changes = sync_field_metadata_from_boundary(
    grower_slug=grower, farm_slug=farm, boundary_path=boundary_path
)
again = sync_field_metadata_from_boundary(
    grower_slug=grower, farm_slug=farm, boundary_path=boundary_path
)

result = {
    "changes": sorted(changes),
    "second_pass": sorted(again),
    "us": json.loads((root / "fields" / "us-1" / "field.json").read_text(encoding="utf-8")),
    "ar": json.loads((root / "fields" / "ar-9" / "field.json").read_text(encoding="utf-8")),
}
print(json.dumps(result))
"""


def check_sync_contract() -> None:
    """Assert the sync result by re-running the case in-process for parsing."""

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        env = {
            **os.environ,
            "DATA_PIPELINE_DATA_ROOT": str(root),
            "PYTHONPATH": str(SCRIPTS_DIR),
        }
        result = subprocess.run(
            [sys.executable, "-c", _SYNC_CASE],
            cwd=SCRIPTS_DIR,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise SmokeFailure(f"sync failed:\n{result.stdout}\n{result.stderr}")
        data = json.loads(result.stdout.strip().splitlines()[-1])
        us, ar = data["us"], data["ar"]

        _assert_equal(us["field_id"], "us-1", "uppercase scaffold id fixed")
        _assert_equal(us["state"], "Illinois", "state from boundary")
        _assert_equal(us["country"], "US", "country from boundary")
        _assert_equal(us["county"], "Iroquois", "county from boundary")
        _assert_equal(us["area_acres"], 100.0, "acres from boundary")
        _assert_equal(us["area_ha"], 40.47, "hectares from boundary")
        _assert_equal(us["source"], "usda_csb_fiboa", "source from boundary")
        _assert_equal(us["crop"], "Corn", "crop override preserved")
        _assert_equal(us["crop_name"], "Corn", "crop_name override preserved")

        _assert_equal(ar["field_id"], "ar-9", "id comes from boundary")
        _assert_equal(ar["state"], "Entre Ríos", "AR state from boundary")
        _assert_equal("county" in ar, False, "absent county not invented")
        _assert_equal(ar["area_ha"], 100.0, "hectares derived from acres")
        _assert_equal("crop" in ar, False, "empty boundary crop writes nothing")

        _assert_equal(data["changes"], ["ar-9", "us-1"], "first pass writes both")
        _assert_equal(data["second_pass"], [], "second pass is idempotent")


def main() -> int:
    checks = [
        ("field_id is the lowercase slug and boundary sync populates metadata", check_sync_contract),
    ]
    for label, check in checks:
        check()
        print(f"PASS: {label}")
    print(f"PASS: {len(checks)} field-metadata smoke checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
