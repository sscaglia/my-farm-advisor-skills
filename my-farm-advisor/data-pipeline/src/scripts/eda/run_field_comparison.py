#!/usr/bin/env python3
"""Runtime entrypoint for the field-comparison EDA subskill.

Thin by design: resolve the skill source directory, then hand every argument
to ``eda-field-comparison/src/cli.py``.  The reusable logic lives in the skill
tree; this wrapper exists so the data pipeline keeps a single command surface
next to the other ``src/scripts/eda`` entrypoints.

Run:

    export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
    cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
    .venv/bin/python scripts/eda/run_field_comparison.py \
        --growers il-grower ia-grower ne-grower ar-grower
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from reporting_bootstrap import ensure_skill_path  # noqa: E402

SKILL_NAME = "eda-field-comparison"


def main(argv: list[str] | None = None) -> int:
    ensure_skill_path(SKILL_NAME)
    from cli import main as run  # noqa: PLC0415 — after sys.path setup

    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
