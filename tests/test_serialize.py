"""Tests for the Markdown and sanitized-HTML serializers."""

from __future__ import annotations

import pytest

from hybridmd import (
    DocElement,
    ElementType,
    element_to_markdown,
    sanitize_table_html,
    table_to_markdown,
)


def test_reexported_from_package_root() -> None:
    from hybridmd import serialize

    assert table_to_markdown is serialize.table_to_markdown
    assert sanitize_table_html is serialize.sanitize_table_html
    assert element_to_markdown is serialize.element_to_markdown


# --- table_to_markdown ------------------------------------------------------


def test_pipe_characters_are_escaped() -> None:
    html = (
        "<table><tr><th>a|b</th><th>c</th></tr><tr><td>d</td><td>e|f</td></tr></table>"
    )
    assert table_to_markdown(html) == ("| a\\|b | c |\n| --- | --- |\n| d | e\\|f |")


def test_header_taken_from_thead() -> None:
    html = (
        "<table><thead><tr><th>H1</th><th>H2</th></tr></thead>"
        "<tbody><tr><td>a</td><td>b</td></tr></tbody></table>"
    )
    assert table_to_markdown(html) == "| H1 | H2 |\n| --- | --- |\n| a | b |"


def test_header_taken_from_first_row_without_thead() -> None:
    html = "<table><tr><td>c1</td><td>c2</td></tr><tr><td>a</td><td>b</td></tr></table>"
    assert table_to_markdown(html) == "| c1 | c2 |\n| --- | --- |\n| a | b |"


def test_internal_whitespace_is_collapsed() -> None:
    html = "<table><tr><td>  a\n  b   c  </td><td>d</td></tr></table>"
    assert table_to_markdown(html) == "| a b c | d |\n| --- | --- |"


def test_empty_cells_are_allowed() -> None:
    html = "<table><tr><td></td><td>b</td></tr></table>"
    assert table_to_markdown(html) == "|  | b |\n| --- | --- |"


def test_delimiter_row_matches_header_width() -> None:
    html = "<table><tr><th>a</th><th>b</th><th>c</th></tr></table>"
    lines = table_to_markdown(html).split("\n")
    assert lines[1] == "| --- | --- | --- |"


def test_table_to_markdown_requires_a_table() -> None:
    with pytest.raises(ValueError, match="<table>"):
        table_to_markdown("<div>nope</div>")


# --- sanitize_table_html ----------------------------------------------------


def test_whitelist_strips_disallowed_attributes() -> None:
    html = (
        '<table class="x" id="y"><tr onclick="evil()">'
        '<td colspan="2" style="color:red" rowspan="3">a</td></tr></table>'
    )
    out = sanitize_table_html(html)
    assert "class=" not in out
    assert "id=" not in out
    assert "onclick=" not in out
    assert "style=" not in out
    assert 'colspan="2"' in out
    assert 'rowspan="3"' in out


def test_whitelist_preserves_all_structural_tags() -> None:
    # Positive side of the whitelist: every allowed structural tag must survive
    # (not be unwrapped). Guards against a regression that drops caption/thead/
    # tbody from the allow-list.
    html = (
        "<table><caption>C</caption>"
        "<thead><tr><th>h</th></tr></thead>"
        "<tbody><tr><td>x</td></tr></tbody></table>"
    )
    assert sanitize_table_html(html) == html


def test_script_and_style_contents_are_dropped() -> None:
    html = (
        "<table><tr><td>"
        "<script>alert(1)</script>keep<style>.x{color:red}</style>"
        "</td></tr></table>"
    )
    out = sanitize_table_html(html)
    assert "alert" not in out
    assert "script" not in out
    assert "style" not in out
    assert ".x{color:red}" not in out
    assert "keep" in out


def test_nested_formatting_tags_are_unwrapped_text_preserved() -> None:
    html = "<table><tr><td><b>bold</b> and <i>italic</i></td></tr></table>"
    out = sanitize_table_html(html)
    assert "<b>" not in out
    assert "<i>" not in out
    assert "bold and italic" in out


def test_span_values_preserved_verbatim_not_reparsed() -> None:
    # "2abc" parses to a span of 2, but sanitized HTML must keep it verbatim.
    html = '<table><tr><td colspan="2abc">a</td></tr></table>'
    out = sanitize_table_html(html)
    assert 'colspan="2abc"' in out


def test_whitespace_between_tags_is_compacted() -> None:
    html = "<table>\n  <tr>\n    <td>a</td>\n  </tr>\n</table>"
    assert sanitize_table_html(html) == "<table><tr><td>a</td></tr></table>"


def test_comments_are_removed() -> None:
    html = "<table><tr><td><!-- secret -->a</td></tr></table>"
    out = sanitize_table_html(html)
    assert "secret" not in out
    assert "<!--" not in out
    assert "a" in out


def test_sanitize_requires_a_table() -> None:
    with pytest.raises(ValueError, match="<table>"):
        sanitize_table_html("<div>nope</div>")


# --- element_to_markdown ----------------------------------------------------


def test_heading_uses_level() -> None:
    el = DocElement(ElementType.HEADING, "Title", level=3)
    assert element_to_markdown(el) == "### Title"


def test_heading_defaults_to_level_one_when_none() -> None:
    el = DocElement(ElementType.HEADING, "Title")
    assert element_to_markdown(el) == "# Title"


@pytest.mark.parametrize(
    ("level", "expected"),
    [(0, "# Title"), (None, "# Title"), (7, "###### Title"), (6, "###### Title")],
)
def test_heading_level_is_clamped(level: int | None, expected: str) -> None:
    el = DocElement(ElementType.HEADING, "Title", level=level)
    assert element_to_markdown(el) == expected


def test_paragraph_is_plain_text() -> None:
    assert element_to_markdown(DocElement(ElementType.PARAGRAPH, "hello")) == "hello"


def test_other_is_plain_text() -> None:
    assert element_to_markdown(DocElement(ElementType.OTHER, "misc")) == "misc"


def test_list_item_is_prefixed() -> None:
    assert element_to_markdown(DocElement(ElementType.LIST_ITEM, "item")) == "- item"


def test_code_is_fenced() -> None:
    el = DocElement(ElementType.CODE, "print(1)")
    assert element_to_markdown(el) == "```\nprint(1)\n```"


def test_table_element_raises() -> None:
    el = DocElement(ElementType.TABLE, "", html="<table></table>")
    with pytest.raises(ValueError, match="element_to_markdown"):
        element_to_markdown(el)
