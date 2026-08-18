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

__all__ = ["iter_texture_paths_for_prim"]

from collections.abc import Iterator

from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS
from omni.usd import get_context
from pxr import Sdf, Usd, UsdShade


def iter_texture_paths_for_prim(
    prim_path: str,
    context_name: str,
    texture_type: str = "",
) -> Iterator[str]:
    """Iterate unique texture file paths for a given prim path.

    Args:
        prim_path: USD path of the prim whose shader graph should be inspected.
        context_name: USD context containing the prim.
        texture_type: Optional shader input name used to filter discovered textures.

    Yields:
        Unique resolved texture file paths reachable from the prim.
    """
    stage = get_context(context_name).get_stage()
    if not stage:
        return

    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return

    seen_texture_paths: set[str] = set()
    for texture_path in _iter_texture_paths(prim, texture_type=texture_type):
        if texture_path in seen_texture_paths:
            continue
        seen_texture_paths.add(texture_path)
        yield texture_path


def _get_bound_material_prim(prim: Usd.Prim) -> Usd.Prim | None:
    """Return the computed bound material prim, including direct material bindings.

    Args:
        prim: USD prim whose inherited or direct material binding should be computed.

    Returns:
        Valid bound material prim, or ``None`` when no material is bound.
    """
    material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    if material:
        material_prim = material.GetPrim()
        if material_prim.IsValid():
            return material_prim
    return None


def _iter_texture_paths(
    prim: Usd.Prim,
    seen_prims: set[str] | None = None,
    texture_type: str = "",
) -> Iterator[str]:
    """Iterate texture file paths through shaders and all material surface outputs.

    Args:
        prim: USD shader, material, or material-bound prim to traverse.
        seen_prims: Traversal set shared across recursive graph visits.
        texture_type: Optional shader input name used to filter discovered textures.

    Yields:
        Resolved texture file paths authored on reachable shader inputs.
    """
    if not prim.IsValid():
        return

    if seen_prims is None:
        seen_prims = set()

    pending = [prim]
    texture_type_key = texture_type.casefold()
    while pending:
        current = pending.pop()
        prim_path = str(current.GetPath())
        if prim_path in seen_prims:
            continue
        seen_prims.add(prim_path)

        shader = UsdShade.Shader(current)
        if shader:
            for shader_input in shader.GetInputs():
                if texture_type_key and texture_type_key != str(shader_input.GetFullName()).casefold():
                    continue
                value = shader_input.Get()
                if isinstance(value, Sdf.AssetPath):
                    if value.resolvedPath:
                        value = value.resolvedPath
                    else:
                        value = value.path
                        for prop_spec in shader_input.GetAttr().GetPropertyStack(Usd.TimeCode.Default()):
                            authored_value = prop_spec.default
                            if isinstance(authored_value, Sdf.AssetPath) and authored_value.path:
                                value = prop_spec.layer.ComputeAbsolutePath(authored_value.path)
                                break
                elif isinstance(value, str) and _is_texture_path(value):
                    for prop_spec in shader_input.GetAttr().GetPropertyStack(Usd.TimeCode.Default()):
                        authored_value = prop_spec.default
                        if isinstance(authored_value, str) and authored_value:
                            value = prop_spec.layer.ComputeAbsolutePath(authored_value)
                            break
                if isinstance(value, str) and _is_texture_path(value):
                    yield value
            continue

        material = UsdShade.Material(current)
        if not material:
            material_prim = _get_bound_material_prim(current)
            if material_prim is not None:
                material = UsdShade.Material(material_prim)

        if not material:
            continue

        surface_outputs = list(material.GetSurfaceOutputs())
        if not surface_outputs:
            universal_output = material.GetSurfaceOutput()
            if universal_output:
                surface_outputs = [universal_output]

        source_prims = []
        for surface_output in surface_outputs:
            for source_info in surface_output.GetConnectedSources()[0]:
                source_prims.append(source_info.source.GetPrim())
        pending.extend(reversed(source_prims))


def _is_texture_path(value: str) -> bool:
    """Check if a string value looks like a texture file path.

    Args:
        value: Candidate asset path to inspect by extension.

    Returns:
        Whether the value ends with a supported texture extension.
    """
    return value.casefold().endswith(tuple(SUPPORTED_TEXTURE_EXTENSIONS))
