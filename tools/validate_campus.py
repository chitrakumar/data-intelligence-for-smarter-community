#!/usr/bin/env python3
"""Validate one or more campus profiles before running the workshop.

    python3 tools/validate_campus.py baylor        # one campus
    python3 tools/validate_campus.py               # every campus under workshop/Includes/campuses/

Exit code 1 if any profile has errors. Stdlib only.
"""
import sys
from pathlib import Path

INCLUDES = Path(__file__).resolve().parents[1] / "workshop" / "Includes"
sys.path.insert(0, str(INCLUDES))
from campus_config import CAMPUSES_DIR, check_profile, load_campus  # noqa: E402


def main(argv):
    slugs = argv or sorted(p.name for p in CAMPUSES_DIR.iterdir() if (p / "campus.json").exists())
    failed = False
    for slug in slugs:
        try:
            cfg = load_campus(slug)
            errors, warnings = check_profile(cfg)
        except (FileNotFoundError, ValueError, KeyError) as e:
            errors, warnings, cfg = [str(e)], [], {"name": slug}
        status = "FAIL" if errors else "OK"
        print(f"[{status}] {slug}: {cfg.get('name')}")
        for e in errors:
            print(f"   ERROR   {e}")
        for w in warnings:
            print(f"   warning {w}")
        failed |= bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
