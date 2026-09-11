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
    "RemixAssetItem",
    "TextureAsset",
    "TextureBinding",
]

import enum
import pathlib
from dataclasses import dataclass, field

from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineItem
from pxr import Sdf


class AssetKind(enum.Enum):
    """Top-level asset families supported by the Remix asset pipeline."""

    TEXTURE = "texture"
    MODEL = "model"


@dataclass
class TextureAsset:
    """One image file to process into a Remix-ready texture.

    The conversion steps do not care whether this came from ComfyUI, Asset
    Library, a referenced model texture, or an extracted embedded model texture.

    For a non-UDIM texture ``udim_tiles`` is an empty tuple and ``path`` is the sole
    concrete output. For a UDIM texture ``udim_tiles`` carries every converted concrete
    tile and ``path`` is the first tile, so downstream steps and publication walk the
    complete set.
    """

    path: pathlib.Path
    texture_type: TextureTypes
    key: str = ""
    original_path: pathlib.Path | None = None
    udim_tiles: tuple[pathlib.Path, ...] = ()

    @property
    def source_path(self) -> pathlib.Path:
        """Return the stable source path used for output naming and reuse checks."""
        return self.original_path or self.path


@dataclass
class TextureBinding:
    """Typed USD binding from a model shader input to one TextureAsset.

    This is model rewrite state, not texture conversion state. It lets the final
    model step replace the original USD asset path with the processed texture path.

    ``material_path`` is the correlation identity. Material conversion rewrites the shader
    between the prepare walk and the mesh walk, so only the owning material prim path survives
    both. See :func:`lightspeed.trex.asset_pipeline.core.jobs.models.derive_texture_key`.
    """

    shader_path: Sdf.Path
    input_name: str
    original_asset_path: Sdf.AssetPath
    texture: TextureAsset
    material_path: str = ""


@dataclass
class RemixAssetItem(PipelineItem[pathlib.Path]):
    """Stable item type for the whole Remix asset pipeline.

    ``value`` is the current primary asset path. For a model, it starts as the
    source model and becomes the generated/collected USD path after import. For a
    texture, it remains the source texture path while ``textures[0].path`` becomes
    the processed texture path.

    ``collected_dependencies`` maps original dependency paths to workspace copies.
    The collector supplies these runtime identities when it imports the model.
    """

    kind: AssetKind
    source_path: pathlib.Path
    textures: list[TextureAsset] = field(default_factory=list)
    texture_bindings: list[TextureBinding] = field(default_factory=list)
    collected_dependencies: dict[pathlib.Path, pathlib.Path] = field(default_factory=dict)

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
    def from_model(cls, path: pathlib.Path) -> RemixAssetItem:
        """Create a model item."""
        return cls(
            value=path,
            kind=AssetKind.MODEL,
            source_path=path,
        )
