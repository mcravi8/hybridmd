"""Tests for the Unstructured adapter.

Uses small fakes — objects with attributes, and plain dicts — that mimic the two
shapes Unstructured produces (native ``Element`` objects and API dicts). The real
``unstructured`` package is never imported, so core CI needs no such dependency.
"""

from __future__ import annotations

from hybridmd import DocElement, ElementType, render
from hybridmd.adapters.unstructured_io import from_unstructured


class FakeMeta:
    """Stand-in for ``ElementMetadata``: attribute access, missing -> ``None``."""

    def __init__(self, **fields: object) -> None:
        for key, value in fields.items():
            setattr(self, key, value)


class FakeElement:
    """Stand-in for an unstructured ``Element`` with an explicit ``.category``."""

    def __init__(self, category: str, text: str, **meta: object) -> None:
        self.category = category
        self.text = text
        self.metadata = FakeMeta(**meta)


class Title:
    """An element object with NO ``.category`` — category comes from the class name."""

    def __init__(self, text: str, **meta: object) -> None:
        self.text = text
        self.metadata = FakeMeta(**meta)


def as_dict(category: str, text: str, **meta: object) -> dict[str, object]:
    """The plain-dict shape returned by the Unstructured API."""
    return {"type": category, "text": text, "metadata": dict(meta)}


# --- category mapping -------------------------------------------------------


def test_category_mapping_covers_every_row() -> None:
    cases = {
        "Title": ElementType.HEADING,
        "NarrativeText": ElementType.PARAGRAPH,
        "UncategorizedText": ElementType.PARAGRAPH,
        "Address": ElementType.PARAGRAPH,
        "FigureCaption": ElementType.PARAGRAPH,
        "ListItem": ElementType.LIST_ITEM,
        "Table": ElementType.TABLE,
        "CodeSnippet": ElementType.CODE,
    }
    for category, expected in cases.items():
        (out,) = from_unstructured([FakeElement(category, "content")])
        assert out.type is expected


def test_page_furniture_is_skipped() -> None:
    els = [
        FakeElement("Header", "confidential"),
        FakeElement("Footer", "page 1"),
        FakeElement("PageBreak", ""),
    ]
    assert from_unstructured(els) == []


def test_unknown_category_maps_to_other() -> None:
    (out,) = from_unstructured([FakeElement("SomethingWeird", "content")])
    assert out.type is ElementType.OTHER
    assert out.text == "content"


def test_dict_without_type_maps_to_other() -> None:
    (out,) = from_unstructured([{"text": "content", "metadata": {}}])
    assert out.type is ElementType.OTHER


def test_object_category_falls_back_to_class_name() -> None:
    (out,) = from_unstructured([Title("Heading via class name")])
    assert out.type is ElementType.HEADING
    assert out.text == "Heading via class name"


# --- object vs dict parity --------------------------------------------------


def test_object_and_dict_produce_identical_elements() -> None:
    obj = FakeElement(
        "Title", "Heading", category_depth=1, page_number=3, filename="f.pdf"
    )
    dct = as_dict("Title", "Heading", category_depth=1, page_number=3, filename="f.pdf")
    expected = [
        DocElement(
            ElementType.HEADING,
            "Heading",
            level=2,
            metadata={"page_number": 3, "filename": "f.pdf"},
        )
    ]
    assert from_unstructured([obj]) == expected
    assert from_unstructured([dct]) == expected


# --- category_depth -> level ------------------------------------------------


def test_category_depth_absent_defaults_to_one() -> None:
    (out,) = from_unstructured([FakeElement("Title", "T")])
    assert out.level == 1


def test_category_depth_zero_is_level_one() -> None:
    (out,) = from_unstructured([FakeElement("Title", "T", category_depth=0)])
    assert out.level == 1


def test_category_depth_one_is_level_two() -> None:
    (out,) = from_unstructured([FakeElement("Title", "T", category_depth=1)])
    assert out.level == 2


def test_category_depth_out_of_range_is_clamped() -> None:
    (high,) = from_unstructured([FakeElement("Title", "T", category_depth=10)])
    (low,) = from_unstructured([FakeElement("Title", "T", category_depth=-5)])
    assert high.level == 6
    assert low.level == 1


# --- Table html -------------------------------------------------------------


def test_table_with_text_as_html() -> None:
    html = "<table><tr><td>a</td></tr></table>"
    (out,) = from_unstructured([FakeElement("Table", "a", text_as_html=html)])
    assert out == DocElement(ElementType.TABLE, "a", html=html)


def test_table_without_text_as_html_keeps_text_and_no_html() -> None:
    (out,) = from_unstructured([FakeElement("Table", "cell text")])
    assert out == DocElement(ElementType.TABLE, "cell text", html=None)


def test_table_with_blank_text_as_html_is_none() -> None:
    (out,) = from_unstructured(
        [FakeElement("Table", "fallback text", text_as_html="   ")]
    )
    assert out == DocElement(ElementType.TABLE, "fallback text", html=None)


# --- blank-text skipping ----------------------------------------------------


def test_blank_text_elements_are_skipped() -> None:
    els = [
        FakeElement("NarrativeText", "   "),
        FakeElement("ListItem", ""),
        FakeElement("Title", "\n\t"),
    ]
    assert from_unstructured(els) == []


def test_blank_text_table_with_html_is_kept() -> None:
    html = "<table><tr><td>x</td></tr></table>"
    (out,) = from_unstructured([FakeElement("Table", "", text_as_html=html)])
    assert out == DocElement(ElementType.TABLE, "", html=html)


def test_blank_text_table_without_html_is_skipped() -> None:
    assert from_unstructured([FakeElement("Table", "   ")]) == []


# --- metadata passthrough ---------------------------------------------------


def test_metadata_passthrough_present() -> None:
    (out,) = from_unstructured(
        [FakeElement("NarrativeText", "p", page_number=7, filename="doc.pdf")]
    )
    assert out.metadata == {"page_number": 7, "filename": "doc.pdf"}


def test_metadata_partial_only_present_keys() -> None:
    (out,) = from_unstructured([FakeElement("NarrativeText", "p", page_number=2)])
    assert out.metadata == {"page_number": 2}


def test_metadata_omitted_when_absent() -> None:
    (out,) = from_unstructured([FakeElement("NarrativeText", "p")])
    assert out.metadata == {}


# --- end to end -------------------------------------------------------------


def test_end_to_end_mixed_list_through_render() -> None:
    els = [
        FakeElement("Title", "Report", category_depth=0, page_number=1),
        FakeElement("NarrativeText", "Revenue rose.", page_number=1),
        FakeElement("ListItem", "Churn up"),
        FakeElement("Header", "confidential"),  # page furniture -> dropped
        FakeElement(
            "Table",
            "Q Rev\nUS 10",
            text_as_html=(
                "<table><thead><tr><th>Q</th><th>Rev</th></tr></thead>"
                "<tbody><tr><td>US</td><td>10</td></tr></tbody></table>"
            ),
        ),
        FakeElement(
            "Table",
            "Region\nUS 10",
            text_as_html=(
                '<table><tr><td colspan="2">Region</td></tr>'
                "<tr><td>US</td><td>10</td></tr></table>"
            ),
        ),
    ]
    assert render(from_unstructured(els)) == (
        "# Report\n"
        "\n"
        "Revenue rose.\n"
        "\n"
        "- Churn up\n"
        "\n"
        "| Q | Rev |\n"
        "| --- | --- |\n"
        "| US | 10 |\n"
        "\n"
        '<table><tr><td colspan="2">Region</td></tr>'
        "<tr><td>US</td><td>10</td></tr></table>\n"
    )
