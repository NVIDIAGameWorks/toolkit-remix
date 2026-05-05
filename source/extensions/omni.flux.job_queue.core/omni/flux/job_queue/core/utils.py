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

import builtins
import enum
import importlib
import inspect
import os
import time
import uuid
import weakref
from typing import Any, Generic, TypeVar
from collections.abc import Callable

T = TypeVar("T")


class classproperty(property, Generic[T]):  # noqa: N801
    def __init__(self, fget: Callable[..., T]) -> None:
        super().__init__(fget)

    def __get__(self, owner_self: object | None, owner_cls: type | None = None, /) -> T:
        if self.fget is None:
            raise RuntimeError(f"Broken object '{type(self).__name__}'.")

        return self.fget(owner_cls)


def time_ms() -> int:
    """
    Get current time in milliseconds.
    """
    return time.time_ns() // 1_000_000


def uuid7() -> uuid.UUID:
    """
    Generate a UUID version 7.
    """
    ms = time_ms()

    rand_a = int.from_bytes(os.urandom(2), "big")
    rand_b = int.from_bytes(os.urandom(8), "big")

    version = 0x07
    var = 2
    rand_a &= 0xFFF
    rand_b &= 0x3FFFFFFFFFFFFFFF

    final_bytes = ms.to_bytes(6, "big")
    final_bytes += ((version << 12) + rand_a).to_bytes(2, "big")
    final_bytes += ((var << 62) + rand_b).to_bytes(8, "big")

    uuid_int = int.from_bytes(final_bytes, "big")
    return uuid.UUID(int=uuid_int)


def get_dotted_import_path(obj: Any) -> str:
    """
    Get the dotted import path of an object's class, function, or method.
    Returns a string suitable for import_type_from_path.
    """
    if obj is None:
        raise ValueError("Cannot get import path for None.")

    if isinstance(obj, enum.Enum):
        return f"{obj.__class__.__module__}.{obj.__class__.__name__}.{obj.name}"

    # Handle classes
    if inspect.isclass(obj):
        module = obj.__module__
        qualname = obj.__qualname__
        if module == "builtins":
            return qualname
        return f"{module}.{qualname}"
    # Handle functions (including module-level)
    if inspect.isfunction(obj):
        module = obj.__module__
        qualname = obj.__qualname__
        if module == "builtins":
            return qualname
        return f"{module}.{qualname}"
    # Handle bound methods (instance or class, including built-in)
    if hasattr(obj, "__self__") and hasattr(obj, "__name__"):
        self_obj = obj.__self__
        method_name = obj.__name__
        # For class methods, __self__ is the class; for instance methods, __self__ is the instance
        if inspect.isclass(self_obj):
            module = self_obj.__module__
            class_name = self_obj.__qualname__
        else:
            module = self_obj.__class__.__module__
            class_name = self_obj.__class__.__qualname__
        if module == "builtins":
            return f"{class_name}.{method_name}"
        return f"{module}.{class_name}.{method_name}"
    # Handle instances
    if hasattr(obj, "__class__"):
        module = obj.__class__.__module__
        qualname = obj.__class__.__qualname__
        if module == "builtins":
            return qualname
        return f"{module}.{qualname}"
    # Handle built-in functions (e.g., len)
    if inspect.isbuiltin(obj):
        name = getattr(obj, "__name__", None)
        if name is not None:
            return name
    raise TypeError(f"Cannot determine import path for object of type {type(obj)}")


def import_type_from_path(path: str) -> object:
    """
    Import a type, function, or method given its dotted import path.
    Handles nested classes and attributes (e.g., 'datetime.datetime.now').
    Also supports builtin types/functions (e.g., 'str', 'RuntimeError').
    """
    # Support for builtin types/functions
    if path and "." not in path and hasattr(builtins, path):
        return getattr(builtins, path)
    parts = path.split(".")
    if not parts:
        raise ImportError(f"Invalid import path: {path}")
    # Try to import the module using the longest prefix possible
    for i in range(len(parts), 0, -1):
        module_name = ".".join(parts[:i])
        try:
            obj = importlib.import_module(module_name)
            attr_parts = parts[i:]
            break
        except ModuleNotFoundError:
            continue
    else:
        # If no module found, try the first part as module
        module_name = parts[0]
        try:
            obj = importlib.import_module(module_name)
            attr_parts = parts[1:]
        except ModuleNotFoundError as exc:
            raise ImportError(f"Cannot import module from path: {path}") from exc
    # Traverse attributes
    for attr in attr_parts:
        try:
            obj = getattr(obj, attr)
        except AttributeError as exc:
            raise ImportError(f"Cannot find attribute '{attr}' in '{obj}' from path: {path}") from exc
    return obj


class WeakRef(Generic[T]):
    """
    Generic weak reference wrapper that handles both bound methods and regular objects.

    Standard weakref.ref doesn't work correctly with bound methods because a new
    method object is created each time you access it. This class handles that case
    by storing a weak reference to the instance and the method name separately.

    For objects that don't support weak references (e.g., built-in types),
    stores the object directly.

    Example::

        def callback():
            print("called")

        ref = WeakRef(callback)
        fn = ref.get()
        if fn is not None:
            fn()
    """

    def __init__(self, obj: T):
        if hasattr(obj, "__self__") and hasattr(obj, "__name__"):
            # Bound method
            self._obj_ref = weakref.ref(obj.__self__)
            self._method_name = obj.__name__
            self._is_method = True
            self._is_direct = False
        else:
            # Regular object
            try:
                self._obj_ref = weakref.ref(obj)
                self._is_method = False
                self._is_direct = False
            except TypeError:
                # Object doesn't support weak references, store directly
                self._obj = obj
                self._obj_ref = None
                self._is_method = False
                self._is_direct = True

    def get(self) -> T | None:
        if self._is_direct:
            return self._obj
        if self._obj_ref is None:
            return None
        if self._is_method:
            obj = self._obj_ref()
            if obj is None:
                return None
            return getattr(obj, self._method_name)
        return self._obj_ref()

    def is_alive(self) -> bool:
        if self._is_direct:
            return True
        if self._obj_ref is None:
            return False
        return self._obj_ref() is not None
