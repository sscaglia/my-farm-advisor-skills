"""Helpers for loading local skill modules and canonical data-tree scaffolding."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from lib.runtime_paths import resolve_runtime_paths


_RUNTIME_PATHS = resolve_runtime_paths()
RUNTIME_BASE = _RUNTIME_PATHS.runtime_base
RUNTIME_SOURCE = _RUNTIME_PATHS.runtime_source
SOURCE_LOCATOR_PATH = RUNTIME_BASE / ".my-farm-advisor-source.json"
DATA_ROOT = RUNTIME_BASE
GROWERS_ROOT = DATA_ROOT / "growers"
SHARED_ROOT = DATA_ROOT / "shared"
DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")
DEFAULT_FARM_NAME = os.environ.get("AG_FARM_NAME", "Default Farm")
DEFAULT_INVENTORY = Path(
    os.environ.get(
        "AG_INVENTORY_CSV",
        str(
            GROWERS_ROOT
            / DEFAULT_GROWER
            / "farms"
            / DEFAULT_FARM
            / "manifests"
            / "field-inventory.csv"
        ),
    )
)


def _candidate_skill_roots() -> list[Path]:
    roots: list[Path] = [RUNTIME_SOURCE]

    locator_root = _source_locator_skill_root()
    if locator_root is not None:
        roots.append(locator_root)

    for env_name in ("MY_FARM_ADVISOR_SKILL_ROOT", "MY_FARM_ADVISOR_ROOT"):
        raw = os.environ.get(env_name)
        if raw:
            roots.append(Path(raw).expanduser().resolve(strict=False))

    install_script = os.environ.get("DATA_PIPELINE_INSTALL_SCRIPT")
    if install_script:
        install_path = Path(install_script).expanduser().resolve(strict=False)
        if len(install_path.parents) >= 3:
            roots.append(install_path.parents[2])

    checkout_root = Path(__file__).resolve().parents[3]
    if (checkout_root / "SKILL.md").exists():
        roots.append(checkout_root)

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        unique_roots.append(root)
    return unique_roots


def _source_locator_skill_root() -> Path | None:
    if not SOURCE_LOCATOR_PATH.exists():
        return None
    try:
        payload = json.loads(SOURCE_LOCATOR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = payload.get("my_farm_advisor_skill_root")
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw).expanduser().resolve(strict=False)
    if not (candidate / "SKILL.md").exists():
        return None
    return candidate


def ensure_skill_path(skill_name: str) -> Path:
    matches: list[Path] = []
    for root in _candidate_skill_roots():
        direct = root / skill_name / "src"
        if direct.exists():
            matches.append(direct)
        matches.extend(sorted(root.glob(f"**/{skill_name}/src")) if root.exists() else [])

    if not matches:
        searched = ", ".join(str(root) for root in _candidate_skill_roots())
        raise FileNotFoundError(
            f"Skill source path not found for '{skill_name}' under: {searched}"
        )

    skill_path = matches[0]
    resolved = str(skill_path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)
    return skill_path


def farm_root(grower_slug: str = DEFAULT_GROWER, farm_slug: str = DEFAULT_FARM) -> Path:
    return GROWERS_ROOT / grower_slug / "farms" / farm_slug


def fields_root(
    grower_slug: str = DEFAULT_GROWER, farm_slug: str = DEFAULT_FARM
) -> Path:
    return farm_root(grower_slug, farm_slug) / "fields"


def field_slugs_from_inventory(inventory_path: Path | None = None) -> list[str]:
    inventory = inventory_path or DEFAULT_INVENTORY
    inventory = inventory if inventory.is_absolute() else DATA_ROOT / inventory
    if not inventory.exists():
        return []
    rows = inventory.read_text(encoding="utf-8").splitlines()
    slugs: list[str] = []
    for line in rows[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) != 2:
            continue
        slugs.append(parts[1].strip())
    return slugs


def field_slug_map_from_inventory(inventory_path: Path | None = None) -> dict[str, str]:
    inventory = inventory_path or DEFAULT_INVENTORY
    inventory = inventory if inventory.is_absolute() else DATA_ROOT / inventory
    if not inventory.exists():
        return {}
    rows = inventory.read_text(encoding="utf-8").splitlines()
    mapping: dict[str, str] = {}
    for line in rows[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) != 2:
            continue
        mapping[parts[0].strip()] = parts[1].strip()
    return mapping


def _write_json(path: Path, payload: dict, *, overwrite: bool = True) -> None:
    if path.exists() and not overwrite:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str, *, overwrite: bool = True) -> None:
    if path.exists() and not overwrite:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_canonical_field_artifacts(
    field_slug: str, grower_slug: str = DEFAULT_GROWER, farm_slug: str = DEFAULT_FARM
) -> None:
    base = fields_root(grower_slug, farm_slug) / field_slug
    for rel in (
        "boundary",
        "soil",
        "weather",
        "satellite/landsat",
        "satellite/sentinel",
        "derived/tables",
        "derived/features",
        "derived/summaries",
        "derived/reports",
        "manifests",
        "logs",
    ):
        (base / rel).mkdir(parents=True, exist_ok=True)

    field_geojson = {
        "type": "FeatureCollection",
        "features": [],
    }
    _write_json(
        base / "field.json",
        {
            "grower_slug": grower_slug,
            "farm_slug": farm_slug,
            "field_slug": field_slug,
            "display_name": field_slug,
            "field_id": field_slug,
            "boundary_file": "boundary/field_boundary.geojson",
            "soil_file": "soil/ssurgo_soil_types.geojson",
            "weather_file": "weather/daily_weather.csv",
            "satellite_dir": "satellite/",
            "notes": "Canonical field metadata",
        },
        overwrite=False,
    )
    _write_json(
        base / "boundary" / "field_boundary.geojson", field_geojson, overwrite=False
    )
    _write_json(
        base / "soil" / "ssurgo_soil_types.geojson", field_geojson, overwrite=False
    )
    _write_text(
        base / "weather" / "daily_weather.csv",
        "field_id,date,T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN,RH2M,WS10M\n",
        overwrite=False,
    )

    _write_json(
        base / "soil" / "metadata.json",
        {
            "dataset_name": "ssurgo_soil_types",
            "source": "usda-sda",
            "spatial_scope": "field",
            "grower_slug": grower_slug,
            "farm_slug": farm_slug,
            "field_slug": field_slug,
            "format": "geojson",
            "crs": "EPSG:4326",
        },
        overwrite=False,
    )
    _write_json(
        base / "weather" / "metadata.json",
        {
            "dataset_name": "daily_weather",
            "source": "nasa-power",
            "spatial_scope": "field",
            "grower_slug": grower_slug,
            "farm_slug": farm_slug,
            "field_slug": field_slug,
            "format": "csv",
            "crs": "EPSG:4326",
        },
        overwrite=False,
    )

    _write_json(
        base / "satellite" / "landsat" / "manifest.json",
        {
            "dataset_name": "landsat",
            "field_slug": field_slug,
            "years": [],
        },
        overwrite=False,
    )
    _write_json(
        base / "satellite" / "sentinel" / "manifest.json",
        {
            "dataset_name": "sentinel",
            "field_slug": field_slug,
            "years": [],
        },
        overwrite=False,
    )
    _write_text(base / "logs" / "pipeline_runs.jsonl", "", overwrite=False)


ACRES_PER_HECTARE = 2.471053814671653


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sync_field_metadata_from_boundary(
    grower_slug: str = DEFAULT_GROWER,
    farm_slug: str = DEFAULT_FARM,
    boundary_path: Path | None = None,
    inventory_path: Path | None = None,
) -> list[str]:
    """Copy stable field attributes from the boundary file into ``field.json``.

    The farm boundary GeoJSON is the authority for ``field_id``, area, county,
    state and country; ``field.json`` is the per-field metadata/override
    sidecar.  This sync keeps the two aligned without ever touching ``crop`` or
    ``crop_name`` -- those stay a human override slot consumed by the web map,
    and must not be filled from the boundary or the override becomes
    meaningless.

    Returns the slugs whose metadata changed.  Writing is atomic per file and
    idempotent, so repeated pipeline runs do not churn the tree.
    """

    boundary = boundary_path or (
        farm_root(grower_slug, farm_slug) / "boundary" / "field_boundaries.geojson"
    )
    if not boundary.is_file():
        return []
    try:
        collection = json.loads(boundary.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    slug_map = field_slug_map_from_inventory(inventory_path)
    changed: list[str] = []
    for feature in collection.get("features", []):
        props = feature.get("properties") or {}
        field_id = str(props.get("field_id") or "").strip()
        if not field_id:
            continue
        field_slug = (
            str(props.get("field_slug") or "").strip()
            or slug_map.get(field_id)
            or field_id
        )
        metadata_path = fields_root(grower_slug, farm_slug) / field_slug / "field.json"
        if not metadata_path.exists():
            ensure_canonical_field_artifacts(field_slug, grower_slug, farm_slug)
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}

        payload["grower_slug"] = grower_slug
        payload["farm_slug"] = farm_slug
        payload["field_slug"] = field_slug
        # ``field_slug`` is the canonical lowercase join key; the boundary
        # ``field_id`` selects the row but must not reintroduce case drift.
        payload["field_id"] = field_slug
        for key in ("country", "state", "county", "source"):
            value = props.get(key)
            if value is not None and str(value).strip():
                payload[key] = str(value).strip()

        acres = _optional_float(props.get("area_acres"))
        hectares = _optional_float(props.get("area_ha_est"))
        if acres is None and hectares is not None:
            acres = hectares * ACRES_PER_HECTARE
        if hectares is None and acres is not None:
            hectares = acres / ACRES_PER_HECTARE
        if acres is not None:
            payload["area_acres"] = round(acres, 2)
        if hectares is not None:
            payload["area_ha"] = round(hectares, 2)

        serialized = json.dumps(payload, indent=2) + "\n"
        try:
            current = metadata_path.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if current != serialized:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(serialized, encoding="utf-8")
            changed.append(field_slug)
    return changed


def ensure_canonical_data_tree(
    grower_slug: str = DEFAULT_GROWER,
    farm_slug: str = DEFAULT_FARM,
    farm_name: str | None = None,
    inventory_path: Path | None = None,
    include_farm: bool = True,
    country: str | None = None,
    state: str | None = None,
) -> list[str]:
    (DATA_ROOT / "shared" / "weather").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "geoadmin" / "l0_countries" / "raw").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "geoadmin" / "l1_states" / "raw").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "geoadmin" / "l2_counties" / "raw").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "corn_maturity" / "tables").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "corn_maturity" / "reports").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "corn_maturity" / "metadata").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "corn_maturity" / "manifests").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "corn_maturity" / "logs").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "soybean_maturity" / "tables").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "soybean_maturity" / "reports").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "soybean_maturity" / "metadata").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "soybean_maturity" / "manifests").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "soybean_maturity" / "logs").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "cdl" / "metadata").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "cdl" / "rasters").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "cdl" / "derived").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "cdl" / "derived" / "tables").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "cdl" / "derived" / "reports").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "cdl" / "manifests").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "cdl" / "logs").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "reference" / "crop_codes").mkdir(
        parents=True, exist_ok=True
    )
    (DATA_ROOT / "shared" / "reference" / "units").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "reference" / "schemas").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "manifests").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "shared" / "logs").mkdir(parents=True, exist_ok=True)
    _write_json(
        DATA_ROOT / "shared" / "geoadmin" / "l0_countries" / "metadata.json",
        {
            "dataset_name": "geoadmin_countries",
            "source": "natural-earth",
            "spatial_scope": "global",
            "format": "geojson-or-parquet",
            "notes": "Shared Level 0 admin root for annual maturity and geoadmin workflows",
        },
        overwrite=False,
    )
    _write_json(
        DATA_ROOT / "shared" / "geoadmin" / "l1_states" / "metadata.json",
        {
            "dataset_name": "geoadmin_states",
            "source": "census-tiger-line",
            "spatial_scope": "usa-state",
            "format": "geojson-or-parquet",
            "notes": "Shared Level 1 admin root for annual maturity and geoadmin workflows",
        },
        overwrite=False,
    )
    _write_json(
        DATA_ROOT / "shared" / "geoadmin" / "l2_counties" / "metadata.json",
        {
            "dataset_name": "geoadmin_counties",
            "source": "census-tiger-line",
            "spatial_scope": "usa-county",
            "format": "geojson-or-parquet",
            "notes": "Shared county and FIPS root for annual maturity and geoadmin workflows",
        },
        overwrite=False,
    )
    _write_json(
        DATA_ROOT / "shared" / "corn_maturity" / "metadata" / "dataset.json",
        {
            "dataset_name": "corn_maturity",
            "status": "planned",
            "notes": "Annual heuristic corn RM and GDD outputs by FIPS live here",
        },
        overwrite=False,
    )
    _write_json(
        DATA_ROOT / "shared" / "soybean_maturity" / "metadata" / "dataset.json",
        {
            "dataset_name": "soybean_maturity",
            "status": "planned",
            "notes": "Annual heuristic soybean maturity-group outputs by FIPS live here",
        },
        overwrite=False,
    )

    if not include_farm:
        return []

    grower = DATA_ROOT / "growers" / grower_slug
    grower.mkdir(parents=True, exist_ok=True)
    (grower / "manifests").mkdir(parents=True, exist_ok=True)
    (grower / "logs").mkdir(parents=True, exist_ok=True)
    _write_json(
        grower / "grower.json",
        {
            "grower_slug": grower_slug,
            "display_name": grower_slug,
            "notes": "Canonical grower metadata",
        },
    )
    _write_text(grower / "logs" / "pipeline_runs.jsonl", "", overwrite=False)

    farm = farm_root(grower_slug, farm_slug)
    farm.mkdir(parents=True, exist_ok=True)
    (farm / "boundary").mkdir(parents=True, exist_ok=True)
    (farm / "manifests").mkdir(parents=True, exist_ok=True)
    (farm / "logs").mkdir(parents=True, exist_ok=True)
    (farm / "derived" / "reports").mkdir(parents=True, exist_ok=True)
    (farm / "derived" / "summaries").mkdir(parents=True, exist_ok=True)
    (farm / "derived" / "dashboards").mkdir(parents=True, exist_ok=True)
    (farm / "derived" / "tables").mkdir(parents=True, exist_ok=True)
    farm_metadata_path = farm / "farm.json"
    existing_metadata: dict[str, object] = {}
    if farm_metadata_path.exists():
        try:
            existing_metadata = json.loads(farm_metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing_metadata = {}
    # Country/state drive soil, crop-history, and strategy routing.  Never
    # reset them to the US/IA placeholder once a real farm has recorded them.
    resolved_country = (country or existing_metadata.get("country") or "US")
    resolved_state = state or existing_metadata.get("state") or "IA"
    # Most pipeline legs call this helper without a farm name just to make sure
    # the tree exists.  The module default must therefore not overwrite a name
    # already recorded on disk, or every leg would rename the farm to
    # "Default Farm".  An explicit farm_name still wins.
    resolved_farm_name = (
        farm_name or existing_metadata.get("display_name") or DEFAULT_FARM_NAME
    )
    _write_json(
        farm_metadata_path,
        {
            "grower_slug": grower_slug,
            "farm_slug": farm_slug,
            "display_name": resolved_farm_name,
            "state": str(resolved_state).strip(),
            "country": str(resolved_country).strip().upper(),
            "default_crs": "EPSG:4326",
            "notes": "Canonical farm metadata",
        },
    )
    _write_text(farm / "logs" / "pipeline_runs.jsonl", "", overwrite=False)

    slugs = field_slugs_from_inventory(inventory_path=inventory_path)
    if not slugs:
        root = fields_root(grower_slug, farm_slug)
        if root.exists():
            slugs = sorted([p.name for p in root.iterdir() if p.is_dir()])

    for slug in slugs:
        ensure_canonical_field_artifacts(slug, grower_slug, farm_slug)

    return slugs
