# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
