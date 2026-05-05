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

import base64
import dataclasses
import enum
import functools
import json
import pathlib
import pickle
import uuid
from typing import Any, Generic, TypeVar
from collections.abc import Callable

import omni.flux.job_queue.core.job
import omni.flux.job_queue.core.utils

T = TypeVar("T")


def serialize(obj: Any) -> str:
    """
    Serialize a Python object to a JSON string using custom serializers.

    Args:
        obj (Any): The Python object to serialize.

    Returns:
        str: The JSON string representation of the object.
    """
    try:
        return json.dumps(obj, cls=Encoder, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise TypeError(f"Object of type {type(obj).__name__} is not serializable: {e}") from e


def deserialize(data: str) -> Any:
    """
    Deserialize a JSON string to a Python object using custom deserializers.
    Raises ValueError for corrupt or invalid data.

    Args:
        data (str): The JSON string to deserialize.

    Returns:
        Any: The deserialized Python object.
    """
    if not isinstance(data, str):
        raise ValueError("Input to deserialize must be a string.")
    try:
        return json.loads(data, object_hook=Serializer.deserialize)
    except Exception as e:
        raise ValueError(f"Failed to deserialize data: {e}") from e


class Encoder(json.JSONEncoder):
    """
    Custom JSON encoder that uses the Serializer class for custom types.
    """

    def encode(self, o: Any) -> str:
        """
        Encode an object using custom serializers.
        """
        try:
            return json.dumps(Serializer.serialize(o))
        except TypeError:
            return super().encode(o)


@dataclasses.dataclass
class TypeSerializer(Generic[T]):
    """
    Represents a serializer/deserializer for a specific type.

    Args:
        name (str): Name of the type.
        claim (Callable[[Any], bool]): Function to determine if this serializer should handle the object.
        serializer (Callable[[T], Any]): Function to serialize the object.
        deserializer (Callable[[Any], T]): Function to deserialize the object.
        priority (int, optional): Priority for serializer selection (higher is preferred, default is 0).
    """

    name: str
    claim: Callable[[Any], bool]
    serializer: Callable[[T], Any]
    deserializer: Callable[[Any], T]
    priority: int = 0


class Serializer:
    """
    Registry and logic for custom (de)serializers.
    """

    _serializers: dict[str, TypeSerializer] = {}
    _serializer_list: list[TypeSerializer] = []

    @classmethod
    def register(cls, type_serializer: TypeSerializer) -> TypeSerializer:
        """
        Register a new TypeSerializer.
        """
        if type_serializer.name in cls._serializers:
            raise ValueError(f"Serializer with name {type_serializer.name} already registered.")
        cls._serializers[type_serializer.name] = type_serializer
        cls._serializer_list.append(type_serializer)
        return type_serializer

    @classmethod
    def serialize(cls, obj: Any) -> Any:
        """
        Serialize an object using the highest-priority matching TypeSerializer.

        JSON-native types (dict, list, str, int, float, bool, None) with exact type matches
        are handled directly. Subclasses of these types go through the serializer registry
        so they can be properly round-tripped.
        """
        # Exact type matches for JSON-native container types - recursively serialize contents
        if type(obj) is dict:
            return {k: cls.serialize(v) for k, v in obj.items()}
        if type(obj) is list:
            return [cls.serialize(item) for item in obj]

        # Exact type matches for JSON-native scalar types - return as-is
        if type(obj) in (str, int, float, bool) or obj is None:
            return obj

        # Try custom serializers (sorted by priority, highest first)
        for _, serializer in sorted(
            enumerate(cls._serializer_list),
            key=lambda x: (x[1].priority, x[0]),
            reverse=True,
        ):
            if serializer.claim(obj):
                return {
                    "__type__": serializer.name,
                    "__data__": serializer.serializer(obj),
                }

        raise TypeError(f"No serializer for type: {type(obj)}")

    @classmethod
    def deserialize(cls, data: Any) -> Any:
        """
        Deserialize an object using the appropriate TypeSerializer.
        """
        if isinstance(data, dict) and "__type__" in data and "__data__" in data:
            name = data["__type__"]
            serializer = cls._serializers.get(name)
            if serializer:
                return serializer.deserializer(data["__data__"])
        return data


# This is the fallback serializer that uses pickle for anything else. Note the priority of -1000 to make it the last
# resort. JSON-native types (exact type matches for dict, list, str, int, float, bool, None) are handled before
# the serializer loop runs, so this will only catch subclasses and other custom types.
Serializer.register(
    TypeSerializer(
        name="pickle",
        claim=lambda obj: True,
        serializer=lambda obj: base64.b64encode(pickle.dumps(obj)).decode("ascii"),
        deserializer=lambda data: pickle.loads(base64.b64decode(data.encode("ascii"))),
        priority=-1000,
    )
)


Serializer.register(
    TypeSerializer(
        name="pathlib",
        claim=lambda obj: isinstance(obj, pathlib.Path),
        serializer=lambda x: x.as_posix(),
        deserializer=pathlib.Path,
    )
)


Serializer.register(
    TypeSerializer(
        name="uuid",
        claim=lambda obj: isinstance(obj, uuid.UUID),
        serializer=str,
        deserializer=uuid.UUID,
    )
)

Serializer.register(
    TypeSerializer(
        name="bytes",
        claim=lambda obj: isinstance(obj, bytes),
        serializer=lambda obj: base64.b64encode(obj).decode("ascii"),
        deserializer=lambda data: base64.b64decode(data.encode("ascii")),
    )
)

Serializer.register(
    TypeSerializer(
        name="tuple",
        claim=lambda obj: isinstance(obj, tuple),
        serializer=lambda obj: [Serializer.serialize(item) for item in obj],
        deserializer=lambda data: tuple(Serializer.deserialize(item) for item in data),
    )
)

Serializer.register(
    TypeSerializer(
        name="list",
        claim=lambda obj: isinstance(obj, list),
        serializer=lambda obj: [Serializer.serialize(item) for item in obj],
        deserializer=lambda data: [Serializer.deserialize(item) for item in data],
    )
)

Serializer.register(
    TypeSerializer(
        name="set",
        claim=lambda obj: isinstance(obj, set),
        serializer=lambda obj: [Serializer.serialize(item) for item in obj],
        deserializer=lambda data: {Serializer.deserialize(item) for item in data},
    )
)

Serializer.register(
    TypeSerializer(
        name="frozenset",
        claim=lambda obj: isinstance(obj, frozenset),
        serializer=lambda obj: [Serializer.serialize(item) for item in obj],
        deserializer=lambda data: frozenset(Serializer.deserialize(item) for item in data),
    )
)

Serializer.register(
    TypeSerializer(
        name="enum",
        claim=lambda obj: isinstance(obj, enum.Enum),
        serializer=omni.flux.job_queue.core.utils.get_dotted_import_path,
        deserializer=omni.flux.job_queue.core.utils.import_type_from_path,
        priority=10,
    )
)


Serializer.register(
    TypeSerializer(
        name="type",
        claim=lambda obj: isinstance(obj, type),
        serializer=omni.flux.job_queue.core.utils.get_dotted_import_path,
        deserializer=omni.flux.job_queue.core.utils.import_type_from_path,
        priority=10,
    )
)


Serializer.register(
    TypeSerializer(
        name="partial",
        claim=lambda obj: isinstance(obj, functools.partial),
        serializer=lambda obj: {
            "func": Serializer.serialize(obj.func),
            "args": Serializer.serialize(obj.args),
            "keywords": Serializer.serialize(obj.keywords),
        },
        deserializer=lambda data: functools.partial(
            Serializer.deserialize(data["func"]),
            *Serializer.deserialize(data["args"]),
            **Serializer.deserialize(data["keywords"]),
        ),
        priority=10,
    )
)


Serializer.register(
    TypeSerializer(
        name="callable",
        claim=callable,
        serializer=omni.flux.job_queue.core.utils.get_dotted_import_path,
        deserializer=omni.flux.job_queue.core.utils.import_type_from_path,
        priority=5,  # Lower than type, partial, dataclass so they get checked first
    )
)


def _serialize_dataclass(obj) -> dict:
    return {
        "__import_path__": omni.flux.job_queue.core.utils.get_dotted_import_path(obj),
        "__fields__": {
            x.name: Serializer.serialize(getattr(obj, x.name)) for x in dataclasses.fields(obj.__class__) if x.init
        },
    }


def _deserialize_dataclass(data: dict):
    cls = omni.flux.job_queue.core.utils.import_type_from_path(data["__import_path__"])
    kwargs = {k: Serializer.deserialize(v) for k, v in data["__fields__"].items()}
    return cls(**kwargs)


Serializer.register(
    TypeSerializer(
        name="dataclass",
        claim=dataclasses.is_dataclass,
        serializer=_serialize_dataclass,
        deserializer=_deserialize_dataclass,
        priority=10,
    )
)
