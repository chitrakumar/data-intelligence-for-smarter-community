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


# ----------------------------------------------------------------------------- deep checks
BLDG_USAGE_VALUES = {
    "Housing", "StudentHousing", "Academic", "Research", "Services", "Operations",
    "Administrative", "Athletics", "Commons", "Parking", "Commercial", "Other",
}
_REQUIRED_PROPS = {
    "buildings": ("BLDG_UID", "NAME", "CONSTR_STATUS", "BLDG_USAGE"),
    "complexes": ("BCOM_UID", "NAME"),
    "neighbourhoods": ("NAME",),
}


def _centroid(geom: Dict[str, Any]):
    """Mean of all coordinates (same rule Lab 02 uses to place a building)."""
    t, c = geom.get("type"), geom.get("coordinates") or []
    rings = c if t == "Polygon" else [r for poly in c for r in poly] if t == "MultiPolygon" else []
    pts = [p for r in rings for p in r]
    if not pts:
        return None
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def check_profile(cfg: Dict[str, Any]):
    """Deeper consistency checks on a loaded profile.

    Returns (errors, warnings). Errors will break a lab or the app; warnings are worth a look.
    """
    import re
    from datetime import datetime

    errors, warnings = [], []
    cdir = Path(cfg["_dir"])
    if cfg["slug"] != cdir.name:
        errors.append(f"slug '{cfg['slug']}' does not match folder name '{cdir.name}'")
    color = (cfg.get("branding") or {}).get("primary_color", "")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color or ""):
        errors.append(f"branding.primary_color must be a #RRGGBB hex color, got {color!r}")

    bb = cfg["map"]["bbox"]
    inside = lambda lat, lon: bb["lat_min"] <= lat <= bb["lat_max"] and bb["lon_min"] <= lon <= bb["lon_max"]  # noqa: E731

    win = cfg["data_window"]
    try:
        end = datetime.fromisoformat(win["end"])
        cs, ce = datetime.fromisoformat(win["study_crunch_start"]), datetime.fromisoformat(win["study_crunch_end"])
        from datetime import timedelta
        start = end - timedelta(days=int(win["days"]))
        if not (start <= cs < ce <= end):
            warnings.append(f"study crunch {cs:%Y-%m-%d}..{ce:%Y-%m-%d} is not inside the data window "
                            f"{start:%Y-%m-%d}..{end:%Y-%m-%d}")
    except (ValueError, TypeError) as e:
        errors.append(f"data_window dates must be ISO timestamps: {e}")

    gj = {}
    for kind in ("buildings", "complexes", "neighbourhoods"):
        with geojson_path(cfg, kind).open("r", encoding="utf-8") as f:
            gj[kind] = json.load(f).get("features", [])
        if not gj[kind]:
            errors.append(f"{GEOJSON_FILES[kind]} has no features")
        for i, ft in enumerate(gj[kind]):
            props = ft.get("properties") or {}
            missing = [k for k in _REQUIRED_PROPS[kind] if props.get(k) in (None, "")]
            if missing:
                errors.append(f"{GEOJSON_FILES[kind]} feature #{i} ({props.get('NAME')!r}) missing {missing}")
                break
            if (ft.get("geometry") or {}).get("type") not in ("Polygon", "MultiPolygon"):
                errors.append(f"{GEOJSON_FILES[kind]} feature {props.get('NAME')!r} is not a (Multi)Polygon")
                break

    bld = [f["properties"] for f in gj["buildings"]]
    for key in ("BLDG_UID", "NAME"):
        dups = sorted({p[key] for p in bld if [q[key] for q in bld].count(p[key]) > 1})
        if dups:
            errors.append(f"buildings.geojson has duplicate {key}: {dups[:5]}")
    complete = [f for f in gj["buildings"] if f["properties"].get("CONSTR_STATUS") == "Complete"]
    if len(complete) < 30:
        warnings.append(f"only {len(complete)} buildings with CONSTR_STATUS='Complete' (TAMU has 321)")
    outside = [f["properties"]["NAME"] for f in complete
               if (c := _centroid(f["geometry"])) and not inside(*c)]
    if outside:
        warnings.append(f"{len(outside)} building(s) outside map.bbox will be dropped in Lab 02: {outside[:5]}")
    bad_usage = sorted({p["BLDG_USAGE"] for p in bld} - BLDG_USAGE_VALUES)
    if bad_usage:
        warnings.append(f"BLDG_USAGE values outside the vocabulary become 'Other': {bad_usage}")
    if not any(p["BLDG_USAGE"] in ("StudentHousing", "Housing") for p in bld):
        warnings.append("no StudentHousing buildings: residence-hall views in the app will be empty")
    zone_names = {f["properties"]["NAME"] for f in gj["neighbourhoods"]}
    unknown_nbhd = sorted({p.get("NEIGHBOURHOOD") for p in bld if p.get("NEIGHBOURHOOD")} - zone_names)
    if unknown_nbhd:
        warnings.append(f"buildings reference NEIGHBOURHOOD values with no zone polygon: {unknown_nbhd}")

    for s in cfg["cell_sites"]:
        if not inside(float(s["lat"]), float(s["lon"])):
            errors.append(f"cell site {s['site_id']} ({s['name']}) is outside map.bbox")
    names = {"buildings": {p["NAME"] for p in bld},
             "complexes": {f["properties"]["NAME"] for f in gj["complexes"]},
             "neighbourhoods": zone_names}
    for z in cfg.get("landmark_zones", []):
        if not inside(float(z["lat"]), float(z["lon"])):
            errors.append(f"landmark {z['zone_id']} ({z['name']}) is outside map.bbox")
        fp = z.get("footprint")
        if fp:
            pool = names.get(fp.get("source"), set())
            target = fp.get("name", "")
            hit = (any(target.lower() in n.lower() or n.lower() in target.lower() for n in pool)
                   if fp.get("contains") else target.lower() in {n.lower() for n in pool})
            if not hit:
                warnings.append(f"landmark {z['name']!r}: footprint {fp.get('source')}/{target!r} not found "
                                f"(the app will draw a circle instead)")
    return errors, warnings
