#!/usr/bin/env python3
"""Offline smoke: MNC crop semantics and rotation confidence.

Regression guards for the Assignment 2 defects found when inspecting the
analysis-ready Argentina layers:

* MNC class 22 (``No agrícola``) is pasture / natural vegetation, not a
  catch-all "Other" crop.  Translating it to ``Other`` made grazing land look
  like an unidentified crop.
* A parcel whose dominant class is non-crop in every year must not report a
  high-confidence crop rotation; it gets ``rotation_confidence=not_applicable``.
* Cropland status is persisted per row so EDA can exclude non-agricultural
  parcels instead of re-deriving it from class labels.

Runs in a subprocess because ``mnc_reporting`` imports ``lib.paths``, which
resolves ``DATA_PIPELINE_DATA_ROOT`` at import time.

Run: no network, no installs.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SKILL_SRC = Path(__file__).resolve().parents[4] / "soil" / "cdl-cropland" / "src"


class SmokeFailure(AssertionError):
    """Raised when a smoke check fails."""


_CHECK = r"""
import sys
import pandas as pd

sys.path.insert(0, SKILL_SRC)
import cdl_reporting
import mnc_reporting

# --- label mapping -------------------------------------------------------
names = mnc_reporting.MNC_TO_CDL_NAME
assert names["No agrícola"] == "Non-agricultural", names["No agrícola"]
assert names["Otros cultivos"] == "Other crops", names["Otros cultivos"]
assert names["No agrícola"] != "Other"

# --- cropland status -----------------------------------------------------
status = mnc_reporting._cropland_status
assert status(0.92) == "cropland"
assert status(0.35) == "partial"
assert status(0.08) == "non_agricultural"

# --- rotation guard ------------------------------------------------------
pasture = ["Non-agricultural"] * 5
outlook = cdl_reporting.build_crop_rotation_outlook(pasture)
assert outlook["rotation_confidence"] == "not_applicable", outlook
assert outlook["predicted_next_crop"] == "Not applicable"

# Forecast from cropped years only: trailing/leading pasture is not a crop.
mixed = ["Non-agricultural", "Non-agricultural", "Soybeans", "Corn", "Soybeans"]
outlook = cdl_reporting.build_crop_rotation_outlook(mixed)
assert outlook["predicted_next_crop"] != "Non-agricultural", outlook
assert outlook["rotation_confidence"] in {"low", "medium", "high"}, outlook

# --- summary columns -----------------------------------------------------
rows = []
for field_id, sequence in {
    "pasture": ["Non-agricultural"] * 5,
    "rotation": ["Soybeans", "Corn", "Soybeans", "Corn", "Soybeans"],
    "converted": ["Non-agricultural", "Non-agricultural", "Soybeans", "Soybeans", "Corn"],
}.items():
    for year, crop in zip(range(2021, 2026), sequence):
        rows.append({"field_id": field_id, "year": year, "crop_name": crop, "pct": 100.0})
summary = cdl_reporting.summarize_crop_history(pd.DataFrame(rows))
by_field = summary.set_index("field_id")
assert by_field.loc["pasture", "rotation_confidence"] == "not_applicable"
assert by_field.loc["pasture", "cropland_years"] == 0
assert by_field.loc["pasture", "non_agricultural_years"] == 5
assert by_field.loc["rotation", "rotation_confidence"] in {"medium", "high"}
assert by_field.loc["rotation", "non_agricultural_years"] == 0
assert by_field.loc["converted", "cropland_years"] == 3
assert by_field.loc["converted", "non_agricultural_years"] == 2
assert by_field.loc["converted", "current_crop"] == "Corn"
print("PASS: MNC label, cropland status, rotation guard and summary columns")
"""


def check_mnc_semantics() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "DATA_PIPELINE_DATA_ROOT": str(Path(tmp)),
            "PYTHONPATH": str(SCRIPTS_DIR),
        }
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"SKILL_SRC = {str(SKILL_SRC)!r}\n" + _CHECK,
            ],
            cwd=SCRIPTS_DIR,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise SmokeFailure(f"MNC semantics failed:\n{result.stdout}\n{result.stderr}")
        print(result.stdout.strip().splitlines()[-1])


def main() -> int:
    check_mnc_semantics()
    print("PASS: 1 MNC crop-semantics smoke check completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
