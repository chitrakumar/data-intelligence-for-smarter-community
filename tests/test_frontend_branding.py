"""The compiled frontend is re-branded per campus by Lab 06 (frontend_branding.py)."""
import shutil
import subprocess

import pytest

import _harness as h
from campus_config import CAMPUSES_DIR, load_campus
from frontend_branding import BUNDLE_SLUG, apply_branding

DIST = h.APP / "frontend" / "dist"
OTHERS = sorted(p.name for p in CAMPUSES_DIR.iterdir() if (p / "campus.json").exists() and p.name != BUNDLE_SLUG)
TAMU_LITERALS = ["TAMU", "Texas A&M", "College Station", "#500000", "rgba(80,0,0,", "[30.6125,-96.3418]"]


def _texts(d):
    return {f: f.read_text(encoding="utf-8") for f in [d / "index.html", *(d / "assets").glob("*.js"),
                                                       *(d / "assets").glob("*.css")]}


def test_bundle_campus_is_a_noop(tmp_path):
    dist = shutil.copytree(DIST, tmp_path / "dist")
    assert apply_branding(str(dist), load_campus(BUNDLE_SLUG)) == {}
    assert [t for t in _texts(dist).values()] == [t for t in _texts(DIST).values()]


@pytest.mark.parametrize("slug", OTHERS)
def test_rebrand_removes_tamu_and_keeps_js_valid(tmp_path, slug):
    cfg = load_campus(slug)
    dist = shutil.copytree(DIST, tmp_path / "dist")
    assert apply_branding(str(dist), cfg)
    texts = _texts(dist)
    for lit in TAMU_LITERALS:
        assert not any(lit.lower() in t.lower() for t in texts.values()), lit
    js = "\n".join(t for f, t in texts.items() if f.suffix == ".js")
    assert f"[{cfg['map']['center']['lat']},{cfg['map']['center']['lon']}]" in js
    assert cfg["branding"]["primary_color"] in js
    node = shutil.which("node")
    if node:
        for f in texts:
            if f.suffix == ".js":
                subprocess.run([node, "--check", str(f)], check=True)


def test_repo_bundle_untouched():
    texts = _texts(DIST)
    assert any("TAMU" in t for t in texts.values()), "repo bundle must stay as shipped; branding edits copies only"
