"""End-to-end golden test — a REGRESSION PIN, not a correctness oracle.

This asserts that ``render()`` reproduces ``examples/expected_output.md``
byte-for-byte on the demo fixture. The golden file locks in behavior that a
human reviewed; it does **not** independently verify that the output is correct.
A failure here means the rendered output *changed* — whether that change is
desirable is a judgment for the reviewer, not something this test can decide.

To regenerate after a deliberate, reviewed change::

    HYBRIDMD_UPDATE_GOLDEN=1 pytest tests/test_e2e.py

which rewrites the golden and then FAILS (it never silently passes), so the new
output must be reviewed and the test re-run without the flag.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hybridmd import DocElement, render

# Resolve fixtures relative to this file, never the current working directory.
_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
_FIXTURE = _EXAMPLES / "demo_elements.json"
_GOLDEN = _EXAMPLES / "expected_output.md"


def test_demo_fixture_matches_golden() -> None:
    elements = [
        DocElement.from_dict(item)
        for item in json.loads(_FIXTURE.read_text(encoding="utf-8"))
    ]
    rendered = render(elements, annotate=True)

    if os.environ.get("HYBRIDMD_UPDATE_GOLDEN") == "1":
        _GOLDEN.write_text(rendered, encoding="utf-8")
        pytest.fail(
            f"golden regenerated at {_GOLDEN.name}; review the diff and re-run "
            "without HYBRIDMD_UPDATE_GOLDEN=1",
            pytrace=False,
        )

    assert rendered == _GOLDEN.read_text(encoding="utf-8")
