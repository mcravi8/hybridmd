"""Tests for the table-complexity analyzer."""

from __future__ import annotations

import pytest

from hybridmd import Reason, TableAnalysis, analyze_table

# --- Fixtures: one table per Reason -----------------------------------------

MERGED = '<table><tr><td colspan="2">a</td></tr><tr><td>b</td><td>c</td></tr></table>'
ROWSPAN_MERGED = (
    '<table><tr><td rowspan="2">a</td><td>b</td></tr><tr><td>c</td></tr></table>'
)
NESTED = "<table><tr><td><table><tr><td>inner</td></tr></table></td></tr></table>"
RAGGED = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>"
MULTI_ROW_HEADER = (
    "<table><thead>"
    "<tr><th>a</th><th>b</th></tr>"
    "<tr><th>c</th><th>d</th></tr>"
    "</thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
)
BLOCK_PARAGRAPH = "<table><tr><td><p>a</p></td></tr></table>"
BLOCK_MULTI_BR = "<table><tr><td>a<br>b<br>c</td></tr></table>"

# A clean, fully rectangular table with a single header row.
CLEAN = (
    "<table><thead><tr><th>H1</th><th>H2</th></tr></thead>"
    "<tbody><tr><td>a</td><td>b</td></tr>"
    "<tr><td>c</td><td>d</td></tr></tbody></table>"
)
# Clean and rectangular, but with no <thead> at all.
NO_THEAD = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"


def test_reexported_from_package_root() -> None:
    from hybridmd import analyzer

    assert analyze_table is analyzer.analyze_table
    assert Reason is analyzer.Reason
    assert TableAnalysis is analyzer.TableAnalysis


def test_merged_cells_via_colspan() -> None:
    assert analyze_table(MERGED).reasons == (Reason.MERGED_CELLS,)


def test_merged_cells_via_rowspan() -> None:
    assert analyze_table(ROWSPAN_MERGED).reasons == (Reason.MERGED_CELLS,)


def test_nested_table() -> None:
    assert analyze_table(NESTED).reasons == (Reason.NESTED_TABLE,)


def test_ragged_rows() -> None:
    assert analyze_table(RAGGED).reasons == (Reason.RAGGED_ROWS,)


def test_multi_row_header() -> None:
    assert analyze_table(MULTI_ROW_HEADER).reasons == (Reason.MULTI_ROW_HEADER,)


def test_block_content_paragraph() -> None:
    assert analyze_table(BLOCK_PARAGRAPH).reasons == (Reason.BLOCK_CONTENT,)


def test_block_content_multiple_br() -> None:
    assert analyze_table(BLOCK_MULTI_BR).reasons == (Reason.BLOCK_CONTENT,)


def test_single_br_is_not_block_content() -> None:
    analysis = analyze_table("<table><tr><td>a<br>b</td></tr></table>")
    assert Reason.BLOCK_CONTENT not in analysis.reasons


def test_clean_table_needs_no_html() -> None:
    analysis = analyze_table(CLEAN)
    assert analysis.needs_html is False
    assert analysis.reasons == ()


def test_table_with_no_thead_is_clean() -> None:
    analysis = analyze_table(NO_THEAD)
    assert analysis.needs_html is False
    assert analysis.reasons == ()
    assert Reason.MULTI_ROW_HEADER not in analysis.reasons


def test_no_table_raises_value_error() -> None:
    with pytest.raises(ValueError, match="<table>"):
        analyze_table("<div>no table here</div>")


def test_empty_input_raises_value_error() -> None:
    with pytest.raises(ValueError, match="<table>"):
        analyze_table("")


def test_nested_table_inner_structure_does_not_leak() -> None:
    # The inner table has both merged cells and ragged rows; neither must
    # surface in the outer table's analysis — only NESTED_TABLE should.
    html = (
        "<table><tr><td>"
        "<table>"
        '<tr><td colspan="3">x</td></tr>'
        "<tr><td>a</td></tr>"
        "</table>"
        "</td></tr></table>"
    )
    analysis = analyze_table(html)
    assert analysis.reasons == (Reason.NESTED_TABLE,)
    assert Reason.MERGED_CELLS not in analysis.reasons
    assert Reason.RAGGED_ROWS not in analysis.reasons


@pytest.mark.parametrize(
    ("value", "is_merged"),
    [
        # Existing malformed cases — behaviour unchanged under the HTML5 rule.
        ("abc", False),
        ("", False),
        ("0", False),
        ("-1", False),
        (" 3 ", True),
        # HTML5 leading-digit-run rule: consume leading ASCII digits, drop rest.
        ("2abc", True),  # trailing garbage ignored, spans 2 columns (browser: 2)
        ("2.5", True),  # leading run "2" -> merged (was 1 under the old int())
        ("3 ", True),
        ("abc2", False),  # no leading digit -> 1
        ("1_000", False),  # underscore is not an ASCII digit; run is "1" -> 1
        ("٣", False),  # non-ASCII digit; [0-9] does not match it
    ],
)
def test_malformed_span_values(value: str, is_merged: bool) -> None:
    html = f'<table><tr><td colspan="{value}">a</td></tr></table>'
    reasons = analyze_table(html).reasons
    assert (Reason.MERGED_CELLS in reasons) is is_merged


def test_malformed_span_never_raises() -> None:
    for value in ("abc", "", "0", "-1", "2.5", " 3 ", "nan", "1e3", "٣"):
        html = f'<table><tr><td rowspan="{value}">a</td></tr></table>'
        analyze_table(html)  # must not raise


def test_reasons_ordered_by_declaration_not_discovery() -> None:
    analysis = analyze_table(_MULTI_REASON)
    declaration_index = {reason: i for i, reason in enumerate(Reason)}
    assert list(analysis.reasons) == sorted(
        analysis.reasons, key=lambda r: declaration_index[r]
    )
    # Deterministic across repeated calls.
    assert analyze_table(_MULTI_REASON).reasons == analysis.reasons


def test_multi_reason_exact_tuple() -> None:
    analysis = analyze_table(_MULTI_REASON)
    assert analysis.needs_html is True
    assert analysis.reasons == (
        Reason.MERGED_CELLS,
        Reason.NESTED_TABLE,
        Reason.MULTI_ROW_HEADER,
        Reason.BLOCK_CONTENT,
    )


def test_analysis_is_frozen() -> None:
    import dataclasses

    analysis = analyze_table(CLEAN)
    with pytest.raises(dataclasses.FrozenInstanceError):
        analysis.needs_html = True


def test_reason_values_are_plain_strings() -> None:
    # Reason subclasses str, so isinstance(..., str) is vacuous; assert the
    # concrete runtime type of the serialized value instead.
    for reason in Reason:
        assert type(reason.value) is str


# A table that triggers four reasons at once. Discovery order in the DOM (header
# first, merged+block next, nested last) differs from declaration order, so the
# output tuple proves reasons are declaration-ordered. RAGGED_ROWS is suppressed
# because merged cells are present.
_MULTI_REASON = (
    "<table>"
    "<thead>"
    "<tr><th>h1</th><th>h2</th></tr>"
    "<tr><th>h3</th><th>h4</th></tr>"
    "</thead>"
    "<tbody>"
    '<tr><td colspan="2"><p>block</p></td></tr>'
    "<tr><td>x</td><td><table><tr><td>n</td></tr></table></td></tr>"
    "</tbody>"
    "</table>"
)
