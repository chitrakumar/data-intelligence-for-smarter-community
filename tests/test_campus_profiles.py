"""Every campus profile under workshop/Includes/campuses/ must be runnable end to end."""
import json
import shutil

import pytest

import _harness as h
from campus_config import CAMPUSES_DIR, check_profile, load_campus

CAMPUSES = sorted(p.name for p in CAMPUSES_DIR.iterdir() if (p / "campus.json").exists())


@pytest.mark.parametrize("slug", CAMPUSES)
def test_profile_has_no_errors(slug):
    errors, _warnings = check_profile(load_campus(slug))
    assert errors == []


@pytest.mark.parametrize("slug", CAMPUSES)
def test_generator_runs_and_stays_on_campus(slug):
    cfg = load_campus(slug)
    tables = h.run_generator(scale=0.01, campus=slug)
    assert len(tables) == 9 and all(len(df) > 0 for df in tables.values())
    bb = cfg["map"]["bbox"]
    for name, df in tables.items():
        if {"latitude", "longitude"} <= set(df.columns):
            lat, lon = df["latitude"].dropna(), df["longitude"].dropna()
            assert lat.between(bb["lat_min"], bb["lat_max"]).all(), name
            assert lon.between(bb["lon_min"], bb["lon_max"]).all(), name
    sites = set(tables["wireless_cells"]["site_name"])
    assert sites == {s["name"] for s in cfg["cell_sites"]}


@pytest.mark.parametrize("slug", CAMPUSES)
def test_app_backend_uses_profile(slug):
    cfg = load_campus(slug)
    geometry, datasets = h.load_app_modules(campus_dir=CAMPUSES_DIR / slug)
    polys = geometry.get_campus_polygons()
    n = len(json.loads((CAMPUSES_DIR / slug / "geojson" / "buildings.geojson").read_text())["features"])
    assert len(polys["features"]) == n
    assert datasets.DATASETS["dim_buildings"][0].startswith(cfg["short_name"] + " ")
    assert set(geometry.ZONE_MAP) == {z["name"] for z in cfg.get("landmark_zones", [])}


def test_checks_catch_a_broken_profile(tmp_path):
    bad = tmp_path / "broken"
    shutil.copytree(CAMPUSES_DIR / "tamu", bad)
    cfg = json.loads((bad / "campus.json").read_text())
    cfg["slug"] = "broken"
    cfg["cell_sites"][0]["lat"] = 0.0                      # outside bbox
    cfg["landmark_zones"][0]["footprint"]["name"] = "Nope"  # unresolvable footprint
    (bad / "campus.json").write_text(json.dumps(cfg))
    gj_path = bad / "geojson" / "buildings.geojson"
    gj = json.loads(gj_path.read_text())
    gj["features"][1]["properties"]["BLDG_UID"] = gj["features"][0]["properties"]["BLDG_UID"]  # duplicate id
    gj_path.write_text(json.dumps(gj))

    errors, warnings = check_profile(load_campus(bad))
    joined = "\n".join(errors + warnings)
    assert "cell site SITE_01" in joined
    assert "duplicate BLDG_UID" in joined
    assert "'Nope' not found" in joined


def test_missing_campus_lists_available():
    with pytest.raises(FileNotFoundError, match="Available campuses"):
        load_campus("does_not_exist")
