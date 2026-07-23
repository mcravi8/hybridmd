"""Assemble the final hybrid Markdown document — the package's public entry point.

:func:`render` walks a sequence of :class:`~hybridmd.schema.DocElement` and emits a
single deterministic string: Markdown wherever it is lossless, and sanitized
embedded HTML only for tables that :func:`~hybridmd.analyzer.analyze_table` flags
as beyond Markdown's reach. Non-table elements are delegated to
:func:`~hybridmd.serialize.element_to_markdown`; tables are routed per the
analyzer's verdict (or an explicit ``force`` override).

The output is byte-for-byte deterministic: identical input always yields identical
output. Blocks are separated by a single blank line with exactly one trailing
newline and no leading whitespace.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, NamedTuple

from hybridmd.analyzer import analyze_table
from hybridmd.schema import DocElement, ElementType
from hybridmd.serialize import (
    element_to_markdown,
    sanitize_table_html,
    table_to_markdown,
)

Force = Literal["md", "html"]


class _TableBlock(NamedTuple):
    """The rendered body of one table plus the metadata its marker reports."""

    body: str  # the emitted string (Markdown table, sanitized HTML, or plain text)
    fmt: str  # what was actually emitted: "md" | "html" | "text"
    reasons: str  # the marker's ``reasons=`` value
    forced: bool  # True iff ``force`` overrode the analyzer for this table


def _render_table(el: DocElement, force: Force | None) -> _TableBlock:
    """Route a single TABLE element to Markdown, sanitized HTML, or a text fallback.

    ``force`` overrides the analyzer only for a table with usable HTML. The two
    fallback paths — no HTML, or HTML that contains no usable ``<table>`` — are
    unaffected by ``force`` and never let a :class:`ValueError` escape.
    """
    html = el.html
    if html is None or not html.strip():
        # No usable HTML → plain text. `force` does not affect this fallback.
        return _TableBlock(el.text, "text", "no_html", forced=False)
    try:
        # The analyzer runs even under `force`: `force` decides what is *emitted*,
        # but the marker always reports the analyzer's real reasons — so the lossy
        # force="md" arm is self-documenting (it records which tables it mangled).
        analysis = analyze_table(html)
        reasons = (
            ",".join(reason.value for reason in analysis.reasons)
            if analysis.reasons
            else "none"
        )
        if force == "md":
            return _TableBlock(table_to_markdown(html), "md", reasons, forced=True)
        if force == "html":
            return _TableBlock(sanitize_table_html(html), "html", reasons, forced=True)
        if analysis.needs_html:
            return _TableBlock(sanitize_table_html(html), "html", reasons, forced=False)
        return _TableBlock(table_to_markdown(html), "md", reasons, forced=False)
    except ValueError:
        # HTML present but no usable <table> (or a table with no rows). This must
        # never escape render; `force` does not rescue it — fall back to text.
        return _TableBlock(el.text, "text", "no_html", forced=False)


def _marker(block: _TableBlock) -> str:
    """The annotation comment emitted immediately before *block*'s table."""
    forced = " forced=true" if block.forced else ""
    return (
        f"<!-- hybridmd: table format={block.fmt} reasons={block.reasons}{forced} -->"
    )


def render(
    elements: Sequence[DocElement],
    *,
    annotate: bool = False,
    force: Force | None = None,
) -> str:
    """Assemble *elements* into a single hybrid Markdown document.

    Non-table elements are rendered with
    :func:`~hybridmd.serialize.element_to_markdown`. Each TABLE is routed by
    :func:`~hybridmd.analyzer.analyze_table`: a representable table becomes a
    Markdown pipe table, a complex one becomes sanitized embedded HTML. A table
    whose ``html`` is missing/blank, or present but containing no usable
    ``<table>``, falls back to its plain ``text`` (the analyzer's ``ValueError``
    is caught and never escapes).

    Args:
        elements: The document elements, in order.
        annotate: When ``True``, emit a ``<!-- hybridmd: table ... -->`` marker on
            its own line immediately before each table (the marker and its table
            form one block). The marker reports ``format`` (``md``/``html``/
            ``text``) and ``reasons`` — the analyzer :class:`~hybridmd.analyzer.
            Reason` values in declaration order, ``none`` when the analyzer found
            none, or ``no_html`` for a text fallback. When ``force`` is set,
            ``format`` reflects what was actually emitted and ``forced=true`` is
            added; the analyzer still runs, so ``reasons`` keeps reporting the real
            verdict — which is what makes the lossy ``force="md"`` arm
            self-documenting (the marker records exactly which tables it mangled).
        force: Override the analyzer for every table with usable HTML: ``"md"``
            forces a Markdown pipe table, ``"html"`` forces sanitized HTML. The
            analyzer still runs and its reasons are still reported (see
            ``annotate``); ``force`` only changes what is emitted.
            **``force="md"`` is explicitly lossy** — it can mangle tables the
            analyzer would have kept as HTML, and exists for benchmarking, not
            production. ``force`` does not affect the text fallback paths.

    Returns:
        The assembled document: blocks joined by a single blank line, with exactly
        one trailing newline and no leading whitespace. An empty *elements*
        sequence yields the empty string.
    """
    blocks: list[str] = []
    for el in elements:
        if el.type is ElementType.TABLE:
            table = _render_table(el, force)
            block = f"{_marker(table)}\n{table.body}" if annotate else table.body
        else:
            block = element_to_markdown(el)
        blocks.append(block)
    return ("\n\n".join(blocks) + "\n") if blocks else ""
