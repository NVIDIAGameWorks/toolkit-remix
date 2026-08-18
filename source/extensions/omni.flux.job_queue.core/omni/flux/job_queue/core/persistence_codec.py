"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import pathlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .job import ApplyBinding, JobOutputPort

__all__ = ("CORE_PERSISTENCE_CODECS", "PersistenceCodec", "decode_positional_payload")


@dataclass(frozen=True, slots=True)
class PersistenceCodec:
    """Bind one stable persisted identifier to an exact Python type.

    Attributes:
        name: Stable identifier stored in the queue database.
        value_type: Exact Python type represented by the identifier.
        encoder: Optional conversion from a custom value to supported queue values.
        decoder: Optional conversion from supported queue values to the custom value.
    """

    name: str
    value_type: type
    encoder: Callable[[Any], Any] | None = None
    decoder: Callable[[Any], Any] | None = None

    def __post_init__(self) -> None:
        """Validate the complete codec declaration.

        Raises:
            TypeError: If the declaration is incomplete or has invalid field types.
        """
        if type(self.name) is not str or not self.name:
            raise TypeError("Persistence codec names must be non-empty strings")
        if not isinstance(self.value_type, type):
            raise TypeError(f"Persistence codec '{self.name}' must expose a Python type")
        if (self.encoder is None) != (self.decoder is None):
            raise TypeError(f"Persistence codec '{self.name}' must define both encoder and decoder")
        if self.encoder is not None and (not callable(self.encoder) or not callable(self.decoder)):
            raise TypeError(f"Persistence codec '{self.name}' encoder and decoder must be callable")


def decode_positional_payload(value_type: type, payload: Any, length: int) -> Any:
    """Construct one registered value from an exact positional payload.

    Args:
        value_type: Exact registered type to construct.
        payload: Decoded custom payload.
        length: Exact number of values required by the codec.

    Returns:
        Constructed value.

    Raises:
        TypeError: If the payload is not an exact tuple.
        ValueError: If the tuple has the wrong number of values.
    """
    if type(payload) is not tuple:
        raise TypeError(f"{value_type.__name__} payload must be a tuple")
    if len(payload) != length:
        raise ValueError(f"{value_type.__name__} payload must contain exactly {length} values")
    return value_type(*payload)


CORE_PERSISTENCE_CODECS = (
    PersistenceCodec(
        "ApplyBinding",
        ApplyBinding,
        lambda value: (value.output_port, value.handler_type, value.target),
        lambda payload: decode_positional_payload(ApplyBinding, payload, 3),
    ),
    PersistenceCodec(
        "JobOutputPort",
        JobOutputPort,
        lambda value: (value.name, value.value_type),
        lambda payload: decode_positional_payload(JobOutputPort, payload, 2),
    ),
    PersistenceCodec("pathlib.Path", pathlib.Path),
    PersistenceCodec("uuid.UUID", uuid.UUID),
    PersistenceCodec("bool", bool),
    PersistenceCodec("bytes", bytes),
    PersistenceCodec("dict", dict),
    PersistenceCodec("float", float),
    PersistenceCodec("frozenset", frozenset),
    PersistenceCodec("int", int),
    PersistenceCodec("list", list),
    PersistenceCodec("set", set),
    PersistenceCodec("str", str),
    PersistenceCodec("tuple", tuple),
)
