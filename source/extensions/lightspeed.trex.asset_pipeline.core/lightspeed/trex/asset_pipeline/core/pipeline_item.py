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
    "AssetKind",
    "MaterialType",
    "RemixAssetItem",
    "TextureAsset",
    "TextureBinding",
    "get_texture_source_path",
    "iter_pipeline_output_paths",
    "iter_texture_assets",
]

import enum
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass, field

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineItem
from pxr import Sdf


class AssetKind(enum.Enum):
    """Top-level asset families supported by the Remix asset pipeline."""

    TEXTURE = "texture"
    MODEL = "model"


class MaterialType(enum.Enum):
    """Material opacity families accepted by the Remix model pipeline."""

    OPAQUE = "opaque"
    TRANSLUCENT = "translucent"


@dataclass
class TextureAsset:
    """One image file to process into a Remix-ready texture.

    The conversion steps do not care whether this came from ComfyUI, Asset
    Library, a referenced model texture, or an extracted embedded model texture.
    """

    path: pathlib.Path
    texture_type: TextureTypes
    original_path: pathlib.Path | None = None


@dataclass
class TextureBinding:
    """Typed USD binding from a model shader input to one TextureAsset.

    This is model rewrite state, not texture conversion state. It lets the final
    model step replace the original USD asset path with the processed texture path.
    """

    shader_path: Sdf.Path
    input_name: str
    original_asset_path: Sdf.AssetPath
    texture: TextureAsset


@dataclass
class RemixAssetItem(PipelineItem[pathlib.Path]):
    """Stable item type for the whole Remix asset pipeline.

    ``value`` is the current primary asset path. For a model, it starts as the
    source model and becomes the generated/collected USD path after import. For a
    texture, it remains the source texture path while ``textures[0].path`` becomes
    the processed texture path.
    """

    kind: AssetKind
    source_path: pathlib.Path
    material_type: MaterialType | None = None
    textures: list[TextureAsset] = field(default_factory=list)
    texture_bindings: list[TextureBinding] = field(default_factory=list)

    @classmethod
    def from_texture(
        cls,
        path: pathlib.Path,
        texture_type: TextureTypes,
    ) -> RemixAssetItem:
        """Create a texture item with one typed texture record."""
        return cls(
            value=path,
            kind=AssetKind.TEXTURE,
            source_path=path,
            textures=[
                TextureAsset(
                    path=path,
                    texture_type=texture_type,
                    original_path=path,
                )
            ],
        )

    @classmethod
    def from_model(
        cls,
        path: pathlib.Path,
        material_type: MaterialType,
    ) -> RemixAssetItem:
        """Create a model item with the caller-selected opacity family."""
        return cls(
            value=path,
            kind=AssetKind.MODEL,
            source_path=path,
            material_type=material_type,
        )


def iter_texture_assets(context: PipelineContext[RemixAssetItem]) -> Iterator[TextureAsset]:
    """Yield every texture record currently owned by the pipeline context."""
    for item in context.items:
        yield from item.textures


def iter_pipeline_output_paths(context: PipelineContext[RemixAssetItem]) -> Iterator[pathlib.Path]:
    """Yield every file path that should be published or receive metadata."""
    for item in context.items:
        if item.kind is AssetKind.MODEL:
            yield item.value
        for texture in item.textures:
            yield texture.path


def get_texture_source_path(texture: TextureAsset) -> pathlib.Path:
    """Return the stable source path used for output naming and reuse checks."""
    return texture.original_path or texture.path
