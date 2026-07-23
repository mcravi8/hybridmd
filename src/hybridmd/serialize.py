"""Output serializers: Markdown pipe tables, sanitized HTML tables, and prose.

Three output paths feed the hybrid renderer:

* :func:`table_to_markdown` — the lossless path for tables that
  :func:`hybridmd.analyzer.analyze_table` has cleared as representable.
* :func:`sanitize_table_html` — the fallback path for complex tables, reducing
  them to a tight, deterministic whitelist for safe embedding.
* :func:`element_to_markdown` — non-table prose elements.

Only ``beautifulsoup4`` is used; parsing always uses the built-in
``html.parser`` backend.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString

from hybridmd.schema import DocElement, ElementType

# Tags kept in sanitized table HTML; everything else is unwrapped.
_ALLOWED_TAGS = frozenset({"table", "thead", "tbody", "tr", "th", "td", "caption"})
# Attributes kept on those tags; everything else is dropped.
_ALLOWED_ATTRS = frozenset({"colspan", "rowspan"})
# Elements removed wholesale, including their text content.
_DROP_TAGS = ["script", "style"]

_WHITESPACE = re.compile(r"\s+")
_MIN_HEADING_LEVEL = 1
_MAX_HEADING_LEVEL = 6


def _first_table(html: str) -> Tag:
    """Parse *html* and return its first ``<table>``, or raise ``ValueError``."""
    table = BeautifulSoup(html, "html.parser").find("table")
    if not isinstance(table, Tag):
        raise ValueError("input contains no <table> element")
    return table


def _cell_text(cell: Tag) -> str:
    """Cell text with whitespace collapsed to single spaces and ``|`` escaped."""
    collapsed = " ".join(cell.get_text().split())
    return collapsed.replace("|", "\\|")


def _row_cells(row: Tag) -> list[str]:
    """The rendered text of each ``td``/``th`` in *row*, left to right."""
    return [
        _cell_text(cell) for cell in row.find_all(["td", "th"]) if isinstance(cell, Tag)
    ]


def _pipe_row(cells: list[str]) -> str:
    """Render one Markdown table row from already-escaped *cells*."""
    return "| " + " | ".join(cells) + " |"


def table_to_markdown(html: str) -> str:
    """Render a *simple* table as a GitHub-flavored Markdown pipe table.

    Precondition:
        The caller must have confirmed via
        :func:`hybridmd.analyzer.analyze_table` that ``needs_html`` is ``False``.
        Behavior on a complex table (merged cells, nesting, ragged rows,
        multi-row header, block content) is **undefined and lossy** — such
        tables must go through :func:`sanitize_table_html` instead.

    The header row is the ``<thead>``'s row if a ``<thead>`` is present,
    otherwise the first row. Cell text has surrounding whitespace stripped and
    internal whitespace collapsed to single spaces; ``|`` is escaped as ``\\|``;
    empty cells are permitted. A delimiter row matching the header's column
    count is emitted between the header and the body.

    Args:
        html: HTML containing the simple table to render.

    Returns:
        The Markdown pipe table as a newline-joined string (no trailing
        newline).

    Raises:
        ValueError: If *html* contains no ``<table>``, or the table has no rows.
    """
    table = _first_table(html)
    rows = [row for row in table.find_all("tr") if isinstance(row, Tag)]
    if not rows:
        raise ValueError("table has no rows to render")

    header_row = rows[0]
    thead = table.find("thead")
    if isinstance(thead, Tag):
        thead_row = thead.find("tr")
        if isinstance(thead_row, Tag):
            header_row = thead_row

    header_cells = _row_cells(header_row)
    body_rows = [row for row in rows if row is not header_row]

    lines = [_pipe_row(header_cells), _pipe_row(["---"] * len(header_cells))]
    lines.extend(_pipe_row(_row_cells(row)) for row in body_rows)
    return "\n".join(lines)


def sanitize_table_html(html: str) -> str:
    """Reduce a table's HTML to a tight, deterministic whitelist for embedding.

    Used for tables that cannot be represented in Markdown, where embedded HTML
    is unavoidable. The result keeps only the structural table tags
    (``table``, ``thead``, ``tbody``, ``tr``, ``th``, ``td``, ``caption``) and
    the ``colspan``/``rowspan`` attributes:

    * ``<script>`` and ``<style>`` elements are dropped entirely, contents and
      all.
    * Any other tag is unwrapped, preserving its text content (e.g. ``<b>x</b>``
      becomes ``x``).
    * Every attribute other than ``colspan``/``rowspan`` is stripped;
      ``colspan``/``rowspan`` values are preserved **verbatim** (never rewritten
      to their parsed integer).
    * HTML comments are removed and whitespace between tags is normalized so the
      output is compact and deterministic — keeping the fallback token-lean.

    Args:
        html: HTML containing the table to sanitize.

    Returns:
        The sanitized table as a compact HTML string.

    Raises:
        ValueError: If *html* contains no ``<table>``.
    """
    table = _first_table(html)

    # 1. Drop script/style elements together with their contents.
    for junk in table.find_all(_DROP_TAGS):
        junk.decompose()

    # 2. Strip attributes on the table itself, then unwrap non-whitelisted
    #    descendants (preserving their text) and clean the whitelisted ones.
    _strip_attrs(table)
    for tag in list(table.find_all(True)):
        if not isinstance(tag, Tag):
            continue
        if tag.name in _ALLOWED_TAGS:
            _strip_attrs(tag)
        else:
            tag.unwrap()

    # 3. Normalize text: drop comments, remove whitespace-only nodes between
    #    tags, and collapse internal whitespace runs to a single space.
    for node in list(table.descendants):
        if not isinstance(node, NavigableString):
            continue
        if isinstance(node, Comment):
            node.extract()
            continue
        collapsed = _WHITESPACE.sub(" ", str(node))
        if collapsed.strip():
            node.replace_with(collapsed)
        else:
            node.extract()

    return str(table)


def _strip_attrs(tag: Tag) -> None:
    """Keep only whitelisted attributes on *tag*, preserving their values."""
    tag.attrs = {
        key: value for key, value in tag.attrs.items() if key in _ALLOWED_ATTRS
    }


def element_to_markdown(el: DocElement) -> str:
    """Render a non-table :class:`~hybridmd.schema.DocElement` as Markdown.

    * ``HEADING`` — ``#`` repeated ``level`` times (clamped to 1-6, defaulting
      to 1 when ``level`` is ``None``) followed by the text.
    * ``PARAGRAPH`` and ``OTHER`` — the plain text.
    * ``LIST_ITEM`` — the text with a ``"- "`` prefix.
    * ``CODE`` — the text in a fenced code block delimited by ```` ``` ````.

    Args:
        el: The element to render.

    Returns:
        The Markdown rendering of *el*.

    Raises:
        ValueError: If ``el.type`` is ``TABLE`` — tables are rendered by
            :func:`table_to_markdown` or :func:`sanitize_table_html`, not here.
    """
    if el.type is ElementType.HEADING:
        raw_level = el.level if el.level is not None else _MIN_HEADING_LEVEL
        level = min(max(raw_level, _MIN_HEADING_LEVEL), _MAX_HEADING_LEVEL)
        return f"{'#' * level} {el.text}"
    if el.type is ElementType.LIST_ITEM:
        return f"- {el.text}"
    if el.type is ElementType.CODE:
        return f"```\n{el.text}\n```"
    if el.type is ElementType.TABLE:
        raise ValueError(
            "TABLE elements are rendered via table_to_markdown or "
            "sanitize_table_html, not element_to_markdown"
        )
    return el.text
