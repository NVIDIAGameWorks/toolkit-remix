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

__all__ = [
    "ProcessedTexture",
    "TextureProcessingItem",
    "TextureProcessingRequest",
    "TextureProcessingResult",
]

import pathlib
from dataclasses import dataclass

from omni.flux.asset_importer.core.data_models import TextureTypes


def _validate_texture_fields(key: str, path: pathlib.Path, texture_type: TextureTypes) -> None:
    """Validate fields shared by source and processed texture records.

    Args:
        key: Stable caller-defined item identifier.
        path: Local source path identifying the asset.
        texture_type: Required texture semantic.

    Raises:
        TypeError: If any field has an invalid type.
        ValueError: If the key is blank.
    """
    if type(key) is not str:
        raise TypeError("key must be a str")
    if not key.strip():
        raise ValueError("key must not be blank")
    if not isinstance(path, pathlib.Path):
        raise TypeError("path must be a pathlib.Path")
    if not isinstance(texture_type, TextureTypes):
        raise TypeError("texture_type must be a TextureTypes value")


@dataclass(frozen=True, slots=True)
class TextureProcessingItem:
    """Describe one local source texture and its required Remix semantic.

    Attributes:
        key: Stable caller-defined identifier preserved through processing.
        path: Local source path consumed by the Remix texture pipeline.
        texture_type: Required texture semantic.
    """

    key: str
    path: pathlib.Path
    texture_type: TextureTypes

    def __post_init__(self) -> None:
        """Validate the persisted texture boundary.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If the stable key is blank.
        """
        _validate_texture_fields(self.key, self.path, self.texture_type)


@dataclass(frozen=True, slots=True)
class TextureProcessingRequest:
    """Provide one ordered texture batch and its publication destination.

    Attributes:
        items: Local source textures in stable caller order.
        source_root: Stable project or import root preserved in output paths.
        output_url: Explicit local or remote destination, or ``None`` to keep outputs in the job directory.
    """

    items: tuple[TextureProcessingItem, ...]
    source_root: pathlib.Path
    output_url: str | None

    def __post_init__(self) -> None:
        """Validate the persisted request boundary.

        Raises:
            TypeError: If request fields do not have their exact persisted types.
            ValueError: If the request has no items or its explicit publication URL is blank.
        """
        if type(self.items) is not tuple or not all(type(item) is TextureProcessingItem for item in self.items):
            raise TypeError("items must be a tuple of TextureProcessingItem values")
        if not self.items:
            raise ValueError("items must not be empty")
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("item keys must be unique within one request")
        if not isinstance(self.source_root, pathlib.Path):
            raise TypeError("source_root must be a pathlib.Path")
        if self.output_url is not None and type(self.output_url) is not str:
            raise TypeError("output_url must be a str or None")
        if self.output_url is not None and not self.output_url.strip():
            raise ValueError("output_url must not be blank")


@dataclass(frozen=True, slots=True)
class ProcessedTexture:
    """Identify one source texture and its final published output.

    Attributes:
        key: Stable caller-defined identifier preserved from the source request.
        source_path: Original local source path used for stable correlation.
        asset_url: Final local path or remote URL safe to pass to Apply handlers.
        texture_type: Final texture semantic after processing.
    """

    key: str
    source_path: pathlib.Path
    asset_url: str
    texture_type: TextureTypes

    def __post_init__(self) -> None:
        """Validate the immutable processed-texture boundary.

        Raises:
            TypeError: If a field has an invalid type.
            ValueError: If the stable key or URL is blank.
        """
        _validate_texture_fields(self.key, self.source_path, self.texture_type)
        if type(self.asset_url) is not str:
            raise TypeError("asset_url must be a str")
        if not self.asset_url.strip():
            raise ValueError("asset_url must not be blank")


@dataclass(frozen=True, slots=True)
class TextureProcessingResult:
    """Contain immutable processed textures in their original request order.

    Attributes:
        items: Fully published textures safe for downstream Apply bindings.
    """

    items: tuple[ProcessedTexture, ...]

    def __post_init__(self) -> None:
        """Validate the exact persisted result shape.

        Raises:
            TypeError: If items is not an exact tuple of processed textures.
            ValueError: If the result is empty.
        """
        if type(self.items) is not tuple or not all(type(item) is ProcessedTexture for item in self.items):
            raise TypeError("items must be a tuple of ProcessedTexture values")
        if not self.items:
            raise ValueError("items must not be empty")
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("item keys must be unique within one result")
