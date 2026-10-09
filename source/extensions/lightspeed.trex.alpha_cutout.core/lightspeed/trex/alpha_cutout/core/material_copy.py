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
    "ALPHA_TEST_ALWAYS",
    "OPAQUE_ALPHA_STATE_INPUTS",
    "author_opaque_alpha_state",
    "copy_material_flattened",
]

import omni.client
from pxr import Sdf, Usd, UsdShade

# The runtime enum value of AlphaTestType::kAlways. The MDL enum lists "Always" first, but the runtime reads
# the raw integer, so 7 is the value that disables alpha testing.
ALPHA_TEST_ALWAYS = 7
OPAQUE_ALPHA_STATE_INPUTS: tuple[tuple[str, Sdf.ValueTypeName, object], ...] = (
    ("use_legacy_alpha_state", Sdf.ValueTypeNames.Bool, False),
    ("blend_enabled", Sdf.ValueTypeNames.Bool, False),
    ("alpha_test_type", Sdf.ValueTypeNames.Int, ALPHA_TEST_ALWAYS),
)

_MDL_RENDER_CONTEXT = "mdl"
_SHADER_NAME = "Shader"
_KIND_KEY = "kind"


def author_opaque_alpha_state(shader: UsdShade.Shader) -> None:
    """Author the inputs that make the runtime treat a material as fully opaque.

    Args:
        shader: Surface shader to edit.
    """
    for name, type_name, value in OPAQUE_ALPHA_STATE_INPUTS:
        shader.CreateInput(name, type_name).Set(value)


def _get_surface_shader(material: UsdShade.Material) -> UsdShade.Shader | None:
    """Return the surface shader of a material, trying the universal then the MDL render context.

    Args:
        material: Material to inspect.

    Returns:
        The surface shader, or ``None``.
    """
    shader, _, _ = material.ComputeSurfaceSource()
    if not shader:
        shader, _, _ = material.ComputeSurfaceSource(_MDL_RENDER_CONTEXT)
    return shader or None


def _relative_asset_path(asset: Sdf.AssetPath, source_attribute: Usd.Attribute, output_file: str) -> Sdf.AssetPath:
    """Rewrite an asset path so it resolves from the output file.

    MDL module paths resolve through search paths rather than the file system, so a path without a resolved
    location is copied unchanged.

    Args:
        asset: Composed asset value.
        source_attribute: Attribute the value was read from.
        output_file: Absolute path of the file the copy is written to.

    Returns:
        Asset path relative to the output file, or the original value.
    """
    absolute = asset.resolvedPath
    if not absolute:
        stack = source_attribute.GetPropertyStack(Usd.TimeCode.Default())
        if stack and asset.path and not asset.path.lower().endswith(".mdl"):
            absolute = stack[0].layer.ComputeAbsolutePath(asset.path)
    if not absolute:
        return Sdf.AssetPath(asset.path)
    relative = omni.client.make_relative_url(output_file, omni.client.normalize_url(absolute))
    return Sdf.AssetPath(omni.client.normalize_url(relative).replace("\\", "/"))


def _copy_attribute(source: Usd.Attribute, destination_prim: Usd.Prim, output_file: str) -> None:
    """Copy one composed attribute value and its color space onto a destination prim.

    Args:
        source: Attribute to copy.
        destination_prim: Prim that receives the attribute.
        output_file: Absolute path of the file the copy is written to.
    """
    destination = destination_prim.CreateAttribute(
        source.GetName(), source.GetTypeName(), custom=source.IsCustom(), variability=source.GetVariability()
    )
    value = source.Get(Usd.TimeCode.Default())
    if isinstance(value, Sdf.AssetPath):
        value = _relative_asset_path(value, source, output_file)
    if value is not None:
        destination.Set(value)
    if source.HasColorSpace():
        destination.SetColorSpace(source.GetColorSpace())


def copy_material_flattened(
    source_material: UsdShade.Material,
    destination_stage: Usd.Stage,
    destination_path: str,
    output_file: str,
    disable_alpha_test: bool,
) -> UsdShade.Material:
    """Define a standalone copy of a material from its composed values.

    Every authored attribute of the surface shader is copied with its composed value, so overrides the user
    authored on the captured material are baked into the copy. Asset paths are rewritten relative to the
    output file. The copy optionally authors the opaque alpha state the runtime needs to skip alpha testing.

    Args:
        source_material: Material to copy, usually the captured ``mat_HASH``.
        destination_stage: Stage of the generated file.
        destination_path: Path of the new material prim, which must not use the captured naming scheme.
        output_file: Absolute path of the generated file.
        disable_alpha_test: Whether to author ``use_legacy_alpha_state``, ``blend_enabled`` and
            ``alpha_test_type`` so the mesh renders fully opaque.

    Returns:
        The new material.
    """
    destination_material = UsdShade.Material.Define(destination_stage, destination_path)
    destination_shader = UsdShade.Shader.Define(destination_stage, f"{destination_path}/{_SHADER_NAME}")
    source_shader = _get_surface_shader(source_material)
    if source_shader is not None:
        source_prim = source_shader.GetPrim()
        kind = source_prim.GetMetadata(_KIND_KEY)
        if kind:
            destination_shader.GetPrim().SetMetadata(_KIND_KEY, kind)
        for attribute in source_prim.GetAuthoredAttributes():
            _copy_attribute(attribute, destination_shader.GetPrim(), output_file)
        for output in source_material.GetOutputs():
            source, source_name, _ = output.GetConnectedSource()
            if not source or source.GetPrim() != source_prim:
                continue
            destination_output = destination_material.CreateOutput(output.GetBaseName(), output.GetTypeName())
            destination_output.ConnectToSource(destination_shader.ConnectableAPI(), source_name)
    if disable_alpha_test:
        author_opaque_alpha_state(destination_shader)
    return destination_material
