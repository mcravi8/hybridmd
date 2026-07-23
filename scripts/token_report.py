"""Dev-only token-count report for the hybridmd demo fixture.

This script is **not** part of the hybridmd package and is not importable from
it — it lives under ``scripts/`` and sits outside the quality gate's typing
scope. It needs the optional ``bench`` extra (tiktoken)::

    pip install "hybridmd[bench]"

It renders ``examples/demo_elements.json`` three ways — hybrid (the analyzer's
own per-table decision), ``force="html"``, and ``force="md"`` — counts tokens
with tiktoken's ``cl100k_base`` encoding, and reports both the token savings and
the *loss* that ``force="md"`` incurs: tables the analyzer flagged as needing
HTML but that ``force="md"`` emitted as lossy Markdown. Token counts are
tokenizer-specific; the header names the tokenizer so the numbers are not
mistaken for universal.
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

_FIXTURE = _ROOT / "examples" / "demo_elements.json"
_ENCODING_NAME = "cl100k_base"
_MARKER = re.compile(
    r"<!-- hybridmd: table format=(?P<fmt>\w+) reasons=(?P<reasons>\S+)"
    r"(?: forced=true)? -->"
)


def _load_elements() -> list[DocElement]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
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


def _corruption(annotated: str) -> tuple[int, int]:
    """Return (corrupted, total) tables from an ``annotate=True`` render.

    A table is *corrupted* when it was emitted as Markdown (``format=md``) even
    though the analyzer reported HTML-requiring reasons — i.e. ``reasons`` is
    something other than ``none`` (nothing to represent) or ``no_html`` (a text
    fallback). This is exactly the loss that ``force="md"`` trades tokens for.
    """
    total = corrupted = 0
    for match in _MARKER.finditer(annotated):
        total += 1
        if match["fmt"] == "md" and match["reasons"] not in ("none", "no_html"):
            corrupted += 1
    return corrupted, total


def main() -> None:
    elements = _load_elements()
    encoder = _get_encoder()

    modes = (
        ("hybrid", None, False),
        ("force=html", "html", False),
        ("force=md", "md", True),
    )
    counts: dict[str, int] = {}
    for name, force, _lossy in modes:
        rendered = render(elements, annotate=False, force=force)
        counts[name] = len(encoder.encode(rendered))

    hybrid = counts["hybrid"]
    print(f"hybridmd token report  —  tokenizer: tiktoken {_ENCODING_NAME}")
    print(f"fixture: {_FIXTURE.relative_to(_ROOT)}")
    print()
    header = f"{'mode':<11} {'tokens':>6} {'delta':>7} {'delta%':>7}  lossy"
    print(header)
    print("-" * len(header))
    for name, _force, lossy in modes:
        delta = counts[name] - hybrid
        pct = (delta / hybrid * 100) if hybrid else 0.0
        flag = "yes" if lossy else "no"
        print(f"{name:<11} {counts[name]:>6} {delta:>+7} {pct:>+6.1f}%  {flag}")
    print()

    corrupted, total = _corruption(render(elements, annotate=True, force="md"))
    print(
        f'force="md": {corrupted} of {total} tables corrupted '
        "(emitted as Markdown despite the analyzer flagging them as needing HTML)."
    )


if __name__ == "__main__":
    main()
