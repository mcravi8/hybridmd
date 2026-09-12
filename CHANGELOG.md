# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **The CLI no longer silently discards tables.** `hybridmd document.pdf` now defaults to the backend's `hi_res` strategy with `infer_table_structure=True`. The backend's own default resolves to a fast, text-only path on text-based PDFs that performs no layout analysis, so every table was flattened into prose before reaching the analyzer — on a sample of three real PDFs, 0 of 14 tables were detected before this change and all 14 after.
- **A table with no header row no longer has one invented.** `table_to_markdown` previously promoted the first row to a header whenever no `<thead>` was present, silently relabelling data as column headings (a regression-coefficient row becoming a header). It now emits an empty header and reports `no_header`.
- A missing format extra (`partition_pdf() is not available…`) is now reported as a clean CLI error instead of escaping as a traceback.

### Added

- Advisory analyzer reasons, reported without forcing the HTML fallback: `no_header` and `single_column` (the latter flags one-column "tables", typically a caption or label that layout detection boxed as tabular).
- `--strategy {auto,fast,hi_res,ocr_only}` and `--no-table-structure` CLI flags.
- Stderr warnings for the two silent-failure modes: using the lossy `--force md`, and finding no tables under a strategy that cannot detect them.
- Format-specific extras — `unstructured-pdf`, `unstructured-pptx`, `unstructured-docx` — since bare `unstructured` cannot parse any binary format.
- `tests/integration/`: tests against the **real** Unstructured backend, plus a CI job running them. Core CI stays dependency-free and skips them. These pin two upstream behaviours: PPTX tables *do* round-trip, and the HTML partitioner strips `colspan`/`rowspan`, making merged cells undetectable on that path (the PDF path is unaffected).

### Documentation

- A "What hybridmd does not do" section: fidelity guarantees are structural, never about whether extracted text is correct.

## [0.1.0] - 2026-07-24

### Added

- Extractor-agnostic `DocElement` schema — the backend-neutral internal representation, with `from_dict`/`to_dict` JSON interop.
- Table complexity analyzer (`analyze_table`) that decides whether a table is representable in Markdown, with typed `Reason`s and HTML5-conformant `colspan`/`rowspan` parsing.
- Markdown and sanitized-HTML serializers: `table_to_markdown`, `sanitize_table_html` (fixed tag/attribute whitelist), and `element_to_markdown`.
- Per-table router (`render`) that assembles hybrid Markdown, with optional annotation markers and `force` modes for benchmarking.
- Unstructured adapter (`from_unstructured`) behind the optional `hybridmd[unstructured]` extra, reading its input purely by duck typing (no core dependency).
- `argparse`-based CLI (`hybridmd`) supporting both JSON element shapes (hybridmd and Unstructured dicts) and direct document partitioning via the backend.
- Demo and table-heavy example fixtures with a token-count report (`scripts/token_report.py`, `hybridmd[bench]`).

[0.1.0]: https://github.com/mcravi8/hybridmd/compare/22c580d...v0.1.0
