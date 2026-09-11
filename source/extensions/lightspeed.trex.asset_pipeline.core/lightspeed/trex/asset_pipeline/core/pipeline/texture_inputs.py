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
    "get_source_texture_paths",
    "get_texture_source_identity",
    "iter_texture_inputs",
]

import pathlib
from collections.abc import Iterator

from lightspeed.common.constants import MATERIAL_INPUTS_NORMALMAP_ENCODING, NormalMapEncodings
from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes, UsdExtensions
from pxr import Usd

from .item import RemixAssetItem


def get_source_texture_paths(item: RemixAssetItem) -> dict[pathlib.Path, pathlib.Path]:
    """Return collector source identities keyed by resolved workspace paths.

    Args:
        item: Model item with the collector source-to-copy mapping.

    Returns:
        Original dependency paths keyed by their resolved collected paths.
    """
    return {copy.resolve(): source for source, copy in item.collected_dependencies.items()}


def get_texture_source_identity(
    item: RemixAssetItem,
    resolved_path: pathlib.Path,
    source_texture_paths: dict[pathlib.Path, pathlib.Path],
) -> pathlib.Path:
    """Return a stable source identity for one collected model texture.

    A USD source names its own texture files, so their paths are the identity. A non-USD source
    has no texture files of its own: the asset converter writes them beside the imported model
    (``textures/<name>`` for the FBX importer). The legacy ingestion converted each of those in
    place, so the published model kept that same layout. The identity is therefore the converter's
    path relative to the imported model, anchored at the source model, so the published DDS lands
    at ``textures/<name>`` beside the published model exactly as it did for legacy.

    Args:
        item: Model item carrying the original model path and the imported model work path.
        resolved_path: Materialized texture file used for processing.
        source_texture_paths: Collector source identities keyed by resolved collected paths.

    Returns:
        Original USD dependency path, or the converter layout anchored at the source model for an
        imported model. A texture the converter left outside the imported model keeps its own path.
    """
    source_path = source_texture_paths.get(resolved_path.resolve())
    if source_path is not None:
        return source_path

    usd_suffixes = {f".{extension.value}" for extension in UsdExtensions}
    if item.source_path.suffix.lower() in usd_suffixes:
        return resolved_path

    try:
        relative_path = resolved_path.resolve().relative_to(item.value.resolve().parent)
    except ValueError:
        return resolved_path
    return item.source_path.parent / relative_path


def iter_texture_inputs(shader_prim: Usd.Prim) -> Iterator[tuple[TextureTypes, str]]:
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
