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

__all__ = ["DiscoverTexturesStep"]

import pathlib

import omni.usd
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.common.path_utils import get_absolute_path_from_relative, get_udim_sequence, is_udim_texture
from pxr import Sdf, UsdShade, UsdUtils

from ..jobs.models import TextureLedgerEntry, derive_texture_key
from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import AssetKind, RemixAssetItem, TextureAsset
from ..pipeline.texture_inputs import get_source_texture_paths, get_texture_source_identity, iter_texture_inputs
from ..worker import run_in_worker_thread


def _texture_exists(path: pathlib.Path) -> bool:
    """Return whether a texture path names a readable file or a UDIM pattern with at least one tile.

    A ``<UDIM>`` token path names a pattern, not a concrete file, so ``exists()`` is always false for
    it; its tiles decide instead.
    """
    if is_udim_texture(str(path)):
        return bool(get_udim_sequence(str(path)))
    return path.exists()


class DiscoverTexturesStep(PipelineStep):
    """Discover model texture records and referenced layers without mutating the stage.

    The step walks shader prims after model import, determines each texture's
    semantic type from its shader input name, and records the composed layer
    identifiers. It does not save or modify the stage.
    """

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "discover_textures"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Discover model textures"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when a model item has no discovered texture records yet."""
        state = context.execution_state.get(self.name)
        if state and state.did_run:
            return False
        return any(item.kind is AssetKind.MODEL and not item.textures for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why texture discovery has no work."""
        if not any(item.kind is AssetKind.MODEL for item in context.items):
            return "no model items"
        return "all model textures are already discovered"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Discover texture records and composed layers from the model stage.

        The step reads the imported model stage, walks shader prims, and records
        each texture's resolved path and semantic type. It does not collect
        texture bindings (that happens after material conversion in the mesh
        phase). It stores the composed layer identifiers on the context.

        Raises:
            FileNotFoundError: If an authored texture path cannot be resolved.
            ValueError: If a model authors an unknown normal-map encoding.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            source_texture_paths = get_source_texture_paths(item)
            stage = await context.open_stage(item.value)

            # Record the composed layers before shader traversal, so the mesh phase knows every
            # layer this model pulls in without opening the stage a second time.
            layers, _assets, _unresolved_paths = await run_in_worker_thread(
                UsdUtils.ComputeAllDependencies, stage.GetRootLayer().identifier
            )
            context.referenced_layers = tuple(layer.identifier for layer in layers)

            item.textures.clear()
            texture_by_key: dict[tuple[pathlib.Path, TextureTypes], TextureAsset] = {}
            texture_ledger: list = []

            for prim in stage.Traverse():
                if not prim.IsA(UsdShade.Material):
                    continue
                shader_prim = omni.usd.get_shader_from_material(prim, get_prim=True)
                if shader_prim is None or not shader_prim.IsValid():
                    continue

                material_path = str(prim.GetPath())
                for texture_type, input_name in iter_texture_inputs(shader_prim):
                    attr = shader_prim.GetAttribute(input_name)
                    if not attr or not attr.HasAuthoredValue():
                        continue

                    original_asset_path = attr.Get()
                    if not isinstance(original_asset_path, Sdf.AssetPath) or not original_asset_path.path:
                        continue

                    resolved_path = pathlib.Path(
                        original_asset_path.resolvedPath
                        or get_absolute_path_from_relative(original_asset_path.path, stage.GetRootLayer())
                    )
                    if not await run_in_worker_thread(_texture_exists, resolved_path):
                        # Material conversion rewrites shader inputs but not texture paths, so a
                        # relative texture path still points next to the original source file rather
                        # than into the work copy. The mesh phase sees the materialized paths instead.
                        resolved_path = (item.source_path.parent / original_asset_path.path).resolve()
                    if not await run_in_worker_thread(_texture_exists, resolved_path):
                        raise FileNotFoundError(
                            f"Texture path on {attr.GetPath()} does not resolve to a readable file: "
                            f"{original_asset_path.path}"
                        )

                    texture_key_pair = (resolved_path, texture_type)
                    texture = texture_by_key.get(texture_key_pair)
                    if texture is None:
                        texture = TextureAsset(
                            path=resolved_path,
                            texture_type=texture_type,
                            key=derive_texture_key(material_path, texture_type),
                            original_path=get_texture_source_identity(item, resolved_path, source_texture_paths),
                        )
                        texture_by_key[texture_key_pair] = texture
                        item.textures.append(texture)

                    # Two materials may share one file. The file is converted once, under the first
                    # material's key, and every sharing material points at that same key.
                    texture_ledger.append(
                        TextureLedgerEntry(
                            material_path=material_path,
                            texture_type=texture_type,
                            texture_key=texture.key,
                        )
                    )

            context.texture_ledger = tuple(texture_ledger)
