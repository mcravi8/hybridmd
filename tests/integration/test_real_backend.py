"""Integration tests that exercise the REAL Unstructured backend.

Every other test in this suite stands the backend up out of fakes. That is what
keeps the core package and its CI dependency-free, and it is the right default —
but it also means the backend's actual behaviour went entirely unexercised, so
nothing anywhere caught the fact that the CLI was asking it for a strategy that
silently discards tables. These tests close that gap from the other side.

They are skipped unless the optional extras are installed, so core CI stays
lean::

    pip install -e ".[dev,unstructured,unstructured-pptx]"
    pytest -m integration
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hybridmd import ElementType, Reason, analyze_table, render
from hybridmd.adapters.unstructured_io import from_unstructured

pytestmark = pytest.mark.integration

partition = pytest.importorskip(
    "unstructured.partition.auto",
    reason='needs the backend: pip install "hybridmd[unstructured]"',
).partition


SIMPLE_TABLE_HTML = """
<html><body>
<h1>Quarterly Report</h1>
<p>Revenue rose.</p>
<table>
  <thead><tr><th>Region</th><th>Revenue</th></tr></thead>
  <tbody>
    <tr><td>North America</td><td>412</td></tr>
    <tr><td>Europe</td><td>256</td></tr>
  </tbody>
</table>
</body></html>
"""

MERGED_TABLE_HTML = """
<html><body>
<table>
  <thead>
    <tr><th rowspan="2">Segment</th><th colspan="2">FY2025</th></tr>
    <tr><th>Q3</th><th>Q4</th></tr>
  </thead>
  <tbody><tr><td>North America</td><td>412</td><td>438</td></tr></tbody>
</table>
</body></html>
"""


def _tables(elements: list[object]) -> list[object]:
    return [el for el in from_unstructured(elements) if el.type is ElementType.TABLE]


def _partition_html(tmp_path: Path, html: str) -> list[object]:
    path = tmp_path / "doc.html"
    path.write_text(html, encoding="utf-8")
    return partition(filename=str(path), strategy="hi_res", infer_table_structure=True)


def test_real_backend_yields_a_table_element_with_html(tmp_path) -> None:
    (table,) = _tables(_partition_html(tmp_path, SIMPLE_TABLE_HTML))
    assert table.html is not None
    assert "<table" in table.html


def test_simple_real_table_routes_to_markdown(tmp_path) -> None:
    elements = from_unstructured(_partition_html(tmp_path, SIMPLE_TABLE_HTML))
    out = render(elements, annotate=True)
    assert "format=md" in out
    assert "| North America | 412 |" in out


def test_merged_real_table_does_not_come_out_as_pipes(tmp_path) -> None:
    # The whole reason this project exists: a table the backend really produced,
    # carrying structure Markdown cannot hold, must not come out as pipes.
    #
    # Note what is NOT asserted here — that the reason is MERGED_CELLS. It is
    # not, because of the upstream behaviour pinned by the test below: this
    # table reaches the analyzer with its spans already gone, and is caught as
    # RAGGED_ROWS instead. The routing is right; the margin is thinner than it
    # looks.
    (table,) = _tables(_partition_html(tmp_path, MERGED_TABLE_HTML))
    assert table.html is not None
    assert analyze_table(table.html).needs_html is True

    out = render([table], annotate=True)
    assert "format=html" in out
    assert "<table" in out


def test_html_partitioner_strips_spans_before_hybridmd_sees_them(tmp_path) -> None:
    """Pin an upstream behaviour that quietly undercuts the analyzer.

    Unstructured's *HTML* partitioner rewrites tables into bare
    ``<tr><td>`` grids: ``colspan``/``rowspan`` are dropped and ``thead``/``th``
    are flattened to ``td``. Merged cells therefore cannot be detected on this
    path — the evidence is destroyed upstream of the analyzer, which is a very
    different thing from the analyzer missing it.

    Here the collapse happens to leave ragged rows, so the table is still routed
    to HTML. That is luck, not design: a merge that collapsed into a uniform grid
    would look perfectly simple and be emitted as lossless Markdown.

    The PDF ``hi_res`` path does *not* share this flaw — its table-structure
    model emits real ``colspan``/``rowspan`` — so this is specific to HTML input.
    If a future version starts preserving spans, this test fails and should be
    deleted, gladly.
    """
    (table,) = _tables(_partition_html(tmp_path, MERGED_TABLE_HTML))
    assert table.html is not None
    assert "colspan" not in table.html
    assert "rowspan" not in table.html
    assert Reason.MERGED_CELLS not in analyze_table(table.html).reasons


def test_pptx_table_is_detected_and_rendered(tmp_path) -> None:
    # Settles an open question: Unstructured's pptx partitioner *does* promote a
    # native PowerPoint table to the Table category with usable text_as_html,
    # the same as its PDF/DOCX paths. A deck that yields no tables genuinely has
    # none, rather than having them quietly dropped on the way through.
    pptx = pytest.importorskip(
        "pptx", reason='needs pip install "hybridmd[unstructured-pptx]"'
    )
    path = tmp_path / "deck.pptx"
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    shape = slide.shapes.add_table(
        2,
        2,
        pptx.util.Inches(1),
        pptx.util.Inches(2),
        pptx.util.Inches(6),
        pptx.util.Inches(1),
    )
    rows = [["Segment", "FY2025"], ["North America", "412"]]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            shape.table.cell(r, c).text = value
    prs.save(path)

    elements = partition(
        filename=str(path), strategy="hi_res", infer_table_structure=True
    )
    tables = _tables(elements)
    assert len(tables) == 1
    assert tables[0].html is not None

    out = render(tables, annotate=True)
    assert "North America" in out
    assert "412" in out
