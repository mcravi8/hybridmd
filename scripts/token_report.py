"""Dev-only token-count report for the hybridmd demo fixtures.

This script is **not** part of the hybridmd package and is not importable from
it — it lives under ``scripts/`` and sits outside the quality gate's typing
scope. It needs the optional ``bench`` extra (tiktoken)::

    pip install "hybridmd[bench]"

It renders two corpora — a 2-table report excerpt and a table-heavy appendix —
three ways each: hybrid (the analyzer's own per-table decision), ``force="html"``
and ``force="md"``. It counts tokens with tiktoken's ``cl100k_base`` encoding and
reports, per corpus, the token deltas AND the fidelity cost: tables the analyzer
flagged as needing HTML but that ``force="md"`` emitted as lossy Markdown. Two
corpora make a point one fixture cannot — the hybrid-vs-``force="html"`` saving
scales with how many *simple* tables a document holds. Token counts are
tokenizer-specific; the header names the tokenizer so they are not mistaken for
universal.
"""

from __future__ import annotations

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
_CORPORA = (
    ("2-table report excerpt", _EXAMPLES / "demo_elements.json"),
    ("table-heavy appendix", _EXAMPLES / "demo_elements_table_heavy.json"),
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


def _report_corpus(label: str, path: Path, encoder) -> tuple[int, int]:
    """Print one corpus's report; return (html_overhead_tokens, simple_tables)."""
    elements = _load(path)
    counts = {
        name: len(encoder.encode(render(elements, annotate=False, force=force)))
        for name, force, _lossy in _MODES
    }
    hybrid = counts["hybrid"]
    simple, complex_ = _table_mix(render(elements, annotate=True, force=None))
    corrupted, total = _corruption(render(elements, annotate=True, force="md"))

    print(f"{label}  ({simple} simple, {complex_} complex tables)")
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
    encoder = _get_encoder()
    print(f"hybridmd token report  —  tokenizer: tiktoken {_ENCODING_NAME}")
    print()

    overheads: list[tuple[str, int, int]] = []
    for label, path in _CORPORA:
        overhead, simple = _report_corpus(label, path, encoder)
        overheads.append((label, overhead, simple))

    print('hybrid vs force="html" — the HTML overhead hybrid avoids on simple tables:')
    for label, overhead, simple in overheads:
        per = overhead / simple if simple else 0.0
        print(
            f"  {label:<23} +{overhead} tokens over {simple} simple (~{per:.0f}/table)"
        )
    print("The saving scales with the number of simple tables in the document.")


if __name__ == "__main__":
    main()
