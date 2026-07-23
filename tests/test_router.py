"""Golden-string tests for the hybrid-document router (the package entry point).

Each test asserts the exact, full ``render`` output — never a substring — so the
deterministic assembly (block separation, trailing newline, annotation markers,
and force overrides) is pinned byte-for-byte.
"""

from __future__ import annotations

from hybridmd import DocElement, ElementType, render

# --- fixtures ---------------------------------------------------------------

HEADING = DocElement(ElementType.HEADING, "Report", level=1)
PARAGRAPH = DocElement(ElementType.PARAGRAPH, "Revenue rose.")
LIST_ITEM = DocElement(ElementType.LIST_ITEM, "Churn up")
SIMPLE_TABLE = DocElement(
    ElementType.TABLE,
    "Q Rev\nUS 10",
    html=(
        "<table><thead><tr><th>Q</th><th>Rev</th></tr></thead>"
        "<tbody><tr><td>US</td><td>10</td></tr></tbody></table>"
    ),
)
MERGED_TABLE = DocElement(
    ElementType.TABLE,
    "Region\nUS 10",
    html=(
        '<table><tr><td colspan="2">Region</td></tr>'
        "<tr><td>US</td><td>10</td></tr></table>"
    ),
)
NO_HTML_TABLE = DocElement(ElementType.TABLE, "plain fallback", html=None)
NO_TABLE_TAG = DocElement(
    ElementType.TABLE, "just a div", html="<div>no table here</div>"
)

MIXED = [HEADING, PARAGRAPH, LIST_ITEM, SIMPLE_TABLE, MERGED_TABLE]


def test_reexported_from_package_root() -> None:
    from hybridmd import router

    assert render is router.render


def test_mixed_document_without_annotations() -> None:
    # Simple table -> pipe table; merged-cell table -> sanitized HTML.
    assert render(MIXED) == (
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


def test_mixed_document_with_annotations() -> None:
    # Each table gets a marker on its own line, joined to its table by a single
    # newline; format=md -> reasons=none, format=html -> declaration-order reasons.
    assert render(MIXED, annotate=True) == (
        "# Report\n"
        "\n"
        "Revenue rose.\n"
        "\n"
        "- Churn up\n"
        "\n"
        "<!-- hybridmd: table format=md reasons=none -->\n"
        "| Q | Rev |\n"
        "| --- | --- |\n"
        "| US | 10 |\n"
        "\n"
        "<!-- hybridmd: table format=html reasons=merged_cells -->\n"
        '<table><tr><td colspan="2">Region</td></tr>'
        "<tr><td>US</td><td>10</td></tr></table>\n"
    )


def test_force_md_is_lossy_and_reports_real_reasons() -> None:
    # force="md" overrides the analyzer on the merged table: the colspan header
    # collapses to one column over a two-column body — explicitly lossy. The
    # marker still reports the analyzer's real reasons (merged_cells), so the
    # lossy arm records exactly which tables it mangled.
    assert render([MERGED_TABLE], annotate=True, force="md") == (
        "<!-- hybridmd: table format=md reasons=merged_cells forced=true -->\n"
        "| Region |\n"
        "| --- |\n"
        "| US | 10 |\n"
    )


def test_force_html_on_simple_table_reports_no_reasons() -> None:
    # Simple table has no analyzer reasons → reasons=none even when forced to html.
    assert render([SIMPLE_TABLE], annotate=True, force="html") == (
        "<!-- hybridmd: table format=html reasons=none forced=true -->\n"
        "<table><thead><tr><th>Q</th><th>Rev</th></tr></thead>"
        "<tbody><tr><td>US</td><td>10</td></tr></tbody></table>\n"
    )


def test_force_html_reports_analyzer_reasons() -> None:
    # The analyzer runs even when forcing html: reasons are reported regardless.
    assert render([MERGED_TABLE], annotate=True, force="html") == (
        "<!-- hybridmd: table format=html reasons=merged_cells forced=true -->\n"
        '<table><tr><td colspan="2">Region</td></tr>'
        "<tr><td>US</td><td>10</td></tr></table>\n"
    )


def test_table_with_html_none_falls_back_to_text() -> None:
    assert render([NO_HTML_TABLE], annotate=True) == (
        "<!-- hybridmd: table format=text reasons=no_html -->\nplain fallback\n"
    )


def test_table_with_html_but_no_table_tag_falls_back_to_text() -> None:
    # analyze_table raises ValueError (html present, no <table>) — must never escape.
    assert render([NO_TABLE_TAG], annotate=True) == (
        "<!-- hybridmd: table format=text reasons=no_html -->\njust a div\n"
    )


def test_empty_sequence_is_empty_string() -> None:
    assert render([]) == ""


def test_output_is_deterministic() -> None:
    assert render(MIXED, annotate=True) == render(MIXED, annotate=True)
