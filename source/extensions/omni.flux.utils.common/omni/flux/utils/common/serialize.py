"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("Converter", "Serializer", "register_std")

import dataclasses
import functools
import inspect
import json
from typing import Any, Callable, Generic, Mapping, Type, TypeAlias, TypeVar, Union

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
PrimitiveValue: TypeAlias = Union[JSON, "Primitive"]
T = TypeVar("T")


@dataclasses.dataclass
class Converter(Generic[T]):
    """
    A dataclass which holds methods used to convert data from one format to another.
    """

    key: str
    claim_func: Callable[[Any], bool]
    serialize_hook: Callable[[T], PrimitiveValue] = dataclasses.field(default=lambda x: x)
    deserialize_hook: Callable[[PrimitiveValue], T] = dataclasses.field(default=lambda x: x)


@dataclasses.dataclass(frozen=True)
class Primitive(Generic[T]):
    """
    Holds a key to a `Converter` and a primitive value.
    """

    _KEY_REMAP = {"key": "_key", "value": "_value"}

    key: str
    value: PrimitiveValue

    @classmethod
    def is_serialized_primitive(cls, data: Any) -> bool:
        return isinstance(data, Mapping) and all(k in data for k in cls._KEY_REMAP.values())

    @classmethod
    def from_serialized(cls, data: Any) -> "Primitive[T]":
        if isinstance(data, Primitive):
            return data
        if cls.is_serialized_primitive(data):
            return cls(key=data["_key"], value=data["_value"])
        raise TypeError(data)

    def asdict(self) -> dict[str, PrimitiveValue]:
        return dataclasses.asdict(self, dict_factory=lambda kv: {self._KEY_REMAP[k]: v for k, v in kv})


class Serializer(Generic[T]):
    """
    A utility class that provides methods to serialize and deserialize objects using custom registered hooks.

    Examples
    --------
    There are a few ways to configure the serializer to handle custom types.

    [Option 1 : Direct Converter instance]
    >>> import datetime
    ...
    >>> serializer = Serializer()
    ...
    >>> serializer.register_converter(
    ...     Converter(
    ...         key="datetime.datetime",
    ...         claim_func=lambda x: isinstance(x, datetime.datetime),
    ...         serialize_hook=lambda dt: dt.isoformat(),
    ...         deserialize_hook=datetime.datetime.fromisoformat,
    ...     )
    ... )

    [Option 2 : Register serialize/deserialize hook decorators]
    >>> import datetime
    ...
    >>> serializer = Serializer()
    ...
    >>> @serializer.register_serialize_hook(datetime.datetime)
    >>> def serialize_datetime(dt):
    ...     return dt.isoformat()
    ...
    >>> @serializer.register_deserialize_hook(datetime.datetime)
    >>> def deserialize_datetime(s):
    ...     return datetime.datetime.fromisoformat(s)
    """

    def __init__(self):
        self._converters: list[Converter] = []

    def register_converter(self, converter: Converter):
        """
        Add a converter to the registry of available converters.
        """
        if any(c.key == converter.key for c in self._converters):
            raise ValueError(f"A converter with key {converter.key} is already registered.")
        self._converters.append(converter)

    @classmethod
    def _resolve_key_and_claim_func(
        cls, claim_func_or_type: Type | Callable[[Any], bool], key: str | None = None
    ) -> tuple[str, Callable[[Any], bool]]:
        """
        Used with the `register_serialize_hook` decorator to determine if the user provided a claim function or type.
        """
        if inspect.isfunction(claim_func_or_type):
            claim_func = claim_func_or_type
            if key is None:
                raise ValueError("Must provide a key if providing a claim function directly.")
        else:

            def claim_func(obj):
                return isinstance(obj, claim_func_or_type)

            if key is None:
                mod = claim_func_or_type.__module__
                if mod == "builtins":
                    key = claim_func_or_type.__qualname__
                else:
                    key = f"{mod}.{claim_func_or_type.__qualname__}"
        return key, claim_func

    def _get_or_create_converter(self, claim_func_or_type: Type | Callable[[Any], bool], key: str | None = None):
        """
        Get an existing converter or create a new one.

        Converter uniqueness is determined by the `key` which is either specified as a kwarg or auto-calculated from
        `claim_func_or_type`.
        """
        key, claim_func = self._resolve_key_and_claim_func(claim_func_or_type, key=key)
        for converter in reversed(self._converters):
            if converter.key == key:
                converter.claim_func = claim_func
                return converter
        result = Converter(key=key, claim_func=claim_func)
        self._converters.append(result)
        return result

    def register_serialize_hook(self, claim_func_or_type: Type | Callable[[Any], bool], key: str | None = None):
        """
        Decorator used to register a serialize hook for specific type(s).
        """
        converter = self._get_or_create_converter(claim_func_or_type, key=key)

        def _deco(fn):
            converter.serialize_hook = fn
            return fn

        return _deco

    def register_deserialize_hook(self, claim_func_or_type: Type | Callable[[Any], bool], key: str | None = None):
        """
        Decorator used to register a deserialize hook for specific type(s).
        """
        converter = self._get_or_create_converter(claim_func_or_type, key=key)

        def _deco(fn):
            converter.deserialize_hook = fn
            return fn

        return _deco

    def to_primitive(self, obj: T) -> Primitive[T] | T:
        """
        Check for any registered converters for `obj`, if one exists, then call its serialize hook to convert it into
        a primitive type.
        """
        for converter in reversed(self._converters):
            if converter.claim_func(obj):
                return Primitive(key=converter.key, value=converter.serialize_hook(obj))
        return obj

    def deserialize(self, data: JSON) -> T:
        """
        Deserialize json data back into native types.
        """
        try:
            primitive = Primitive.from_serialized(data)
        except TypeError:
            return data

        for converter in reversed(self._converters):
            if primitive.key == converter.key:
                return converter.deserialize_hook(primitive.value)
        return data

    def serialize(self, obj: T) -> JSON:
        """
        Serialize `obj` to something json friendly.

        This method is called recursively for nested types such as `tuple`, `list`, `set`, and `dict`.
        """
        primitive = self.to_primitive(obj)
        if isinstance(primitive, Primitive):
            primitive = primitive.asdict()

        if isinstance(primitive, Mapping):
            primitive = {self.serialize(k): self.serialize(v) for k, v in primitive.items()}
        elif isinstance(primitive, (tuple, list, set)):
            primitive = [self.serialize(x) for x in primitive]
        return primitive

    def dumps(self, obj: T) -> JSON:
        """
        Wrapper for `json.dumps` which will serialize any complex types using the registered converters.
        """
        return json.dumps(obj, cls=functools.partial(SerializerJSONEncoder, self))

    def loads(self, s: JSON) -> T:
        """
        Wrapper for `json.loads` which will deserialize into native types using the registered converters.
        """
        return json.loads(s, object_hook=self.deserialize)


class SerializerJSONEncoder(json.JSONEncoder):
    def __init__(self, serializer: Serializer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.serializer = serializer

    def encode(self, o):
        return super().encode(self.serializer.serialize(o))


def register_std(serializer: Serializer):
    """
    Simple helper method to register converters for common standard library types.
    """
    import datetime

    serializer.register_converter(
        Converter(
            key="datetime.datetime",
            claim_func=lambda x: isinstance(x, datetime.datetime),
            serialize_hook=lambda x: x.isoformat(),
            deserialize_hook=datetime.datetime.fromisoformat,
        )
    )

    # Converter for tuple so the type is maintained.
    serializer.register_converter(
        Converter(
            key="tuple",
            claim_func=lambda x: isinstance(x, tuple),
            serialize_hook=list,
            deserialize_hook=tuple,
        )
    )

    # Converter for set so the type is maintained.
    serializer.register_converter(
        Converter(
            key="set",
            claim_func=lambda x: isinstance(x, set),
            serialize_hook=list,
            deserialize_hook=set,
        )
    )
