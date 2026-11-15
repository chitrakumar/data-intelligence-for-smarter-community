"""Re-brand the pre-built app frontend for the active campus.

The React source for the app isn't in this repo, only the compiled bundle in
``reference_code/app/frontend/dist``. That bundle was built for TAMU, so the map's
initial center, the brand color and the "TAMU" labels are baked in. Lab 06 calls
``apply_branding()`` on the *student's copy* of the app (never on the repo) to swap
those literals for the values in campus.json.

Once the frontend source is available, it should read ``/api/campus`` instead and
this module can go away.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# What the shipped bundle was built with.
BUNDLE_SLUG = "tamu"
BUNDLE_CENTER = "[30.6125,-96.3418]"
BUNDLE_COLOR = "#500000"
BUNDLE_RGBA_PREFIX = "rgba(80,0,0,"
BUNDLE_NAME = "Texas A&M"
BUNDLE_SHORT = "TAMU"
BUNDLE_CITY = "College Station"
BUNDLE_BUILDINGS_SENTENCE = "All 321 mapped buildings on the Texas A&M campus in College Station"


def _js(s: str) -> str:
    """Escape for use inside a double-quoted JS string literal."""
    return json.dumps(s, ensure_ascii=False)[1:-1]


def _rgba_prefix(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},"


def _replacements(cfg: Dict[str, Any], n_buildings: int, for_html: bool) -> List[Tuple[str, str]]:
    esc = html.escape if for_html else _js
    c = cfg["map"]["center"]
    color = cfg["branding"]["primary_color"]
    return [
        (BUNDLE_BUILDINGS_SENTENCE,
         esc(f"All {n_buildings} mapped buildings on the {cfg['name']} campus in {cfg.get('city') or cfg['name']}")),
        (BUNDLE_CENTER, f"[{float(c['lat'])},{float(c['lon'])}]"),
        (BUNDLE_RGBA_PREFIX, _rgba_prefix(color)),
        (BUNDLE_NAME, esc(cfg["name"])),
        (BUNDLE_CITY, esc(cfg.get("city") or "")),
        (BUNDLE_SHORT, esc(cfg["short_name"])),
    ]


def brand_text(text: str, cfg: Dict[str, Any], n_buildings: int, for_html: bool = False) -> Tuple[str, int]:
    """Apply campus branding to one file's text. Returns (new_text, n_replacements)."""
    total = 0
    for old, new in _replacements(cfg, n_buildings, for_html):
        total += text.count(old)
        text = text.replace(old, new)
    text, n = re.subn(re.escape(BUNDLE_COLOR), cfg["branding"]["primary_color"], text, flags=re.I)
    return text, total + n


def apply_branding(dist_dir: str, cfg: Dict[str, Any]) -> Dict[str, int]:
    """Rewrite index.html + assets/*.js|*.css under dist_dir in place. No-op for the bundle's own campus."""
    dist = Path(dist_dir)
    if cfg["slug"] == BUNDLE_SLUG:
        return {}
    gj = Path(cfg["_geojson_dir"]) / "buildings.geojson"
    n_buildings = len(json.loads(gj.read_text(encoding="utf-8")).get("features", []))
    counts: Dict[str, int] = {}
    files = [dist / "index.html"] + sorted((dist / "assets").glob("*.js")) + sorted((dist / "assets").glob("*.css"))
    for f in files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        new, n = brand_text(text, cfg, n_buildings, for_html=f.suffix == ".html")
        if n:
            f.write_text(new, encoding="utf-8")
            counts[str(f.relative_to(dist))] = n
    return counts
