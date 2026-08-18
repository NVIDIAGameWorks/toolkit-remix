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

__all__ = ["CollectTexturesStep"]

import pathlib
from collections.abc import Iterator

import carb
import omni.usd
from lightspeed.common.constants import MATERIAL_INPUTS_NORMALMAP_ENCODING, NormalMapEncodings
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes, UsdExtensions
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.common.path_utils import get_absolute_path_from_relative
from pxr import Sdf, Usd, UsdShade

from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import AssetKind, RemixAssetItem, TextureAsset, TextureBinding
from ..worker import run_in_worker_thread


class CollectTexturesStep(PipelineStep):
    """Collect model texture records and typed USD bindings."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "collect_textures"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Collect model textures"

    def should_run(self, context: PipelineContext) -> bool:
        """Return true when a model item has not collected texture bindings yet.

        Args:
            context: Pipeline state to inspect.

        Returns:
            Whether at least one model still needs texture collection.
        """
        state = context.execution_state.get(self.name)
        if state and state.did_run:
            return False
        return any(item.kind is AssetKind.MODEL and not item.texture_bindings for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why model texture collection has no work.

        Args:
            context: Pipeline state without runnable collection work.

        Returns:
            User-readable skip reason.
        """
        if not any(item.kind is AssetKind.MODEL for item in context.items):
            return "no model items"
        return "all model texture bindings are already collected"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Collect existing AperturePBR texture inputs from model shader prims.

        Args:
            context: Remix pipeline state containing standardized model stages.

        Raises:
            FileNotFoundError: If an authored texture path cannot be resolved.
            ValueError: If a model authors an unknown normal-map encoding.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            source_texture_paths = _get_source_texture_paths(context, item)
            stage = context.open_stage(item.value)
            item.textures.clear()
            item.texture_bindings.clear()
            texture_by_key: dict[tuple[pathlib.Path, TextureTypes], TextureAsset] = {}

            for prim in stage.Traverse():
                if not prim.IsA(UsdShade.Material):
                    continue

                shader_prim = omni.usd.get_shader_from_material(prim, get_prim=True)
                if shader_prim is None or not shader_prim.IsValid():
                    continue

                for texture_type, input_name in _iter_texture_inputs(shader_prim):
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
                    if not await run_in_worker_thread(resolved_path.exists):
                        raise FileNotFoundError(
                            f"Texture path on {attr.GetPath()} does not resolve to a readable file: "
                            f"{original_asset_path.path}"
                        )

                    texture_key = (resolved_path, texture_type)
                    texture = texture_by_key.get(texture_key)
                    if texture is None:
                        texture = TextureAsset(
                            path=resolved_path,
                            texture_type=texture_type,
                            original_path=_get_texture_source_identity(
                                item,
                                shader_prim.GetPath(),
                                input_name,
                                resolved_path,
                                source_texture_paths,
                            ),
                        )
                        texture_by_key[texture_key] = texture
                        item.textures.append(texture)

                    item.texture_bindings.append(
                        TextureBinding(
                            shader_path=shader_prim.GetPath(),
                            input_name=input_name,
                            original_asset_path=original_asset_path,
                            texture=texture,
                        )
                    )

            carb.log_info(
                f"[CollectTextures] Collected {len(item.textures)} textures and "
                f"{len(item.texture_bindings)} bindings from {item.value}"
            )


def _get_source_texture_paths(
    context: RemixAssetPipelineContext,
    item: RemixAssetItem,
) -> dict[tuple[Sdf.Path, str], pathlib.Path]:
    """Return stable source paths for dependencies copied into the workspace.

    Args:
        context: Pipeline context used to open the original source stage.
        item: Model item carrying original and standardized stage paths.

    Returns:
        Source texture paths keyed by shader and input, or an empty mapping for non-USD model sources.

    Raises:
        ValueError: If an authored texture input is not mapped to a supported Remix texture type.
    """
    usd_suffixes = {f".{extension.value}" for extension in UsdExtensions}
    if item.source_path.suffix.lower() not in usd_suffixes or item.source_path == item.value:
        return {}

    stage = context.open_stage(item.source_path)
    source_paths: dict[tuple[Sdf.Path, str], pathlib.Path] = {}
    for prim in stage.Traverse():
        if not prim.IsA(UsdShade.Material):
            continue

        shader_prim = omni.usd.get_shader_from_material(prim, get_prim=True)
        if shader_prim is None or not shader_prim.IsValid():
            continue

        for _texture_type, input_name in _iter_texture_inputs(shader_prim):
            attr = shader_prim.GetAttribute(input_name)
            if not attr or not attr.HasAuthoredValue():
                continue

            asset_path = attr.Get()
            if not isinstance(asset_path, Sdf.AssetPath) or not asset_path.path:
                continue

            source_paths[(shader_prim.GetPath(), input_name)] = pathlib.Path(
                asset_path.resolvedPath or get_absolute_path_from_relative(asset_path.path, stage.GetRootLayer())
            )
    return source_paths


def _get_texture_source_identity(
    item: RemixAssetItem,
    shader_path: Sdf.Path,
    input_name: str,
    resolved_path: pathlib.Path,
    source_texture_paths: dict[tuple[Sdf.Path, str], pathlib.Path],
) -> pathlib.Path:
    """Return a stable source identity for one collected model texture.

    Args:
        item: Model item carrying the original model path.
        shader_path: Stable shader prim path owning the texture input.
        input_name: Authored shader input name.
        resolved_path: Materialized texture file used for processing.
        source_texture_paths: Original dependency paths recovered from a USD source.

    Returns:
        Original USD dependency path, or a deterministic model/shader/input identity for imported models.
    """
    source_path = source_texture_paths.get((shader_path, input_name))
    if source_path is not None:
        return source_path

    usd_suffixes = {f".{extension.value}" for extension in UsdExtensions}
    if item.source_path.suffix.lower() in usd_suffixes:
        return resolved_path

    shader_parts = tuple(part for part in str(shader_path).split("/") if part)
    input_token = input_name.rsplit(":", 1)[-1]
    return (
        item.source_path.parent
        / item.source_path.stem
        / pathlib.Path(*shader_parts)
        / (f"{input_token}{resolved_path.suffix.lower()}")
    )


def _iter_texture_inputs(shader_prim: Usd.Prim) -> Iterator[tuple[TextureTypes, str]]:
    """Yield each authored shader texture input once.

    Args:
        shader_prim: Shader prim whose known texture inputs should be inspected.

    Yields:
        Texture semantic and authored shader input name.

    Raises:
        ValueError: If a normal input authors an unknown encoding.
    """
    yielded_inputs: set[str] = set()
    for texture_type, input_name in TEXTURE_TYPE_INPUT_MAP.items():
        if input_name in yielded_inputs:
            continue
        yielded_inputs.add(input_name)

        if input_name == TEXTURE_TYPE_INPUT_MAP[TextureTypes.NORMAL_OTH]:
            if shader_prim.HasAttribute(input_name):
                yield _get_normal_texture_type(shader_prim), input_name
            continue

        if shader_prim.HasAttribute(input_name):
            yield texture_type, input_name


def _get_normal_texture_type(shader_prim: Usd.Prim) -> TextureTypes:
    """Resolve the authored normal-map semantic for one shader.

    Args:
        shader_prim: Shader prim carrying the optional encoding attribute.

    Returns:
        Texture semantic matching the authored normal-map encoding.

    Raises:
        ValueError: If the authored encoding is unknown.
    """
    encoding_attr = shader_prim.GetAttribute(MATERIAL_INPUTS_NORMALMAP_ENCODING)
    if not encoding_attr or not encoding_attr.HasAuthoredValue():
        return TextureTypes.NORMAL_DX

    encoding = encoding_attr.Get()
    try:
        normal_encoding = NormalMapEncodings(encoding)
    except ValueError as error:
        raise ValueError(f"Unknown normal map encoding {encoding} on {shader_prim.GetPath()}") from error

    if normal_encoding is NormalMapEncodings.OCTAHEDRAL:
        return TextureTypes.NORMAL_OTH
    if normal_encoding is NormalMapEncodings.TANGENT_SPACE_OGL:
        return TextureTypes.NORMAL_OGL
    return TextureTypes.NORMAL_DX
