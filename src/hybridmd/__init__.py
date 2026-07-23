"""hybridmd — convert parsed document elements into hybrid Markdown output.

The library emits Markdown wherever it is lossless and falls back to embedded,
sanitized HTML only for tables whose structure (merged cells, nesting, ragged
rows) plain Markdown cannot represent.
"""

from __future__ import annotations

from hybridmd.schema import DocElement, ElementType

__version__ = "0.0.1"

__all__ = ["DocElement", "ElementType", "__version__"]
