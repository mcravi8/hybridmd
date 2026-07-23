"""Core decision logic: can a table be represented losslessly in Markdown?

Markdown pipe tables can only express a rectangular grid of single, inline-only
cells with a single header row. This module inspects a table's HTML and reports
the concrete structural reasons (if any) it exceeds that — the signal the router
uses to decide between emitting a Markdown pipe table and falling back to
embedded, sanitized HTML.

The analysis is deliberately conservative and self-contained: it depends only on
``beautifulsoup4`` and operates purely on structure, never on styling.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bs4 import BeautifulSoup, Tag

# Block-level tags whose presence in a cell defeats an inline Markdown cell.
_BLOCK_TAGS = ["p", "ul", "ol", "div"]


class Reason(str, Enum):
    """Why a table cannot be represented with Markdown pipe syntax.

    Members are ``str``-valued so they serialize transparently to JSON. The
    *declaration order below is significant*: :attr:`TableAnalysis.reasons` is
    always ordered by it, never by the order in which reasons are discovered.
    """

    MERGED_CELLS = "merged_cells"
    NESTED_TABLE = "nested_table"
    RAGGED_ROWS = "ragged_rows"
    MULTI_ROW_HEADER = "multi_row_header"
    BLOCK_CONTENT = "block_content"


@dataclass(frozen=True)
class TableAnalysis:
    """The verdict for a single table.

    Attributes:
        needs_html: ``True`` iff at least one :class:`Reason` was found — i.e.
            Markdown pipe syntax would be lossy and the table must fall back to
            embedded HTML.
        reasons: The reasons the table needs HTML, as a tuple in :class:`Reason`
            *declaration order* (deterministic, never discovery order). Empty
            iff ``needs_html`` is ``False``.
    """

    needs_html: bool
    reasons: tuple[Reason, ...]


def _parse_span(raw: object) -> int:
    """Resolve a ``colspan``/``rowspan`` attribute to an effective span (>= 1).

    Extractor output is frequently malformed, so this never raises. Any value
    that is not a base-10 integer greater than one resolves to ``1`` (i.e. *not*
    merged): non-string, empty, whitespace-only, non-numeric, float-like, zero
    and negative values all collapse to ``1``. Surrounding whitespace is
    stripped before parsing.
    """
    if not isinstance(raw, str):
        return 1
    try:
        value = int(raw.strip())
    except ValueError:
        return 1
    return max(value, 1)


def _nearest_table(element: Tag) -> Tag | None:
    """Return the closest ancestor ``<table>`` of *element*, or ``None``."""
    for parent in element.parents:
        if isinstance(parent, Tag) and parent.name == "table":
            return parent
    return None


def _find_tags(root: Tag, names: list[str]) -> list[Tag]:
    """All descendant tags of *root* whose name is in *names* (Tags only)."""
    return [node for node in root.find_all(names) if isinstance(node, Tag)]


def _owned(nodes: list[Tag], target: Tag) -> list[Tag]:
    """Keep only *nodes* whose nearest ancestor table is *target*.

    This is what stops a nested table's own structure from leaking into the
    outer table's analysis: cells, rows and content inside a nested table have
    that nested table — not *target* — as their nearest table ancestor.
    """
    return [node for node in nodes if _nearest_table(node) is target]


def analyze_table(html: str) -> TableAnalysis:
    """Analyze the first ``<table>`` in *html* for Markdown representability.

    Precondition:
        Operates on the **first ``<table>`` in document order**, which is
        necessarily top-level (any enclosing table would appear earlier in the
        document). Any other top-level tables in the input are ignored. Raises
        :class:`ValueError` if the input contains no ``<table>`` element.

    Parsing uses BeautifulSoup with the built-in ``html.parser`` backend.

    Detection rules — each reason is recorded only for the target table's *own*
    structure; a nested table is considered solely insofar as its presence
    triggers :attr:`Reason.NESTED_TABLE`:

    * ``MERGED_CELLS`` — any ``td``/``th`` with ``colspan`` or ``rowspan``
      resolving to > 1 (see :func:`_parse_span` for the defensive policy).
    * ``NESTED_TABLE`` — a ``<table>`` nested inside a cell of the target.
    * ``MULTI_ROW_HEADER`` — a ``<thead>`` containing more than one ``<tr>``.
    * ``BLOCK_CONTENT`` — any cell containing ``p``, ``ul``, ``ol``, ``div`` or
      more than one ``<br>``.
    * ``RAGGED_ROWS`` — *only when no merged cells are present* — rows (``thead``
      and ``tbody`` counted together) with differing cell counts.

    Args:
        html: A fragment or document containing at least one ``<table>``.

    Returns:
        A :class:`TableAnalysis`. ``needs_html`` is ``True`` iff ``reasons`` is
        non-empty; ``reasons`` is ordered by :class:`Reason` declaration order.

    Raises:
        ValueError: If *html* contains no ``<table>`` element.
    """
    target = BeautifulSoup(html, "html.parser").find("table")
    if not isinstance(target, Tag):
        raise ValueError("analyze_table requires input containing a <table> element")

    cells = _owned(_find_tags(target, ["td", "th"]), target)
    rows = _owned(_find_tags(target, ["tr"]), target)

    detected: set[Reason] = set()

    merged = any(
        _parse_span(cell.get("colspan")) > 1 or _parse_span(cell.get("rowspan")) > 1
        for cell in cells
    )
    if merged:
        detected.add(Reason.MERGED_CELLS)

    if any(isinstance(cell.find("table"), Tag) for cell in cells):
        detected.add(Reason.NESTED_TABLE)

    for thead in _owned(_find_tags(target, ["thead"]), target):
        if len(_owned(_find_tags(thead, ["tr"]), target)) > 1:
            detected.add(Reason.MULTI_ROW_HEADER)
            break

    for cell in cells:
        blocks = _owned(_find_tags(cell, _BLOCK_TAGS), target)
        line_breaks = _owned(_find_tags(cell, ["br"]), target)
        if blocks or len(line_breaks) > 1:
            detected.add(Reason.BLOCK_CONTENT)
            break

    if not merged:
        widths = {len(_owned(_find_tags(row, ["td", "th"]), target)) for row in rows}
        if len(widths) > 1:
            detected.add(Reason.RAGGED_ROWS)

    reasons = tuple(reason for reason in Reason if reason in detected)
    return TableAnalysis(needs_html=bool(reasons), reasons=reasons)
