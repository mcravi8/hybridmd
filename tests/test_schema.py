"""Tests for the extractor-agnostic document element schema."""

from __future__ import annotations

import dataclasses
import json

import pytest

from hybridmd import DocElement, ElementType, schema


def test_construction_with_defaults() -> None:
    element = DocElement(type=ElementType.PARAGRAPH, text="hello")
    assert element.type is ElementType.PARAGRAPH
    assert element.text == "hello"
    assert element.html is None
    assert element.level is None
    assert element.metadata == {}


def test_construction_with_all_fields() -> None:
    element = DocElement(
        type=ElementType.TABLE,
        text="a b",
        html="<table><tr><td>a</td><td>b</td></tr></table>",
        level=None,
        metadata={"source": "unstructured"},
    )
    assert element.html == "<table><tr><td>a</td><td>b</td></tr></table>"
    assert element.metadata == {"source": "unstructured"}


def test_reexported_from_package_root() -> None:
    assert DocElement is schema.DocElement
    assert ElementType is schema.ElementType


def test_is_frozen_field_assignment_raises() -> None:
    element = DocElement(type=ElementType.HEADING, text="Title", level=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        element.text = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        element.type = ElementType.PARAGRAPH


@pytest.mark.parametrize("element_type", list(ElementType))
def test_dict_round_trip_every_type(element_type: ElementType) -> None:
    original = DocElement(
        type=element_type,
        text=f"text for {element_type.value}",
        html="<table></table>" if element_type is ElementType.TABLE else None,
        level=2 if element_type is ElementType.HEADING else None,
        metadata={"k": "v"},
    )
    as_dict = original.to_dict()
    assert as_dict["type"] == element_type.value
    # Exact-type check, not isinstance: ElementType subclasses str, so an
    # isinstance/`==` check still passes if to_dict leaks the raw enum member.
    # `type(...) is str` fails unless the plain string value was emitted.
    assert type(as_dict["type"]) is str
    restored = DocElement.from_dict(as_dict)
    assert restored == original


def test_to_dict_output_is_json_serializable() -> None:
    element = DocElement(
        type=ElementType.CODE, text="print(1)", metadata={"lang": "py"}
    )
    encoded = json.dumps(element.to_dict())
    assert DocElement.from_dict(json.loads(encoded)) == element


def test_from_dict_unknown_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown element type"):
        DocElement.from_dict({"type": "bogus", "text": ""})


def test_from_dict_defaults_optional_fields() -> None:
    element = DocElement.from_dict({"type": "paragraph", "text": "hi"})
    assert element.html is None
    assert element.level is None
    assert element.metadata == {}


def test_default_metadata_isolated_between_instances() -> None:
    a = DocElement(type=ElementType.OTHER, text="a")
    b = DocElement(type=ElementType.OTHER, text="b")
    assert a.metadata is not b.metadata
    a.metadata["only_in_a"] = 1
    assert b.metadata == {}


def test_from_dict_does_not_alias_source_metadata() -> None:
    source: dict[str, object] = {
        "type": "paragraph",
        "text": "x",
        "metadata": {"m": 1},
    }
    element = DocElement.from_dict(source)
    element.metadata["extra"] = 2
    assert source["metadata"] == {"m": 1}


def test_to_dict_copy_does_not_leak_back_into_instance() -> None:
    element = DocElement(type=ElementType.OTHER, text="x", metadata={"a": 1})
    dumped = element.to_dict()
    dumped["metadata"]["b"] = 2
    assert element.metadata == {"a": 1}
