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

from collections.abc import Callable, Iterable

from .persistence_codec import CORE_PERSISTENCE_CODECS, PersistenceCodec

__all__ = ("PersistenceCodec", "PersistenceRegistry", "get_registry", "shutdown", "startup")


class PersistenceRegistry:
    """Resolve explicitly registered codecs by stable name or exact Python type."""

    def __init__(self) -> None:
        """Initialize empty forward and reverse codec indexes."""
        self._codecs_by_name: dict[str, PersistenceCodec] = {}
        self._names_by_type: dict[type, str] = {}
        self._changed_callback: Callable[[], None] | None = None

    def register_codecs(self, codecs: Iterable[PersistenceCodec]) -> None:
        """Register persistence codecs atomically.

        Args:
            codecs: Codec values that bind stable names to exact Python types.

        Raises:
            TypeError: If an item is not a persistence codec.
            ValueError: If a name or Python type conflicts with a registered codec.
        """
        codecs = tuple(codecs)
        codecs_by_name = self._codecs_by_name.copy()
        names_by_type = self._names_by_type.copy()
        for codec in codecs:
            if type(codec) is not PersistenceCodec:
                raise TypeError("Queue persistence registrations must be PersistenceCodec values")
            registered_codec = codecs_by_name.get(codec.name)
            if registered_codec is not None and registered_codec is not codec:
                raise ValueError(f"Persistence identifier '{codec.name}' is already registered")
            registered_name = names_by_type.get(codec.value_type)
            if registered_name is not None and registered_name != codec.name:
                raise ValueError(f"{codec.value_type.__name__} is already registered as '{registered_name}'")

            codecs_by_name[codec.name] = codec
            names_by_type[codec.value_type] = codec.name

        self._codecs_by_name = codecs_by_name
        self._names_by_type = names_by_type
        if self._changed_callback is not None:
            self._changed_callback()

    def unregister_codecs(self, codecs: Iterable[PersistenceCodec]) -> None:
        """Unregister exact persistence codecs atomically.

        Args:
            codecs: Codec values previously registered with this registry.

        Raises:
            ValueError: If any codec is absent or differs from the registered codec.
        """
        codecs = tuple(codecs)
        for codec in codecs:
            if self.get_codec(codec.name) is not codec:
                raise ValueError(f"Persistence codec '{codec.name}' is not registered")

        for codec in codecs:
            self._codecs_by_name.pop(codec.name)
            self._names_by_type.pop(codec.value_type)
        if self._changed_callback is not None:
            self._changed_callback()

    def set_changed_callback(self, callback: Callable[[], None] | None) -> None:
        """Set the process-owned registration change callback.

        Args:
            callback: Callback invoked after exact registration changes.
        """
        self._changed_callback = callback

    def get_name(self, value_type: type) -> str | None:
        """Return the stable registered name for a Python type.

        Args:
            value_type: Python type to resolve.

        Returns:
            Stable persistence name, or ``None`` when the type is unavailable.
        """
        return self._names_by_type.get(value_type)

    def get_type(self, name: str) -> type | None:
        """Return the Python type exposed by a registered plugin.

        Args:
            name: Stable persistence codec name.

        Returns:
            Registered Python type, or ``None`` when the codec is unavailable.
        """
        codec = self.get_codec(name)
        return codec.value_type if codec is not None else None

    def get_codec_for_type(self, value_type: type) -> PersistenceCodec | None:
        """Return the codec registered for one exact Python type.

        Args:
            value_type: Exact Python type to resolve.

        Returns:
            Registered codec or ``None``.
        """
        name = self._names_by_type.get(value_type)
        return None if name is None else self._codecs_by_name[name]

    def get_codec(self, name: str) -> PersistenceCodec | None:
        """Return the codec registered under one stable name.

        Args:
            name: Stable persisted identifier.

        Returns:
            Registered codec or ``None``.
        """
        return self._codecs_by_name.get(name)

    def destroy(self) -> None:
        """Release all registered codecs and callbacks."""
        self._codecs_by_name.clear()
        self._names_by_type.clear()
        self._changed_callback = None


_registry: PersistenceRegistry | None = None


def get_registry() -> PersistenceRegistry:
    """Return the process-wide persistence registry.

    Returns:
        Registry created by the job queue extension.

    Raises:
        RuntimeError: If the job queue extension has not started.
    """
    if _registry is None:
        raise RuntimeError("Job queue core extension is not started")
    return _registry


def startup() -> None:
    """Create the extension-owned registry and register its built-in codecs.

    Raises:
        RuntimeError: If the registry is already active.
    """
    global _registry
    if _registry is not None:
        raise RuntimeError("Job queue persistence registry is already started")
    _registry = PersistenceRegistry()
    _registry.register_codecs(CORE_PERSISTENCE_CODECS)


def shutdown() -> None:
    """Destroy the extension-owned persistence registry."""
    global _registry
    if _registry is not None:
        _registry.destroy()
    _registry = None
