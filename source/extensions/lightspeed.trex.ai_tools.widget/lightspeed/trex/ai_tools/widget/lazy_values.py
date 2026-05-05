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

import dataclasses
import inspect
import pathlib
from collections.abc import Callable
from typing import Generic, TypeVar, get_type_hints

from lightspeed.trex.ai_tools.widget.comfy import Field
from omni.flux.asset_importer.core.data_models import TextureTypes
from pxr import Usd

T = TypeVar("T")


def get_callable_interface(func: Callable[[Usd.Prim], T]) -> tuple[tuple[Field, ...], type[T]]:
    """Extract field definitions and return type from a callable."""
    fields = []
    return_type = None

    if dataclasses.is_dataclass(func):
        type_hints = get_type_hints(type(func))
        for field in dataclasses.fields(func):
            native_type = type_hints.get(field.name, field.type)
            fields.append(
                Field(
                    name=field.name,
                    native_type=native_type,
                    default_value=field.default if field.default is not dataclasses.MISSING else None,
                    value=field.default if field.default is not dataclasses.MISSING else None,
                )
            )

    if not inspect.isfunction(func) and not inspect.ismethod(func):
        target = getattr(func, "__call__", None)  # noqa: B004
    else:
        target = func

    if target and callable(target):
        sig = inspect.signature(target)
        type_hints = get_type_hints(target)
        return_type = type_hints.get(
            "return",
            sig.return_annotation if sig.return_annotation != inspect.Signature.empty else type(None),
        )

        if not dataclasses.is_dataclass(func):
            params = list(sig.parameters.values())
            start_idx = 1 if params and params[0].name in ("self", "prim") else 0

            for param in params[start_idx:]:
                native_type = type_hints.get(
                    param.name,
                    param.annotation if param.annotation != inspect.Parameter.empty else type(None),
                )
                fields.append(
                    Field(
                        name=param.name,
                        native_type=native_type,
                        default_value=param.default if param.default != inspect.Parameter.empty else None,
                        value=param.default if param.default != inspect.Parameter.empty else None,
                    )
                )

    return tuple(fields), return_type


@dataclasses.dataclass
class LazyValue(Generic[T]):
    """A lazy value that is evaluated at job submission time."""

    func: Callable[[Usd.Prim], T]
    return_type: type[T]
    label: str
    fields: list[Field] = dataclasses.field(default_factory=list)
    description: str = ""

    @classmethod
    def from_callable(cls, func):
        fields, return_type = get_callable_interface(func)
        return cls(
            func=func,
            return_type=return_type,
            label=func.__name__,
            fields=fields,
            description=func.__doc__ or "",
        )

    def __call__(self, prim: Usd.Prim) -> T:
        return self.func(prim)


@dataclasses.dataclass
class TexturePath:
    """
    Lazy value that extracts a texture path from a prim.

    Traverses related prims to find the shader and extract the texture
    path for the specified texture type.

    Attributes:
        texture_type: The type of texture to extract (default: DIFFUSE).

    Raises:
        ValueError: If the prim doesn't have exactly one texture of the specified type.
    """

    texture_type: TextureTypes = TextureTypes.DIFFUSE

    def __call__(self, prim: Usd.Prim) -> pathlib.Path:
        # Import here to avoid circular imports
        from lightspeed.trex.ai_tools.widget.job_generator import iter_texture_path  # noqa: PLC0415

        paths = set(iter_texture_path(prim, self.texture_type))
        if len(paths) != 1:
            raise ValueError(f"Expected exactly one texture path for prim {prim.GetPath()}, got {len(paths)}, {paths}")
        return pathlib.Path(paths.pop())


LAZY_VALUE_REGISTRY = [
    LazyValue(
        func=TexturePath(),
        return_type=pathlib.Path,
        label="Selected Texture Path (Diffuse)",
        description="Gets the diffuse texture path from the selected prim",
    ),
]
