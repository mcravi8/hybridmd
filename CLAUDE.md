# hybridmd — project conventions

`hybridmd` converts parsed document elements into **hybrid Markdown**: Markdown
wherever it is lossless, and embedded **sanitized HTML only for tables** whose
structure (merged cells, nesting, ragged rows) plain Markdown cannot represent.

These conventions are binding. Follow them exactly.

## Layout

- **src layout.** Importable code lives under `src/hybridmd/`. Tests live under
  `tests/`. Never add importable modules at the repo root.
- The package is typed: ship the `py.typed` marker and annotate all public APIs.

## Python

- **Target Python `>=3.10`.** Code must run on 3.10, 3.11, and 3.12 (the CI
  matrix). Do not use syntax or stdlib APIs newer than 3.10.

## Dependencies

- **The core package depends ONLY on `beautifulsoup4`.** Do not add any other
  runtime dependency to `[project.dependencies]`.
- **Adapters (document parsers) and backends (renderers / HTML sanitizers) go in
  optional extras** under `[project.optional-dependencies]`, never in the core
  dependency list. Add a new named extra rather than widening the core.

## Tooling

- **ruff** for both linting and formatting (`ruff check`, `ruff format`).
- **mypy `--strict`** on `src` — the source tree must type-check cleanly under
  strict mode.
- **pytest** for tests.
- All tool configuration lives in `pyproject.toml`.

## Commits

- **Conventional Commits** (`type: summary`), e.g. `feat:`, `fix:`, `chore:`,
  `docs:`, `test:`, `refactor:`. Keep the summary imperative and scoped.

## Quality gate

**Before every commit, run the full gate and make sure it passes:**

```
ruff check . && ruff format --check . && mypy src && pytest
```

Do not commit if any stage fails.
