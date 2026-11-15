# Tests

Local checks that run in seconds, with no Spark or Databricks workspace needed.

```bash
python3 -m venv .venv && .venv/bin/pip install -r tests/requirements.txt
.venv/bin/python -m pytest tests -q
```

| File | Checks |
|---|---|
| `test_tamu_regression.py` | TAMU generator output + app backend are byte-identical to the pre-templatization code (`golden/tamu.json`, recorded from commit `5c46142`) |
| `test_campus_profiles.py` | Every campus under `workshop/Includes/campuses/` passes `check_profile`, generates all 9 tables inside its bbox, and drives the app backend |
| `test_frontend_branding.py` | Lab 06's bundle re-branding: no-op for TAMU, removes every TAMU literal for other campuses, JS still parses (`node --check` if Node is installed) |

If you change TAMU output on purpose, re-record the golden file with
`python3 tests/update_golden.py` and explain why in the commit.
