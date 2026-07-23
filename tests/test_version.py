"""Smoke tests for the hybridmd package skeleton."""

from __future__ import annotations

import hybridmd


def test_version_is_exposed() -> None:
    assert hybridmd.__version__ == "0.0.1"


def test_version_is_a_string() -> None:
    assert isinstance(hybridmd.__version__, str)
