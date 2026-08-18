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

__all__ = [
    "ConstantResolver",
    "LayerIdentifierResolver",
    "SelectedPrimPathResolver",
]

import dataclasses
import pathlib
from typing import ClassVar

from omni.flux.utils.common.path_utils import is_file_path_valid
from pxr import Usd

from .base import (
    ResolverConfigurationError,
    ResolverParameter,
    ResolverValueError,
    ValueResolver,
    normalize_native_value,
)


@dataclasses.dataclass
class ConstantResolver(ValueResolver[object]):
    """Resolves every selected prim to one configured static value."""

    label: ClassVar[str] = "Constant"
    is_fallback: ClassVar[bool] = True
    value: object = None
    value_type: type = object

    def __post_init__(self) -> None:
        """Infer or validate the exact native type stored by this Constant."""
        if self.value_type is object and self.value is not None:
            self.value_type = pathlib.Path if isinstance(self.value, pathlib.Path) else type(self.value)
        if self.value_type is not object:
            self.value = normalize_native_value(self.value_type, self.value)

    @property
    def parameters(self) -> tuple[ResolverParameter[object], ...]:
        """Return the editable constant value binding.

        Returns:
            Single binding that reads and writes the configured constant.
        """
        return (
            ResolverParameter(
                "value",
                self.value_type,
                lambda: self.value,
                self._set_value,
                tooltip="The fixed value sent to the workflow for every processed material.",
            ),
        )

    @classmethod
    def create(cls, default_value: object, context_name: str | None = None) -> "ConstantResolver":
        """Create an empty constant matching the workflow-authored value's native type.

        Args:
            default_value: Authored workflow value used only to infer the native type.
            context_name: USD context supplied by the generic factory and unused by constants.

        Returns:
            Constant resolver initialized with the native type's empty value.
        """
        value_type = pathlib.Path if isinstance(default_value, pathlib.Path) else type(default_value)
        return cls(value_type=value_type)

    def _set_value(self, value: object) -> None:
        """Store an edited constant resolver value.

        Args:
            value: New constant returned for every selected prim.
        """
        self.value = normalize_native_value(self.value_type, value) if self.value_type is not object else value

    def __call__(self, prim: Usd.Prim) -> object:
        """Return the configured value without inspecting the prim.

        Args:
            prim: Selected USD prim ignored by this resolver.

        Returns:
            Configured constant value.

        Raises:
            ResolverConfigurationError: If a configured file path cannot be read.
        """
        if self.value_type is pathlib.Path and not is_file_path_valid(str(self.value), log_error=False):
            raise ResolverConfigurationError("Select a valid file for this workflow input, then try again.")
        return self.value


@dataclasses.dataclass
class SelectedPrimPathResolver(ValueResolver[str]):
    """Resolve the actual material prim path supplied by the generation flow."""

    label: ClassVar[str] = "Selected Prim"
    native_types: ClassVar[tuple[type, ...]] = (str,)

    def __call__(self, prim: Usd.Prim) -> str:
        """Return the selected material prim path.

        Args:
            prim: Material prim supplied by ComfyUI generation.

        Returns:
            Absolute USD prim path string.
        """
        return str(prim.GetPath())


@dataclasses.dataclass
class LayerIdentifierResolver(ValueResolver[str]):
    """Resolve the root layer identifier for the material prim's stage."""

    label: ClassVar[str] = "Current Layer"
    native_types: ClassVar[tuple[type, ...]] = (str,)

    def __call__(self, prim: Usd.Prim) -> str:
        """Return the root layer identifier for the selected material.

        Args:
            prim: Material prim supplied by ComfyUI generation.

        Returns:
            Identifier of the material stage's root layer.

        Raises:
            ResolverValueError: If the material prim has no stage.
        """
        stage = prim.GetStage()
        if stage is None:
            raise ResolverValueError("The current layer could not be read. Reopen the project and try again.")
        return stage.GetRootLayer().identifier
