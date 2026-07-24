"""Smoke tests for the hybridmd package version.

The version is deliberately asserted by *format*, not by an exact literal, so it
lives in only two places (pyproject.toml and src/hybridmd/__init__.py) and does
not need updating here on every release.
"""

from __future__ import annotations

import re

import hybridmd


def test_version_is_exposed() -> None:
    assert isinstance(hybridmd.__version__, str)
    assert hybridmd.__version__


def test_version_is_semver_formatted() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", hybridmd.__version__)
