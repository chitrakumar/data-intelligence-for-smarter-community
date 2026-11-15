"""TAMU must produce exactly the same data and app output as before templatization.

Golden values in tests/golden/tamu.json were recorded from commit 5c46142 (the last
commit before campus profiles). If you change TAMU output on purpose, re-record with
``python3 tests/update_golden.py`` and say why in the commit message.
"""
import json

import _harness as h

GOLDEN = json.loads((h.GOLDEN / "tamu.json").read_text())


def test_generated_telemetry_matches_golden():
    got = h.telemetry_digests(h.run_generator(scale=GOLDEN["scale"], seed=GOLDEN["seed"], campus="tamu"))
    want = {k: tuple(v) for k, v in GOLDEN["telemetry"].items()}
    assert got == want


def test_app_backend_matches_golden():
    geometry, datasets = h.load_app_modules(campus_dir=h.INCLUDES / "campuses" / "tamu")
    got = json.loads(json.dumps(h.app_digests(geometry, datasets)))
    assert got == GOLDEN["app"]
