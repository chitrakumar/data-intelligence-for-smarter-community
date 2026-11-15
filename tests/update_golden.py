#!/usr/bin/env python3
"""(Re)write tests/golden/tamu.json: the expected TAMU output of the generator + app backend.

Only run this when a change to TAMU output is *intended*. By default it reads the
current working tree; ``--from <checkout>`` records from another checkout instead
(the committed golden file was recorded from the pre-templatization commit 5c46142).

    python3 tests/update_golden.py
    python3 tests/update_golden.py --from /path/to/old/checkout
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as h  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--from", dest="src", default=str(h.REPO), help="repo checkout to record from")
args = ap.parse_args()
src = Path(args.src) / "workshop" / "Includes"

tele = h.telemetry_digests(h.run_generator(src))
geometry, datasets = h.load_app_modules(src / "reference_code" / "app")
golden = {"scale": h.GOLDEN_SCALE, "seed": 42, "telemetry": tele, "app": h.app_digests(geometry, datasets)}
h.GOLDEN.mkdir(exist_ok=True)
(h.GOLDEN / "tamu.json").write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")
print(f"wrote {h.GOLDEN / 'tamu.json'} from {src}")
for k, (n, d) in tele.items():
    print(f"  {k:<24} {n:>7} rows  {d}")
