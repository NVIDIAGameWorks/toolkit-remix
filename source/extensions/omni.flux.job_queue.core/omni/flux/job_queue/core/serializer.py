"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import enum
import json
import math
import pathlib
import uuid
from collections.abc import Iterator
from typing import Any

from . import persistence
from .constants import COLLECTION_TYPE_NAMES, COLLECTION_TYPES

__all__ = ("deserialize", "serialize")


def serialize(obj: Any) -> str:
    """Serialize one supported queue value to JSON.

    Args:
        obj: Registered or built-in queue value to encode.

    Returns:
        JSON representation containing only explicitly supported data.

    Raises:
        TypeError: If the value or any nested value is unsupported or invalid.
    """
    try:
        return json.dumps(_encode(obj, set()), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise TypeError(f"Object of type {type(obj).__name__} is not serializable: {error}") from error


def deserialize(data: str) -> Any:
    """Deserialize one queue JSON value.

    Args:
        data: JSON representation produced by :func:`serialize`.

    Returns:
        Decoded registered or built-in queue value.

    Raises:
        ValueError: If the input is not a string or contains malformed or unsupported data.
    """
    if not isinstance(data, str):
        raise ValueError("Input to deserialize must be a string.")
    try:
        return _decode(
            json.loads(
                data,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_decode_json_object,
            )
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Failed to deserialize data: {error}") from error


def _encode(obj: Any, active_containers: set[int]) -> Any:
    """Convert one supported value into JSON-native data.

    Args:
        obj: Registered or built-in value to encode recursively.
        active_containers: Identities currently being traversed for cycle detection.

    Returns:
        JSON-native scalar, list, or tagged dictionary.

    Raises:
        TypeError: If the value is unsupported, unregistered, or structurally invalid.
    """
    if type(obj) is float:
        if not math.isfinite(obj):
            raise TypeError("Non-finite floats are not supported")
        return obj
    if obj is None or type(obj) in (str, int, bool):
        return obj
    if type(obj) is dict:
        if not all(type(key) is str for key in obj):
            raise TypeError("Dictionary keys must be strings")
        with _track_container(obj, active_containers):
            return {
                "__type__": "dict",
                "value": [[key, _encode(value, active_containers)] for key, value in obj.items()],
            }
    if type(obj) is list:
        with _track_container(obj, active_containers):
            return [_encode(value, active_containers) for value in obj]
    if isinstance(obj, enum.Enum):
        return {"__type__": "enum", "class": _get_type_id(type(obj)), "member": obj.name}
    if isinstance(obj, type):
        return {"__type__": "type", "value": _get_type_id(obj)}
    if isinstance(obj, pathlib.Path):
        return {"__type__": "path", "value": obj.as_posix()}
    if isinstance(obj, uuid.UUID):
        return {"__type__": "uuid", "value": str(obj)}
    if isinstance(obj, bytes):
        return {"__type__": "bytes", "value": base64.b64encode(obj).decode("ascii")}
    codec = persistence.get_registry().get_codec_for_type(type(obj))
    if codec is not None and codec.encoder is not None:
        with _track_container(obj, active_containers):
            return {
                "__type__": "custom",
                "class": codec.name,
                "value": _encode(codec.encoder(obj), active_containers),
            }
    if type(obj) in COLLECTION_TYPE_NAMES:
        with _track_container(obj, active_containers):
            return {
                "__type__": COLLECTION_TYPE_NAMES[type(obj)],
                "value": [_encode(value, active_containers) for value in obj],
            }
    raise TypeError(f"No serializer for type: {type(obj)}")


@contextlib.contextmanager
def _track_container(value: Any, active_containers: set[int]) -> Iterator[None]:
    """Track one active object identity while recursively serializing it.

    Args:
        value: Object whose recursive encoding is starting.
        active_containers: Identities already being traversed.

    Yields:
        Control while the value is marked active.

    Raises:
        TypeError: If this object is already an ancestor in the active traversal.
    """
    identity = id(value)
    if identity in active_containers:
        raise TypeError("Cyclic values are not supported")
    active_containers.add(identity)
    try:
        yield
    finally:
        active_containers.remove(identity)


def _reject_json_constant(value: str) -> None:
    """Reject non-standard JSON numeric constants.

    Args:
        value: Non-standard constant emitted by the JSON parser.

    Raises:
        ValueError: Always, because persisted queue data must be standard JSON.
    """
    raise ValueError(f"Non-standard JSON number is not supported: {value}")


def _decode_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build one JSON object while rejecting duplicate member names.

    Args:
        pairs: Ordered member pairs emitted by the JSON parser.

    Returns:
        Parsed object with unique member names.

    Raises:
        ValueError: If a member name occurs more than once.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON object contains duplicate member: {key}")
        result[key] = value
    return result


def _decode(data: Any) -> Any:
    """Restore one recursively encoded queue value.

    Args:
        data: JSON-native scalar, list, or tagged dictionary to decode.

    Returns:
        Restored registered or built-in queue value.

    Raises:
        KeyError: If a tagged enum names an unknown member.
        TypeError: If a tagged value has an invalid field type or registered class.
        ValueError: If a tagged value is malformed or uses an unknown tag.
    """
    if type(data) is float and not math.isfinite(data):
        raise ValueError("Non-finite floats are not supported")
    if type(data) is list:
        return [_decode(value) for value in data]
    if type(data) is not dict:
        return data
    value_type = data.get("__type__")
    if value_type == "dict":
        _require_fields(data, "dict", "value")
        values = data["value"]
        if type(values) is not list:
            raise TypeError("Serialized dict value must be a list")
        result = {}
        for item in values:
            if type(item) is not list or len(item) != 2:
                raise ValueError("Serialized dict entries must be key-value pairs")
            key, value = item
            if type(key) is not str:
                raise TypeError("Dictionary keys must be strings")
            if key in result:
                raise ValueError(f"Serialized dictionary contains duplicate key: {key}")
            result[key] = _decode(value)
        return result
    if value_type is None:
        raise ValueError("Serialized dictionaries must have an explicit type")
    if value_type == "enum":
        _require_fields(data, "enum", "class", "member")
        if type(data["class"]) is not str or type(data["member"]) is not str:
            raise TypeError("Serialized enum class and member must be strings")
        enum_type = _get_registered_type(data["class"])
        if not issubclass(enum_type, enum.Enum):
            raise TypeError(f"Registered type is not an enum: {data['class']}")
        return enum_type[data["member"]]
    if value_type == "type":
        _require_fields(data, "type", "value")
        if type(data["value"]) is not str:
            raise TypeError("Serialized type value must be a string")
        return _get_registered_type(data["value"])
    if value_type == "path":
        _require_fields(data, "path", "value")
        if type(data["value"]) is not str:
            raise TypeError("Serialized path value must be a string")
        return pathlib.Path(data["value"])
    if value_type == "uuid":
        _require_fields(data, "uuid", "value")
        if type(data["value"]) is not str:
            raise TypeError("Serialized uuid value must be a string")
        return uuid.UUID(data["value"])
    if value_type == "bytes":
        _require_fields(data, "bytes", "value")
        if type(data["value"]) is not str:
            raise TypeError("Serialized bytes value must be a string")
        try:
            return base64.b64decode(data["value"].encode("ascii"), validate=True)
        except (binascii.Error, UnicodeEncodeError) as error:
            raise ValueError("Serialized bytes value must be valid Base64") from error
    if value_type == "custom":
        _require_fields(data, "custom", "class", "value")
        if type(data["class"]) is not str:
            raise TypeError("Serialized custom class must be a string")
        codec = persistence.get_registry().get_codec(data["class"])
        if codec is None or codec.decoder is None:
            raise TypeError(f"Persisted custom type '{data['class']}' is not registered")
        return codec.decoder(_decode(data["value"]))
    if value_type in COLLECTION_TYPES:
        _require_fields(data, value_type, "value")
        if type(data["value"]) is not list:
            raise TypeError(f"Serialized {value_type} value must be a list")
        values = (_decode(value) for value in data["value"])
        return COLLECTION_TYPES[value_type](values)
    raise ValueError(f"Unknown serialized type: {value_type}")


def _require_fields(data: dict[str, Any], value_type: str, *field_names: str) -> None:
    """Require one tagged payload to contain exactly its canonical fields.

    Args:
        data: Tagged payload whose keys should be validated.
        value_type: Display name used in validation errors.
        *field_names: Canonical fields required in addition to the type tag.

    Raises:
        ValueError: If the payload contains missing or unexpected fields.
    """
    expected_fields = {"__type__", *field_names}
    if set(data) != expected_fields:
        raise ValueError(f"Serialized {value_type} must contain exactly: {', '.join(sorted(expected_fields))}")


def _get_type_id(value_type: type) -> str:
    """Return the stable identifier for one explicitly registered type.

    Args:
        value_type: Type whose persistence identifier should be resolved.

    Returns:
        Stable persistence identifier registered for the type.

    Raises:
        TypeError: If the type is not registered for queue persistence.
    """
    type_id = persistence.get_registry().get_name(value_type)
    if type_id is None:
        raise TypeError(f"{value_type.__name__} is not registered for queue persistence")
    return type_id


def _get_registered_type(type_id: str) -> type:
    """Return one explicitly registered type without importing executable code.

    Args:
        type_id: Stable persistence identifier to resolve.

    Returns:
        Type registered for the identifier.

    Raises:
        TypeError: If the identifier is not registered for queue persistence.
    """
    value_type = persistence.get_registry().get_type(type_id)
    if value_type is None:
        raise TypeError(f"Persisted type '{type_id}' is not registered")
    return value_type
