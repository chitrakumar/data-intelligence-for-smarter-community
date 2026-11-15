"""Lab notebooks and setup notebooks must stay campus-neutral.

Campus-specific text belongs in the campus profile (campus.json) and is rendered at
runtime (setup banner, Lab 05 Genie instructions, Lab 06 "you should see" line).
The only allowed exceptions are the attribution notices for earlier editions.
"""
import re

import _harness as h

WORKSHOP = h.REPO / "workshop"
NOTEBOOKS = sorted(WORKSHOP.glob("*.py")) + sorted((WORKSHOP / "Includes").glob("Classroom-Setup-*.py"))
CAMPUS_WORDS = re.compile(r"TAMU|Texas A&M|College Station|Aggie|Kyle Field|#500000")  # case-sensitive: the "tamu" slug is fine
ALLOWED = ("Modified November 2026 by Hayley Horn",)  # attribution notices: keep as-is


def test_found_notebooks():
    assert len(NOTEBOOKS) >= 14


def test_no_campus_specific_text():
    hits = []
    for nb in NOTEBOOKS:
        for i, line in enumerate(nb.read_text(encoding="utf-8").splitlines(), 1):
            if CAMPUS_WORDS.search(line) and not any(a in line for a in ALLOWED):
                hits.append(f"{nb.relative_to(h.REPO)}:{i}: {line.strip()[:120]}")
    assert not hits, "campus-specific text in notebooks (move it to campus.json):\n" + "\n".join(hits)
