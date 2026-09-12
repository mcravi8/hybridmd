"""Command-line interface for hybridmd — ``argparse`` only, no third-party deps.

The zero-dependency core principle extends to the CLI: parsing uses the standard
library alone. The optional ``unstructured`` backend is imported lazily and only
when a non-JSON input is given, so core usage never needs it.

Usage::

    hybridmd INPUT [-o OUT] [--annotate] [--force {md,html}]
             [--strategy {auto,fast,hi_res,ocr_only}] [--no-table-structure]
             [--version]

``main`` returns the process exit code rather than calling :func:`sys.exit`, so
every path is testable in-process; the thin :func:`run` entry point does the
actual exit.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from importlib import import_module
from pathlib import Path
from typing import Any

from hybridmd import __version__
from hybridmd.adapters.unstructured_io import from_unstructured
from hybridmd.router import render
from hybridmd.schema import DocElement, ElementType

# The lowercase snake_case values that identify a hybridmd DocElement dict.
_ELEMENT_TYPE_VALUES = frozenset(member.value for member in ElementType)
_INSTALL_HINT = (
    'install the optional backend with: pip install "hybridmd[unstructured]" — '
    "binary formats additionally need that format's own extra, e.g. "
    '"hybridmd[unstructured-pdf]" or "hybridmd[unstructured-pptx]"'
)

# Table detection is the whole point of this tool, so the CLI defaults to the
# accurate-but-slower backend strategy rather than the backend's own "auto".
# `auto` resolves to a fast, text-only path for text-based PDFs, which performs
# no layout analysis at all: every table is flattened into prose before hybridmd
# ever sees it, so the router silently has nothing to route. Correctness first;
# `--strategy fast` remains available for callers who want the speed.
_DEFAULT_STRATEGY = "hi_res"
_STRATEGIES = ("auto", "fast", "hi_res", "ocr_only")


class _CliError(Exception):
    """An expected, user-facing failure — reported as one stderr line, exit 1."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hybridmd",
        description="Convert parsed document elements into hybrid Markdown.",
    )
    parser.add_argument(
        "input",
        metavar="INPUT",
        help=(
            "a .json file of hybridmd or unstructured element dicts, or any "
            "document file to parse via the unstructured backend"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="OUT",
        help="write the document to this file instead of stdout",
    )
    parser.add_argument(
        "--annotate",
        action="store_true",
        help="emit an HTML comment before each table recording its routing",
    )
    parser.add_argument(
        "--force",
        choices=("md", "html"),
        help='force every usable-html table to "md" (lossy) or "html"',
    )
    parser.add_argument(
        "--strategy",
        choices=_STRATEGIES,
        default=_DEFAULT_STRATEGY,
        help=(
            "backend parsing strategy for non-JSON documents "
            f"(default: {_DEFAULT_STRATEGY}). "
            '"fast" and "auto" skip layout analysis on text-based PDFs and '
            "will miss their tables entirely"
        ),
    )
    parser.add_argument(
        "--no-table-structure",
        action="store_true",
        help="do not ask the backend to infer table structure (not recommended)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def _parse_docelements(data: list[Any], source: Path) -> list[DocElement]:
    """Parse hybridmd DocElement dicts; a malformed element becomes a clean error.

    Shape detection keys off the first element, but every element is parsed here,
    so a bad element (missing ``text``, unknown ``type``, or not an object) is
    reported as one stderr line rather than surfacing ``from_dict``'s raw
    ``ValueError``/``KeyError``/``TypeError`` as a traceback.
    """
    parsed: list[DocElement] = []
    for index, item in enumerate(data):
        try:
            parsed.append(DocElement.from_dict(item))
        except (ValueError, KeyError, TypeError) as exc:
            raise _CliError(
                f"{source}: element {index} is not a valid hybridmd element: {exc}"
            ) from exc
    return parsed


def _dispatch_json(data: list[Any], source: Path) -> list[DocElement]:
    """Route a non-empty JSON list to the right parser by its first element.

    A hybridmd DocElement dict has a lowercase ``type`` (an :class:`ElementType`
    value); an unstructured element dict has a CapitalizedCamelCase category.
    """
    first = data[0]
    type_value = first.get("type") if isinstance(first, Mapping) else None
    if type_value in _ELEMENT_TYPE_VALUES:
        return _parse_docelements(data, source)
    if isinstance(type_value, str) and type_value[:1].isupper():
        return from_unstructured(data)
    raise _CliError(
        f"{source}: unrecognized element type {type_value!r} in the first "
        f"element; expected a hybridmd type "
        f"({', '.join(sorted(_ELEMENT_TYPE_VALUES))}) or a capitalized "
        f"unstructured category (e.g. Title, NarrativeText, Table)"
    )


def _load_json(path: Path) -> list[DocElement]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # permissions, is-a-directory, etc.
        raise _CliError(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _CliError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise _CliError(
            f"{path}: expected a JSON list at the top level, got {type(data).__name__}"
        )
    if not data:
        return []
    return _dispatch_json(data, path)


def _load_via_unstructured(
    path: Path, *, strategy: str, infer_table_structure: bool
) -> list[DocElement]:
    """Parse *path* with the optional backend, surfacing both ImportError paths.

    The backend raises ImportError twice over: once at import time when it is not
    installed at all, and again at *partition* time when the package is present
    but that document's format extra is not. The second is easy to miss — it
    escapes as a traceback rather than a clean CLI error — so both are caught.
    """
    try:
        partition = import_module("unstructured.partition.auto").partition
    except ImportError as exc:  # backend (or a dependency of it) not installed
        raise _CliError(_INSTALL_HINT) from exc
    try:
        elements = partition(
            filename=str(path),
            strategy=strategy,
            infer_table_structure=infer_table_structure,
        )
    except ImportError as exc:  # backend present, this format's extra is not
        raise _CliError(f"{exc}; {_INSTALL_HINT}") from exc
    return from_unstructured(elements)


def _load_elements(
    input_path: str, *, strategy: str, infer_table_structure: bool
) -> list[DocElement]:
    path = Path(input_path)
    if not path.exists():
        raise _CliError(f"input file not found: {input_path}")
    if input_path.endswith(".json"):
        return _load_json(path)
    return _load_via_unstructured(
        path, strategy=strategy, infer_table_structure=infer_table_structure
    )


def _warn(message: str) -> None:
    """Emit one advisory line to stderr, leaving stdout to carry the document."""
    print(f"hybridmd: warning: {message}", file=sys.stderr)


def _warn_on_missing_tables(elements: Sequence[DocElement], strategy: str) -> None:
    """Flag the silent-table-loss case: a weak strategy that found no tables.

    A strategy that skips layout analysis cannot report that it skipped it — the
    document simply arrives with every table flattened into prose, and hybridmd
    has nothing to route. Zero tables under such a strategy is therefore
    ambiguous in the one direction that matters, so say so. Under ``hi_res`` the
    same result is trustworthy and stays silent.
    """
    if strategy == "hi_res":
        return
    if any(el.type is ElementType.TABLE for el in elements):
        return
    _warn(
        f"no tables detected using --strategy {strategy}; this strategy skips "
        "layout analysis, so any tables in the document were flattened into "
        "text. Re-run with --strategy hi_res to detect them"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv*, render, and return the exit code (0 success, 1 on error).

    Expected failures (missing input, malformed JSON, non-list root, unknown
    element shape, missing backend) are reported as a single stderr line and
    return 1. argparse handles usage errors with its own exit code 2. Genuinely
    unexpected exceptions are left to propagate.
    """
    args = _build_parser().parse_args(argv)
    if args.force == "md":
        _warn(
            'force="md" is explicitly lossy: tables that need HTML will be '
            "emitted as Markdown anyway and silently corrupted. It exists to "
            "quantify the tradeoff, not for production use"
        )
    try:
        elements = _load_elements(
            args.input,
            strategy=args.strategy,
            infer_table_structure=not args.no_table_structure,
        )
    except _CliError as exc:
        print(f"hybridmd: error: {exc}", file=sys.stderr)
        return 1
    if not args.input.endswith(".json"):
        _warn_on_missing_tables(elements, args.strategy)
    document = render(elements, annotate=args.annotate, force=args.force)
    if args.output is not None:
        try:
            Path(args.output).write_text(document, encoding="utf-8")
        except OSError as exc:
            print(
                f"hybridmd: error: cannot write {args.output}: {exc}", file=sys.stderr
            )
            return 1
    else:
        sys.stdout.write(document)
    return 0


def run() -> None:
    """Console-script entry point: exit with :func:`main`'s return code."""
    sys.exit(main())


if __name__ == "__main__":
    run()
