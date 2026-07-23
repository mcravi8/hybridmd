"""Adapter from Unstructured (unstructured.io) elements to :class:`DocElement`.

The ``unstructured`` package is **never imported here**. Inputs are read purely by
duck typing, so this adapter — and hybridmd's core CI — require no such
dependency; the ``hybridmd[unstructured]`` extra is needed only to *produce* the
inputs. Both native ``Element`` objects and the plain dicts returned by the
Unstructured API (``elements_to_dicts``) are accepted; a single shape-agnostic
accessor (:func:`_get`) reads either, so the category mapping is defined once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from hybridmd.schema import DocElement, ElementType

_MIN_LEVEL = 1
_MAX_LEVEL = 6

# Unstructured category -> our element type. Anything absent maps to OTHER (never
# dropped silently); Header/Footer/PageBreak are page furniture and are skipped.
_CATEGORY_TO_TYPE: dict[str, ElementType] = {
    "Title": ElementType.HEADING,
    "NarrativeText": ElementType.PARAGRAPH,
    "UncategorizedText": ElementType.PARAGRAPH,
    "Address": ElementType.PARAGRAPH,
    "FigureCaption": ElementType.PARAGRAPH,
    "ListItem": ElementType.LIST_ITEM,
    "Table": ElementType.TABLE,
    "CodeSnippet": ElementType.CODE,
}
_SKIP_CATEGORIES = frozenset({"Header", "Footer", "PageBreak"})


def _get(el: Any, obj_attr: str, dict_key: str, *, meta: bool = False) -> Any:
    """Read one field from an unstructured ``Element`` *or* its plain-dict form.

    This is the single seam that lets the rest of the adapter stay shape-agnostic.
    ``meta=True`` reads from the element's ``metadata`` sub-object/sub-dict;
    missing fields (or a missing/blank ``metadata``) resolve to ``None``.
    """
    container: Any = el
    if meta:
        container = (
            el.get("metadata")
            if isinstance(el, Mapping)
            else getattr(el, "metadata", None)
        )
    if isinstance(container, Mapping):
        return container.get(dict_key)
    return getattr(container, obj_attr, None)


def _category(el: Any) -> str | None:
    """The element's category: ``.category`` / ``"type"``, else its class name.

    Objects fall back to ``type(el).__name__`` (Unstructured's element classes are
    named after their category). Dicts have no such fallback; a dict lacking a
    ``"type"`` resolves to ``None`` and is treated as an unrecognized category.
    """
    category = _get(el, "category", "type")
    if category is None and not isinstance(el, Mapping):
        category = type(el).__name__
    return str(category) if category is not None else None


def _heading_level(depth: Any) -> int:
    """Heading level from ``category_depth``: ``depth + 1`` clamped to 1-6.

    Absent or non-integer depth (``bool`` is not accepted as an integer here)
    defaults to the top level, 1.
    """
    if isinstance(depth, bool) or not isinstance(depth, int):
        return _MIN_LEVEL
    return min(max(depth + 1, _MIN_LEVEL), _MAX_LEVEL)


def from_unstructured(elements: Iterable[Any]) -> list[DocElement]:
    """Convert Unstructured elements (objects or API dicts) to ``DocElement``.

    Category mapping:

    * ``Title`` -> HEADING (``level = category_depth + 1`` clamped to 1-6,
      default 1 when absent).
    * ``NarrativeText`` / ``UncategorizedText`` / ``Address`` /
      ``FigureCaption`` -> PARAGRAPH.
    * ``ListItem`` -> LIST_ITEM.
    * ``Table`` -> TABLE (``html`` = ``text_as_html`` when present and non-blank,
      else ``None``).
    * ``CodeSnippet`` -> CODE.
    * ``Header`` / ``Footer`` / ``PageBreak`` -> skipped (page furniture).
    * Any unrecognized category -> OTHER (never dropped silently).

    Elements whose text is blank/whitespace-only are dropped, **except** tables
    that carry usable ``html``. ``page_number`` and ``filename`` are preserved in
    :attr:`DocElement.metadata` when present (the keys are omitted when absent) —
    page provenance downstream financial-document citation needs, kept at its
    cheapest source.

    Args:
        elements: An iterable of Unstructured ``Element`` objects and/or the
            plain dicts from the Unstructured API. The two shapes may be mixed.

    Returns:
        The converted elements, in input order, with skipped elements omitted.
    """
    result: list[DocElement] = []
    for el in elements:
        category = _category(el)
        if category in _SKIP_CATEGORIES:
            continue  # page furniture: Header / Footer / PageBreak

        element_type = (
            _CATEGORY_TO_TYPE.get(category, ElementType.OTHER)
            if category is not None
            else ElementType.OTHER
        )

        raw_text = _get(el, "text", "text")
        text = raw_text if isinstance(raw_text, str) else ""

        html: str | None = None
        if element_type is ElementType.TABLE:
            raw_html = _get(el, "text_as_html", "text_as_html", meta=True)
            if isinstance(raw_html, str) and raw_html.strip():
                html = raw_html

        # Drop blank-text elements, except tables that carry usable html.
        table_with_html = element_type is ElementType.TABLE and html is not None
        if not text.strip() and not table_with_html:
            continue

        level = (
            _heading_level(_get(el, "category_depth", "category_depth", meta=True))
            if element_type is ElementType.HEADING
            else None
        )

        metadata: dict[str, Any] = {}
        page_number = _get(el, "page_number", "page_number", meta=True)
        if page_number is not None:
            metadata["page_number"] = page_number
        filename = _get(el, "filename", "filename", meta=True)
        if filename is not None:
            metadata["filename"] = filename

        result.append(
            DocElement(
                type=element_type,
                text=text,
                html=html,
                level=level,
                metadata=metadata,
            )
        )
    return result
