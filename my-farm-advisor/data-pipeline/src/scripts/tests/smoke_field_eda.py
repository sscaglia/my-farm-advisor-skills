#!/usr/bin/env python3
"""Offline smoke: field-comparison EDA invariants on a synthetic runtime.

The four rules this guards are the ones that silently corrupt every number
downstream, so each gets a deliberately small fixture that fails loudly:

1. **Weather de-duplication.**  Two fields that share one grid cell write two
   identical daily series.  The EDA must resolve them to *one* series and sum
   a year once (365 mm, not 730 mm).  Argentina gets two distinct series so the
   series count itself is exercised.
2. **Crop class provenance.**  The boundaries carry ``crop = "Unknown"`` (as
   Argentine OSM boundaries do); the class must come from the CDL/MNC table.
3. **Split threshold.**  A field-year whose dominant class holds 55 % is split;
   one at 100 % is not.
4. **Land status survives.**  MNC's ``agricultural_share`` / ``cropland_status``
   are per field-year attributes and must not be dropped by the dominant-class
   aggregation.

The runtime is built in a temp directory and the real runtime wrapper is run in
a subprocess (``reporting_bootstrap`` resolves ``DATA_PIPELINE_DATA_ROOT`` at
import time).  ``--no-maps`` keeps it offline: no tiles, no network.

Run with the runtime virtualenv:

    ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python \
        my-farm-advisor/data-pipeline/src/scripts/tests/smoke_field_eda.py
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
WRAPPER = SCRIPTS_DIR / "eda" / "run_field_comparison.py"

YEARS = (2022, 2023)

# Squares and rectangles, all distinct areas, so the rank tests have no ties.
# (field_id, state, country, lon0, lat0, width_deg, height_deg)
FIELDS = {
    "us": [
        ("us-1", "Illinois", "US", -88.60, 40.00, 0.0100, 0.0100),
        ("us-2", "Illinois", "US", -88.55, 40.02, 0.0250, 0.0070),
    ],
    "ar": [
        ("ar-1", "Entre Ríos", "AR", -58.60, -32.00, 0.0090, 0.0090),
        ("ar-2", "Entre Ríos", "AR", -58.56, -32.04, 0.0060, 0.0100),
    ],
}

WEATHER_TEMPLATE = {
    "T2M": 20.0,
    "T2M_MAX": 28.0,
    "T2M_MIN": 12.0,
    "ALLSKY_SFC_SW_DWN": 18.0,
    "RH2M": 60.0,
    "WS10M": 3.0,
}

# US fields share one series (same daily values); AR fields are distinct.
PRECIP_BY_FIELD = {
    "us-1": 1.0,
    "us-2": 1.0,
    "ar-1": 2.0,
    "ar-2": 3.0,
}


class SmokeFailure(AssertionError):
    """Raised when a smoke check fails."""


def _assert_equal(actual: object, expected: object, context: object) -> None:
    if actual != expected:
        raise SmokeFailure(f"expected {expected!r}, got {actual!r}; context={context!r}")


def _assert_close(actual: float, expected: float, context: object) -> None:
    if abs(float(actual) - float(expected)) > 1e-6:
        raise SmokeFailure(f"expected {expected}, got {actual}; context={context!r}")


def _write_boundary(path: Path, grower_code: str) -> None:
    features = []
    for field_id, state, country, lon0, lat0, width, height in FIELDS[grower_code]:
        ring = [
            [lon0, lat0],
            [lon0 + width, lat0],
            [lon0 + width, lat0 + height],
            [lon0, lat0 + height],
            [lon0, lat0],
        ]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "field_id": field_id,
                    "state": state,
                    "country": country,
                    # A human/OSM hint that is wrong on purpose: the EDA must
                    # read crop class from the table, never from here.
                    "crop": "Unknown",
                    "crop_name": "Unknown",
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )


def _write_crop_csv(path: Path, rows: list[dict[str, object]], code: str) -> None:
    fieldnames = ["field_id", "year", "crop_name", "pct"]
    if code == "ar":
        fieldnames = [
            "field_id",
            "year",
            "season",
            "crop_name",
            "pct",
            "agricultural_share",
            "cropland_status",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_weather(path: Path, code: str) -> None:
    field_ids = [row[0] for row in FIELDS[code]]
    start = date(YEARS[0], 1, 1)
    end = date(YEARS[-1], 12, 31)
    days = (end - start).days + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field_id", "date", *WEATHER_TEMPLATE, "PRECTOTCORR"])
        for field_id in field_ids:
            precip = PRECIP_BY_FIELD[field_id]
            for offset in range(days):
                day = start + timedelta(days=offset)
                writer.writerow(
                    [
                        field_id,
                        day.isoformat(),
                        *[WEATHER_TEMPLATE[column] for column in WEATHER_TEMPLATE],
                        precip,
                    ]
                )


def _build_runtime(root: Path) -> None:
    pipeline = root / "data-pipeline"
    # ensure_runtime_libs() only needs the directory to exist; --no-maps never
    # imports lib.field_frame, so nothing has to live in it.
    (pipeline / "src" / "scripts").mkdir(parents=True, exist_ok=True)

    for code, grower_slug in (("us", "us-grower"), ("ar", "ar-grower")):
        farm = pipeline / "growers" / grower_slug / "farms" / f"{code}-farm"
        _write_boundary(farm / "boundary" / "field_boundaries.geojson", code)
        tables = farm / "derived" / "tables"

        if code == "us":
            years = {
                2022: [
                    {"field_id": "us-1", "year": 2022, "crop_name": "Corn", "pct": 100},
                    {"field_id": "us-2", "year": 2022, "crop_name": "Soybeans", "pct": 100},
                ],
                2023: [
                    {"field_id": "us-1", "year": 2023, "crop_name": "Soybeans", "pct": 100},
                    {"field_id": "us-2", "year": 2023, "crop_name": "Corn", "pct": 100},
                ],
            }
        else:
            years = {
                2022: [
                    {
                        "field_id": "ar-1", "year": 2022, "season": "summer",
                        "crop_name": "Corn", "pct": 100,
                        "agricultural_share": 1.0, "cropland_status": "cropland",
                    },
                    {
                        "field_id": "ar-2", "year": 2022, "season": "summer",
                        "crop_name": "Non-agricultural", "pct": 100,
                        "agricultural_share": 0.0, "cropland_status": "non-cropland",
                    },
                ],
                2023: [
                    # 55 / 45: dominant class below the 60 % split threshold.
                    {
                        "field_id": "ar-1", "year": 2023, "season": "summer",
                        "crop_name": "Corn", "pct": 55,
                        "agricultural_share": 0.96, "cropland_status": "cropland",
                    },
                    {
                        "field_id": "ar-1", "year": 2023, "season": "summer",
                        "crop_name": "Soybeans", "pct": 45,
                        "agricultural_share": 0.96, "cropland_status": "cropland",
                    },
                    {
                        "field_id": "ar-2", "year": 2023, "season": "summer",
                        "crop_name": "Non-agricultural", "pct": 100,
                        "agricultural_share": 0.0, "cropland_status": "non-cropland",
                    },
                ],
            }

        for year, rows in years.items():
            _write_crop_csv(tables / f"{code}_{year}_cdl.csv", rows, code)
        _write_weather(tables / f"{code}_weather_{YEARS[0]}_{YEARS[-1]}.csv", code)


def _run_cli(root: Path, out: Path) -> None:
    env = dict(os.environ)
    env["DATA_PIPELINE_DATA_ROOT"] = str(root)
    env.pop("DATA_PIPELINE_VENV_DIR", None)
    result = subprocess.run(
        [sys.executable, str(WRAPPER), "--out", str(out), "--no-maps"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise SmokeFailure(
            "field-comparison CLI failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SmokeFailure(f"expected artifact missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rows(rows: list[dict[str, str]], **match: str) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if all(str(row.get(key)) == str(value) for key, value in match.items())
    ]


def _check_artifacts(out: Path) -> None:
    figures = sorted(path.relative_to(out).as_posix() for path in out.rglob("*.png"))
    tables = sorted(path.relative_to(out).as_posix() for path in out.rglob("*.csv"))
    _assert_equal(len(figures), 6, f"--no-maps figure set: {figures}")
    _assert_equal(len(tables), 12, f"table set: {tables}")
    _assert_equal(
        (out / "maps").exists(), False, "--no-maps must not write a maps/ tree"
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    _assert_equal(manifest["skill"], "eda-field-comparison", "manifest skill name")
    _assert_equal(len(manifest["growers"]), 2, "manifest grower count")
    _assert_equal(manifest["years"], [2022, 2023], "manifest years")
    _assert_equal(
        manifest["thresholds"]["split_dominance_pct"], 60.0, "split threshold"
    )
    _assert_equal(manifest["warnings"], [], "synthetic runtime must be warning-free")


def _check_weather(out: Path) -> None:
    field_series = _read_csv(out / "weather" / "weather_series.csv")
    by_grower: dict[str, set[str]] = {}
    for row in field_series:
        by_grower.setdefault(row["grower"], set()).add(row["series_id"])

    _assert_equal(len(by_grower["us"]), 1, "US fields share one weather series")
    _assert_equal(len(by_grower["ar"]), 2, "AR fields have two distinct series")
    _assert_equal(
        sum(len(ids) for ids in by_grower.values()), 3, "total distinct series"
    )
    for row in field_series:
        _assert_equal(int(row["days"]), 730, f"{row['field_id']} daily coverage")

    annual = _read_csv(out / "weather" / "weather_annual_by_series.csv")
    for year in YEARS:
        us = _rows(annual, series_id="us-S1", year=str(year))
        _assert_equal(len(us), 1, f"one US series row for {year}")
        # 1.0 mm/day x 365 days. A per-field sum would write 730 here.
        _assert_close(us[0]["precip_mm"], 365.0, f"us-S1 {year} precip de-duplicated")
        _assert_close(us[0]["gdd10"], 3650.0, f"us-S1 {year} GDD10 de-duplicated")

        ar1 = _rows(annual, series_id="ar-S1", year=str(year))
        ar2 = _rows(annual, series_id="ar-S2", year=str(year))
        _assert_close(ar1[0]["precip_mm"], 730.0, f"ar-S1 {year} precip")
        _assert_close(ar2[0]["precip_mm"], 1095.0, f"ar-S2 {year} precip")

    audit = _read_csv(out / "weather" / "weather_audit.csv")
    _assert_equal(
        _rows(audit, grower="us")[0]["series_count"], "1", "US audit series count"
    )
    _assert_equal(
        _rows(audit, grower="ar")[0]["series_count"], "2", "AR audit series count"
    )


def _check_cropland(out: Path) -> None:
    sequence = _read_csv(out / "cropland" / "field_crop_sequence.csv")

    us_2022 = _rows(sequence, field_id="us-1", year="2022")[0]
    # The boundary says "Unknown"; the table says Corn. The table wins.
    _assert_equal(us_2022["crop_name"], "Corn", "crop class from table, not boundary")
    _assert_equal(us_2022["is_split"], "False", "100 % dominant is not split")
    _assert_close(us_2022["purity_pct"], 100.0, "us-1 2022 purity")

    ar_2023 = _rows(sequence, field_id="ar-1", year="2023")[0]
    _assert_equal(ar_2023["crop_name"], "Corn", "ar-1 2023 dominant class")
    _assert_equal(ar_2023["is_split"], "True", "55 % dominant is split")
    _assert_close(ar_2023["purity_pct"], 55.0, "ar-1 2023 purity")
    _assert_close(ar_2023["agricultural_share"], 0.96, "AR agricultural share kept")
    _assert_equal(ar_2023["cropland_status"], "cropland", "AR cropland status kept")

    ar_2022 = _rows(sequence, field_id="ar-1", year="2022")[0]
    _assert_close(ar_2022["agricultural_share"], 1.0, "AR share preserved per year")

    pasture = _rows(sequence, field_id="ar-2", year="2022")[0]
    _assert_equal(
        pasture["is_managed_crop"], "False", "Non-agricultural is land cover, not a crop"
    )

    # US rows have no land-status attribute; the columns stay present and empty.
    _assert_equal(us_2022["agricultural_share"], "", "US has no agricultural_share")

    composition = _read_csv(out / "cropland" / "crop_composition.csv")
    _assert_equal(
        {row["grower"] for row in composition}, {"us", "ar"}, "composition growers"
    )

    transitions = _read_csv(out / "cropland" / "crop_transitions.csv")
    us_changes = _rows(transitions, grower="us")
    _assert_equal(
        sorted((row["from_crop"], row["to_crop"]) for row in us_changes),
        [("Corn", "Soybeans"), ("Soybeans", "Corn")],
        "US rotation transitions",
    )


def _check_summary(out: Path) -> None:
    summary = _read_csv(out / "cross_grower_summary.csv")
    _assert_equal({row["grower"] for row in summary}, {"us", "ar"}, "summary growers")
    us = _rows(summary, grower="us")[0]
    ar = _rows(summary, grower="ar")[0]
    _assert_equal(us["weather_series"], "1", "US summary series count")
    _assert_equal(ar["weather_series"], "2", "AR summary series count")
    _assert_equal(us["fields"], "2", "US summary field count")
    _assert_equal(ar["split_field_years"], "1", "AR summary split field-years")
    _assert_equal(us["split_field_years"], "0", "US summary split field-years")


def main() -> int:
    if not WRAPPER.exists():
        raise SmokeFailure(f"runtime wrapper not found: {WRAPPER}")
    with tempfile.TemporaryDirectory(prefix="field-eda-") as tmp:
        root = Path(tmp).resolve()
        out = root / "artifacts"
        _build_runtime(root)
        _run_cli(root, out)
        _check_artifacts(out)
        _check_weather(out)
        _check_cropland(out)
        _check_summary(out)
    print("PASS: field-comparison EDA smoke (artifacts, series, crop, split)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
