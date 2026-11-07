"""Campus profile loader for the Smart Community workshop.

Each campus lives in ``Includes/campuses/<slug>/``:

    campus.json                 names, branding, map bbox/center, data window,
                                landmark zones, synthetic cell sites
    geojson/buildings.geojson       building footprints   (BLDG_UID, NAME, BLDG_USAGE, ...)
    geojson/complexes.geojson       residence complexes   (BCOM_UID, NAME, GBA, UNITS, ...)
    geojson/neighbourhoods.geojson  zone polygons         (ID, NAME)
    geojson/landuse.geojson         optional
    geojson/legal_boundary.geojson  optional

Pick the active campus with ``CAMPUS`` in ``Classroom-Setup-Common``. Stdlib only, so it
loads the same way in notebooks, the generator and the app.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

CAMPUSES_DIR = Path(__file__).parent / "campuses"

GEOJSON_FILES = {
    "buildings": "buildings.geojson",
    "complexes": "complexes.geojson",
    "neighbourhoods": "neighbourhoods.geojson",
    "landuse": "landuse.geojson",
    "legal_boundary": "legal_boundary.geojson",
}
REQUIRED_GEOJSON = ("buildings", "complexes", "neighbourhoods")

_REQUIRED_KEYS = {
    "": ("slug", "name", "short_name", "map", "data_window", "cell_sites"),
    "map": ("center", "bbox"),
    "map.center": ("lat", "lon"),
    "map.bbox": ("lat_min", "lat_max", "lon_min", "lon_max"),
    "data_window": ("end", "days", "study_crunch_start", "study_crunch_end"),
}


def campus_dir(campus: Union[str, Path], base: Optional[Path] = None) -> Path:
    """Resolve a campus slug (e.g. ``"tamu"``) or a directory path to the profile dir."""
    p = Path(campus)
    if p.is_dir():
        return p
    return (base or CAMPUSES_DIR) / str(campus)


def _get(cfg: Dict[str, Any], dotted: str) -> Any:
    node: Any = cfg
    for part in filter(None, dotted.split(".")):
        node = node[part]
    return node


def validate(cfg: Dict[str, Any], cdir: Optional[Path] = None) -> None:
    missing = []
    for section, keys in _REQUIRED_KEYS.items():
        try:
            node = _get(cfg, section)
        except (KeyError, TypeError):
            missing.append(section)
            continue
        missing += [f"{section}.{k}".lstrip(".") for k in keys if k not in node]
    if missing:
        raise ValueError(f"campus.json is missing required keys: {', '.join(missing)}")
    bb = cfg["map"]["bbox"]
    if not (bb["lat_min"] < bb["lat_max"] and bb["lon_min"] < bb["lon_max"]):
        raise ValueError(f"campus.json map.bbox is inverted: {bb}")
    c = cfg["map"]["center"]
    if not (bb["lat_min"] <= c["lat"] <= bb["lat_max"] and bb["lon_min"] <= c["lon"] <= bb["lon_max"]):
        raise ValueError(f"campus.json map.center {c} is outside map.bbox {bb}")
    if cdir is not None:
        gdir = cdir / "geojson"
        absent = [GEOJSON_FILES[k] for k in REQUIRED_GEOJSON if not (gdir / GEOJSON_FILES[k]).exists()]
        if absent:
            raise FileNotFoundError(f"Campus '{cfg['slug']}' is missing geojson files in {gdir}: {absent}")


def load_campus(campus: Union[str, Path], base: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate a campus profile. Adds ``_dir`` and ``_geojson_dir`` (as str)."""
    cdir = campus_dir(campus, base)
    path = cdir / "campus.json"
    if not path.exists():
        available = sorted(p.name for p in (base or CAMPUSES_DIR).glob("*") if (p / "campus.json").exists())
        raise FileNotFoundError(f"No campus profile at {path}. Available campuses: {available}")
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    validate(cfg, cdir)
    cfg["_dir"] = str(cdir)
    cfg["_geojson_dir"] = str(cdir / "geojson")
    return cfg


def geojson_path(cfg: Dict[str, Any], kind: str) -> Path:
    return Path(cfg["_geojson_dir"]) / GEOJSON_FILES[kind]
