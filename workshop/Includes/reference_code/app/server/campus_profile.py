"""Active campus profile for the app (campus.json + geojson).

Lab 06 copies ``Includes/campuses/<CAMPUS>/`` into ``server/campus/`` before deploying,
so a deployed app is self-contained. Lookup order:

1. ``CAMPUS_DIR`` env var (a campus profile directory)
2. ``server/campus/`` (bundled by Lab 06)
3. ``Includes/campuses/<CAMPUS env var, default "tamu">/`` (running from the repo for local dev)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

_SERVER_DIR = Path(__file__).parent


def _candidates():
    if os.environ.get("CAMPUS_DIR"):
        yield Path(os.environ["CAMPUS_DIR"])
    yield _SERVER_DIR / "campus"
    # server/ -> app/ -> reference_code/ -> Includes/
    yield _SERVER_DIR.parents[2] / "campuses" / os.environ.get("CAMPUS", "tamu")


@lru_cache(maxsize=1)
def campus_dir() -> Path:
    tried = []
    for d in _candidates():
        if (d / "campus.json").exists():
            return d
        tried.append(str(d))
    raise FileNotFoundError(f"No campus profile (campus.json) found. Looked in: {tried}")


@lru_cache(maxsize=1)
def campus() -> Dict[str, Any]:
    with (campus_dir() / "campus.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def geojson_dir() -> Path:
    return campus_dir() / "geojson"


def center() -> tuple:
    c = campus()["map"]["center"]
    return float(c["lat"]), float(c["lon"])


def short_name() -> str:
    return campus().get("short_name") or campus().get("name", "Campus")


def public_config() -> Dict[str, Any]:
    """Campus settings safe to expose to the frontend via /api/campus."""
    c = campus()
    return {
        "slug": c.get("slug"),
        "name": c.get("name"),
        "short_name": c.get("short_name"),
        "city": c.get("city"),
        "event_name": c.get("event_name"),
        "branding": c.get("branding", {}),
        "map": {k: c["map"][k] for k in ("center", "bbox") if k in c["map"]},
        "attribution": c.get("attribution"),
    }
