"""Tests for the hybridmd CLI — all in-process via main(), never a subprocess."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hybridmd import __version__, cli
from hybridmd.cli import main

# --- fixtures / helpers -----------------------------------------------------


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


DOC_ELEMENTS = [
    {"type": "heading", "text": "Report", "level": 1},
    {"type": "paragraph", "text": "Hello."},
    {
        "type": "table",
        "text": "fallback",
        "html": "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>",
    },
]
EXPECTED_DOC = "# Report\n\nHello.\n\n| A |\n| --- |\n| 1 |\n"

UNSTRUCTURED_ELEMENTS = [
    {"type": "Title", "text": "Report", "metadata": {"category_depth": 0}},
    {"type": "NarrativeText", "text": "Hello."},
]
EXPECTED_UNSTRUCTURED = "# Report\n\nHello.\n"


# --- happy paths ------------------------------------------------------------


def test_docelement_json_end_to_end(tmp_path, capsys) -> None:
    path = _write(tmp_path / "doc.json", DOC_ELEMENTS)
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == EXPECTED_DOC


def test_unstructured_json_end_to_end(tmp_path, capsys) -> None:
    path = _write(tmp_path / "u.json", UNSTRUCTURED_ELEMENTS)
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == EXPECTED_UNSTRUCTURED


def test_equivalent_inputs_produce_identical_output(tmp_path, capsys) -> None:
    doc = _write(
        tmp_path / "doc.json",
        [
            {"type": "heading", "text": "T", "level": 1},
            {"type": "paragraph", "text": "Body."},
        ],
    )
    uns = _write(
        tmp_path / "uns.json",
        [
            {"type": "Title", "text": "T", "metadata": {"category_depth": 0}},
            {"type": "NarrativeText", "text": "Body."},
        ],
    )
    assert main([str(doc)]) == 0
    out_doc = capsys.readouterr().out
    assert main([str(uns)]) == 0
    out_uns = capsys.readouterr().out
    assert out_doc == out_uns == "# T\n\nBody.\n"


def test_output_written_to_file_not_stdout(tmp_path, capsys) -> None:
    path = _write(tmp_path / "doc.json", DOC_ELEMENTS)
    out = tmp_path / "out.md"
    assert main([str(path), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == EXPECTED_DOC
    assert capsys.readouterr().out == ""


def test_output_to_stdout(tmp_path, capsys) -> None:
    path = _write(tmp_path / "doc.json", DOC_ELEMENTS)
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == EXPECTED_DOC


def test_annotate_is_plumbed_through(tmp_path, capsys) -> None:
    path = _write(tmp_path / "doc.json", DOC_ELEMENTS)
    assert main([str(path), "--annotate"]) == 0
    assert "<!-- hybridmd: table format=md reasons=none -->" in capsys.readouterr().out


def test_force_html_is_plumbed_through(tmp_path, capsys) -> None:
    path = _write(tmp_path / "doc.json", DOC_ELEMENTS)
    assert main([str(path), "--annotate", "--force", "html"]) == 0
    out = capsys.readouterr().out
    assert "format=html" in out
    assert "forced=true" in out


def test_force_md_is_plumbed_through(tmp_path, capsys) -> None:
    # A merged-cell table would route to html; force="md" overrides it and the
    # marker still reports the real analyzer reasons.
    merged = _write(
        tmp_path / "m.json",
        [
            {
                "type": "table",
                "text": "t",
                "html": (
                    '<table><tr><td colspan="2">wide</td></tr>'
                    "<tr><td>a</td><td>b</td></tr></table>"
                ),
            }
        ],
    )
    assert main([str(merged), "--annotate", "--force", "md"]) == 0
    out = capsys.readouterr().out
    assert "format=md reasons=merged_cells forced=true" in out


def test_version_prints_version_and_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_empty_json_list_renders_empty_document(tmp_path, capsys) -> None:
    path = _write(tmp_path / "empty.json", [])
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == ""


# --- error discipline (all exit 1, one-line stderr, no traceback) -----------


def test_nonexistent_path(tmp_path, capsys) -> None:
    assert main([str(tmp_path / "nope.json")]) == 1
    assert "not found" in capsys.readouterr().err


def test_malformed_json(tmp_path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert main([str(path)]) == 1
    assert "JSON" in capsys.readouterr().err


def test_json_root_not_a_list(tmp_path, capsys) -> None:
    path = _write(tmp_path / "obj.json", {"type": "heading"})
    assert main([str(path)]) == 1
    assert "list" in capsys.readouterr().err


def test_unrecognized_type_value(tmp_path, capsys) -> None:
    path = _write(tmp_path / "weird.json", [{"type": "frobnicate", "text": "x"}])
    assert main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "frobnicate" in err  # names the offending value
    assert "heading" in err  # names the hybridmd shape
    assert "unstructured" in err  # names the unstructured shape


def test_missing_backend_names_the_pip_extra(tmp_path, monkeypatch, capsys) -> None:
    doc = tmp_path / "doc.pdf"
    doc.write_text("dummy", encoding="utf-8")

    def _no_backend(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(cli, "import_module", _no_backend)
    assert main([str(doc)]) == 1
    assert 'pip install "hybridmd[unstructured]"' in capsys.readouterr().err


def test_malformed_docelement_reports_cleanly_no_traceback(tmp_path, capsys) -> None:
    # First element is correctly detected as a paragraph but is missing its
    # required "text" — an expected bad-input case, must not dump a traceback.
    path = _write(tmp_path / "m.json", [{"type": "paragraph"}])
    assert main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "element 0" in err


def test_malformed_later_element_reports_cleanly(tmp_path, capsys) -> None:
    path = _write(
        tmp_path / "m2.json",
        [{"type": "paragraph", "text": "ok"}, {"type": "banana", "text": "bad"}],
    )
    assert main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "element 1" in err


@pytest.mark.parametrize(
    "data",
    [
        [{"text": "x"}],  # first element has no "type"
        [{"type": 123, "text": "x"}],  # "type" is not a string
        [42],  # first element is not an object at all
    ],
)
def test_unrecognized_first_element_shape(tmp_path, capsys, data) -> None:
    path = _write(tmp_path / "bad.json", data)
    assert main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "heading" in err  # names the hybridmd shape
    assert "unstructured" in err  # names the unstructured shape


def test_output_to_unwritable_path_reports_cleanly(tmp_path, capsys) -> None:
    path = _write(tmp_path / "doc.json", DOC_ELEMENTS)
    bad_out = tmp_path / "missing" / "sub" / "out.md"  # parent dirs don't exist
    assert main([str(path), "-o", str(bad_out)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "cannot write" in err


def test_input_that_cannot_be_read_reports_cleanly(tmp_path, capsys) -> None:
    # A directory named like a .json file: exists() is True, but the read fails.
    directory = tmp_path / "d.json"
    directory.mkdir()
    assert main([str(directory)]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "cannot read" in err


@pytest.mark.parametrize("argv", [[], ["doc.json", "--force", "bogus"]])
def test_argparse_usage_errors_exit_code_2(argv) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
