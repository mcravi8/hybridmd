"""Dev-only token-count report for the hybridmd demo fixtures.

This script is **not** part of the hybridmd package and is not importable from
it — it lives under ``scripts/`` and sits outside the quality gate's typing
scope. It needs the optional ``bench`` extra (tiktoken)::

    pip install "hybridmd[bench]"

It renders a fixture three ways — hybrid (the analyzer's own per-table decision),
``force="html"`` and ``force="md"`` — counts tokens with tiktoken's
``cl100k_base`` encoding, and reports per fixture the token deltas AND the
fidelity cost: tables the analyzer flagged as needing HTML but that
``force="md"`` emitted as lossy Markdown.

Run with no arguments to compare both bundled fixtures side by side (which shows
that the hybrid-vs-``force="html"`` saving scales with simple-table density);
pass a fixture path to report on just that one. Token counts are
tokenizer-specific; the header names the tokenizer so they are not mistaken for
universal.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# Allow running from a source checkout without installing the package.
sys.path.insert(0, str(_ROOT / "src"))

from hybridmd import DocElement, render  # noqa: E402

_ENCODING_NAME = "cl100k_base"
_EXAMPLES = _ROOT / "examples"
_DEFAULT_FIXTURES = (
    _EXAMPLES / "demo_elements.json",
    _EXAMPLES / "table_heavy_elements.json",
)
_MODES = (
    ("hybrid", None, False),
    ("force=html", "html", False),
    ("force=md", "md", True),
)
_MARKER = re.compile(
    r"<!-- hybridmd: table format=(?P<fmt>\w+) reasons=(?P<reasons>\S+)"
    r"(?: forced=true)? -->"
)


def _load(path: Path) -> list[DocElement]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DocElement.from_dict(item) for item in data]


def _get_encoder():  # returns a tiktoken.Encoding (untyped: optional extra)
    try:
        import tiktoken
    except ImportError:
        sys.exit(
            "token_report needs the optional bench extra; install it with:\n"
            '    pip install "hybridmd[bench]"'
        )
    return tiktoken.get_encoding(_ENCODING_NAME)


def _table_mix(annotated: str) -> tuple[int, int]:
    """(simple, complex) table counts from a hybrid ``annotate=True`` render."""
    simple = complex_ = 0
    for match in _MARKER.finditer(annotated):
        if match["fmt"] == "html":
            complex_ += 1
        elif match["fmt"] == "md":
            simple += 1
    return simple, complex_


def _corruption(annotated: str) -> tuple[int, int]:
    """(corrupted, total) tables — emitted as md despite HTML-requiring reasons."""
    total = corrupted = 0
    for match in _MARKER.finditer(annotated):
        total += 1
        if match["fmt"] == "md" and match["reasons"] not in ("none", "no_html"):
            corrupted += 1
    return corrupted, total


def _report_fixture(path: Path, encoder) -> tuple[int, int]:
    """Print one fixture's comparison block; return (html_overhead, simple_tables)."""
    elements = _load(path)
    counts = {
        name: len(encoder.encode(render(elements, annotate=False, force=force)))
        for name, force, _lossy in _MODES
    }
    hybrid = counts["hybrid"]
    simple, complex_ = _table_mix(render(elements, annotate=True, force=None))
    corrupted, total = _corruption(render(elements, annotate=True, force="md"))

    print(f"{path.name}  ({simple} simple + {complex_} complex tables)")
    header = f"  {'mode':<11} {'tokens':>6} {'delta':>7} {'delta%':>7}  lossy"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for name, _force, lossy in _MODES:
        delta = counts[name] - hybrid
        pct = (delta / hybrid * 100) if hybrid else 0.0
        flag = "yes" if lossy else "no"
        print(f"  {name:<11} {counts[name]:>6} {delta:>+7} {pct:>+6.1f}%  {flag}")
    print(f'  force="md": {corrupted} of {total} tables corrupted (lossy Markdown).')
    print()
    return counts["force=html"] - hybrid, simple


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Token-count comparison for hybridmd's demo fixtures."
    )
    parser.add_argument(
        "fixture",
        nargs="?",
        default=None,
        help="fixture JSON to report on; omit to compare both bundled fixtures",
    )
    args = parser.parse_args()
    fixtures = [Path(args.fixture)] if args.fixture else list(_DEFAULT_FIXTURES)

    encoder = _get_encoder()
    print(f"hybridmd token report  —  tokenizer: tiktoken {_ENCODING_NAME}")
    print()

    overheads: list[tuple[str, int, int]] = []
    for path in fixtures:
        overhead, simple = _report_fixture(path, encoder)
        overheads.append((path.name, overhead, simple))

    if len(overheads) > 1:
        print('hybrid vs force="html" — HTML overhead avoided on simple tables:')
        for name, overhead, simple in overheads:
            per = overhead / simple if simple else 0.0
            print(
                f"  {name:<26} +{overhead} tokens over "
                f"{simple} simple (~{per:.0f}/table)"
            )
        print("The saving scales with the number of simple tables in the document.")


if __name__ == "__main__":
    main()
