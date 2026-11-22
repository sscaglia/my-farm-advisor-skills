#!/usr/bin/env python3
"""Offline smoke: canonical tree scaffolding must not rename an existing farm.

Regression guard for the Assignment 2 defect where every pipeline leg called
``ensure_canonical_data_tree(grower, farm)`` without a farm name and the
module default (``AG_FARM_NAME`` / "Default Farm") overwrote the name already
recorded in ``farm.json``. Each case runs in a subprocess because
``reporting_bootstrap`` resolves ``DATA_PIPELINE_DATA_ROOT`` at import time.

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


def _scaffold(root: Path, code: str, extra_env: dict[str, str] | None = None) -> dict:
    """Run one ensure_canonical_data_tree call inside a throwaway data root."""
    env = {
        **os.environ,
        "DATA_PIPELINE_DATA_ROOT": str(root),
        "PYTHONPATH": str(SCRIPTS_DIR),
        **(extra_env or {}),
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=SCRIPTS_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise SmokeFailure(
            f"ensure_canonical_data_tree failed: {result.stdout}\n{result.stderr}"
        )
    farm_json = root / "data-pipeline" / "growers" / "g" / "farms" / "f" / "farm.json"
    return json.loads(farm_json.read_text(encoding="utf-8"))


_CALL = (
    "import sys; sys.path.insert(0, {scripts!r});"
    "from reporting_bootstrap import ensure_canonical_data_tree as ensure;"
    "ensure({args})"
)


def _call(*args: str) -> str:
    return _CALL.format(scripts=str(SCRIPTS_DIR), args=", ".join(args))


def check_nameless_call_preserves_existing_name() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meta = _scaffold(
            root,
            _call("'g'", "'f'", "'Hamilton County Farm'", "country='US'", "state='Nebraska'"),
        )
        _assert_equal(meta["display_name"], "Hamilton County Farm", "seeded name")

        meta = _scaffold(root, _call("'g'", "'f'"))
        _assert_equal(meta["display_name"], "Hamilton County Farm", "nameless repair call")
        _assert_equal(meta["state"], "Nebraska", "state preserved")
        _assert_equal(meta["country"], "US", "country preserved")


def check_explicit_name_still_wins() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _scaffold(root, _call("'g'", "'f'", "'First Name'"))
        meta = _scaffold(root, _call("'g'", "'f'", "'Second Name'"))
        _assert_equal(meta["display_name"], "Second Name", "explicit rename")


def check_fresh_farm_gets_default_name() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        meta = _scaffold(Path(tmp), _call("'g'", "'f'"))
        _assert_equal(meta["display_name"], "Default Farm", "fresh farm fallback")


def check_env_default_does_not_rename_existing_farm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _scaffold(root, _call("'g'", "'f'", "'Recorded Name'"))
        meta = _scaffold(
            root,
            _call("'g'", "'f'"),
            extra_env={"AG_FARM_NAME": "Env Name"},
        )
        _assert_equal(meta["display_name"], "Recorded Name", "env default on existing farm")


def _assert_equal(actual: object, expected: object, context: object) -> None:
    if actual != expected:
        raise SmokeFailure(f"expected {expected!r}, got {actual!r}; context={context!r}")


def main() -> int:
    checks = [
        ("nameless repair call preserves the recorded farm name", check_nameless_call_preserves_existing_name),
        ("explicit farm name still renames", check_explicit_name_still_wins),
        ("fresh farm falls back to the default name", check_fresh_farm_gets_default_name),
        ("AG_FARM_NAME does not rename an existing farm", check_env_default_does_not_rename_existing_farm),
    ]
    for label, check in checks:
        check()
        print(f"PASS: {label}")
    print(f"PASS: {len(checks)} canonical-tree farm-name smoke checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
