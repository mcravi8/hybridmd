"""Extractor-agnostic internal representation for document elements.

This module defines the small, backend-neutral schema that sits between
document extractors (Unstructured, Docling, and future backends) and the
Markdown/HTML router. Keeping this representation independent of any specific
extractor is the seam that lets the router stay decoupled from where elements
came from: a backend adapter is responsible for producing :class:`DocElement`
instances, and everything downstream depends only on this module — never on a
backend's own types.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ElementType(str, Enum):
    """The kind of a parsed document element.

    Members are ``str``-valued so the enum serializes transparently to JSON and
    compares equal to its wire value (e.g. ``ElementType.HEADING == "heading"``).
    The string value is the stable identifier used by :meth:`DocElement.to_dict`
    and :meth:`DocElement.from_dict`.
    """

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    CODE = "code"
    OTHER = "other"


@dataclass(frozen=True)
class DocElement:
    """A single parsed document element in the extractor-agnostic schema.

    Instances are immutable (:func:`dataclasses.dataclass` with ``frozen=True``)
    so they can be passed across the pipeline without defensive copying.

    Attributes:
        type: The :class:`ElementType` classifying this element.
        text: The element's plain-text content. Always present; for tables this
            is a best-effort text rendering while :attr:`html` carries structure.
        html: Structural HTML for the element, populated by a backend only when
            it provides it — in practice for tables whose structure (merged
            cells, nesting, ragged rows) plain Markdown cannot represent.
            ``None`` when no structural HTML is available.
        level: Nesting depth for hierarchical elements such as headings
            (e.g. ``1`` for a top-level heading). ``None`` when not applicable.
        metadata: Free-form, backend-specific key/value data. Each instance gets
            a fresh empty ``dict`` via ``default_factory``; a bare mutable
            default (``{}``) would be shared by every instance and silently
            defeat this frozen dataclass's per-instance guarantees, so it is
            deliberately avoided.
    """

    type: ElementType
    text: str
    html: str | None = None
    level: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable ``dict`` representation of this element.

        ``type`` is emitted as its string value, and ``metadata`` is shallow
        copied so mutating the returned mapping cannot affect this (frozen)
        instance.

        Returns:
            A mapping with the keys ``type``, ``text``, ``html``, ``level`` and
            ``metadata``.
        """
        return {
            "type": self.type.value,
            "text": self.text,
            "html": self.html,
            "level": self.level,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DocElement:
        """Build a :class:`DocElement` from a mapping (e.g. decoded JSON).

        Args:
            data: A mapping with at least ``type`` and ``text`` keys. ``html``,
                ``level`` and ``metadata`` are optional and fall back to their
                field defaults when absent.

        Returns:
            The reconstructed :class:`DocElement`. Its ``metadata`` is copied so
            the new instance does not alias ``data``.

        Raises:
            ValueError: If ``type`` is not one of the known
                :class:`ElementType` values.
            KeyError: If a required key (``type`` or ``text``) is missing.
        """
        raw_type = data["type"]
        try:
            element_type = ElementType(raw_type)
        except ValueError as exc:
            valid = ", ".join(repr(member.value) for member in ElementType)
            raise ValueError(
                f"Unknown element type {raw_type!r}; expected one of: {valid}"
            ) from exc

        raw_metadata = data.get("metadata")
        metadata: dict[str, Any] = dict(raw_metadata) if raw_metadata else {}

        return cls(
            type=element_type,
            text=data["text"],
            html=data.get("html"),
            level=data.get("level"),
            metadata=metadata,
        )
