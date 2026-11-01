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
    "APERTURE_SHADERS",
    "OPAQUE_ALPHA_STATE_INPUTS",
    "author_opaque_alpha_state",
    "define_material",
    "snapshot_material",
]

import os
from typing import Any

import omni.client
from pxr import Gf, Sdf, Usd, UsdShade

from .usd_reader import get_surface_shader

# The runtime reads the alpha test type as a raw integer; 7 is its "always pass" value.
ALPHA_TEST_ALWAYS = 7
OPAQUE_ALPHA_STATE_INPUTS: tuple[tuple[str, Sdf.ValueTypeName, object], ...] = (
    ("use_legacy_alpha_state", Sdf.ValueTypeNames.Bool, False),
    ("blend_enabled", Sdf.ValueTypeNames.Bool, False),
    ("alpha_test_type", Sdf.ValueTypeNames.Int, ALPHA_TEST_ALWAYS),
)
APERTURE_SHADERS = frozenset({"AperturePBR_Opacity", "AperturePBR_Translucent"})

_MDL_RENDER_CONTEXT = "mdl"
_MDL_SUFFIX = ".mdl"
_SHADER_NAME = "Shader"
_SOURCE_ASSET_ATTR = "info:mdl:sourceAsset"
_SUB_IDENTIFIER_ATTR = "info:mdl:sourceAsset:subIdentifier"
_ASSET_KEY = "asset"
_VECTOR_TYPES = (Gf.Vec2f, Gf.Vec3f, Gf.Vec4f, Gf.Vec2d, Gf.Vec3d, Gf.Vec4d, Gf.Vec2i, Gf.Vec3i, Gf.Vec4i)


def author_opaque_alpha_state(shader: UsdShade.Shader) -> None:
    """Author the inputs that make the runtime treat a material as fully opaque.

    Args:
        shader: Surface shader to edit.
    """
    for name, type_name, value in OPAQUE_ALPHA_STATE_INPUTS:
        shader.CreateInput(name, type_name).Set(value)


def _absolute_asset_path(asset: Sdf.AssetPath, attribute: Usd.Attribute) -> str:
    """Return the absolute file path of an asset value, or the bare module name of an MDL.

    Args:
        asset: Composed asset value.
        attribute: Attribute the value was read from.

    Returns:
        Path string to store in the snapshot.
    """
    if asset.path.lower().endswith(_MDL_SUFFIX):
        return os.path.basename(asset.path)
    if asset.resolvedPath:
        return omni.client.normalize_url(asset.resolvedPath)
    stack = attribute.GetPropertyStack(Usd.TimeCode.Default())
    if stack and asset.path:
        return omni.client.normalize_url(stack[0].layer.ComputeAbsolutePath(asset.path))
    return asset.path


def _encode_value(value: Any, attribute: Usd.Attribute) -> Any:
    """Convert an attribute value into JSON-compatible data.

    Args:
        value: Composed attribute value.
        attribute: Attribute the value was read from.

    Returns:
        Scalars as they are, vectors as lists, assets as ``{"asset": path}``; ``None`` for unsupported types.
    """
    if isinstance(value, Sdf.AssetPath):
        return {_ASSET_KEY: _absolute_asset_path(value, attribute)}
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, _VECTOR_TYPES):
        return [float(component) for component in value]
    return None


def _decode_value(encoded: Any, type_name: Sdf.ValueTypeName) -> Any:
    """Rebuild an attribute value from its snapshot form.

    Args:
        encoded: Value produced by ``_encode_value``.
        type_name: Attribute type the value is authored as.

    Returns:
        A value the attribute accepts.
    """
    if isinstance(encoded, dict):
        return Sdf.AssetPath(encoded[_ASSET_KEY])
    value_class = type(type_name.defaultValue)
    if isinstance(encoded, list):
        return value_class(*encoded)
    return value_class(encoded)


def snapshot_material(material: UsdShade.Material) -> dict | None:
    """Capture the composed surface shader of a material as JSON-compatible data.

    Asset paths are stored absolute so the snapshot resolves from anywhere, except MDL modules, which stay
    bare module names that resolve through the MDL search paths.

    Args:
        material: Material to capture, with the user's overrides composed in.

    Returns:
        The snapshot, or ``None`` when the material has no surface shader.
    """
    shader = get_surface_shader(material)
    if shader is None:
        return None
    shader_prim = shader.GetPrim()
    attributes = []
    for attribute in shader_prim.GetAuthoredAttributes():
        value = attribute.Get(Usd.TimeCode.Default())
        encoded = _encode_value(value, attribute) if value is not None else None
        if encoded is None:
            continue
        attributes.append(
            {
                "name": attribute.GetName(),
                "type": str(attribute.GetTypeName()),
                "value": encoded,
                "color_space": attribute.GetColorSpace() if attribute.HasColorSpace() else None,
                "custom": attribute.IsCustom(),
                "uniform": attribute.GetVariability() == Sdf.VariabilityUniform,
            }
        )
    outputs = []
    for output in material.GetOutputs():
        source, source_name, _ = output.GetConnectedSource()
        if source and source.GetPrim() == shader_prim:
            outputs.append({"name": output.GetBaseName(), "type": str(output.GetTypeName()), "source": source_name})
    return {"attributes": attributes, "outputs": outputs}


def define_material(
    stage: Usd.Stage, material_path: str, snapshot: dict, disable_alpha_test: bool
) -> UsdShade.Material:
    """Define a material from a snapshot.

    The MDL module is authored through the shader schema so the asset pipeline recognizes the Aperture shader and
    keeps its inputs.

    Args:
        stage: Stage of the file being written.
        material_path: Path of the new material prim.
        snapshot: Data produced by ``snapshot_material``.
        disable_alpha_test: Whether to author the opaque alpha state on the shader.

    Returns:
        The new material.
    """
    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, f"{material_path}/{_SHADER_NAME}")
    shader_prim = shader.GetPrim()
    module = None
    sub_identifier = None
    for entry in snapshot["attributes"]:
        type_name = Sdf.ValueTypeNames.Find(entry["type"])
        if entry["name"] == _SOURCE_ASSET_ATTR:
            module = entry["value"][_ASSET_KEY]
            continue
        if entry["name"] == _SUB_IDENTIFIER_ATTR:
            sub_identifier = entry["value"]
            continue
        attribute = shader_prim.CreateAttribute(
            entry["name"],
            type_name,
            custom=entry["custom"],
            variability=Sdf.VariabilityUniform if entry["uniform"] else Sdf.VariabilityVarying,
        )
        attribute.Set(_decode_value(entry["value"], type_name))
        if entry["color_space"]:
            attribute.SetColorSpace(entry["color_space"])
    if module:
        shader.SetSourceAsset(Sdf.AssetPath(module), _MDL_RENDER_CONTEXT)
    if sub_identifier:
        shader.SetSourceAssetSubIdentifier(sub_identifier, _MDL_RENDER_CONTEXT)
    for entry in snapshot["outputs"]:
        output = material.CreateOutput(entry["name"], Sdf.ValueTypeNames.Find(entry["type"]))
        output.ConnectToSource(shader.ConnectableAPI(), entry["source"])
    if disable_alpha_test:
        author_opaque_alpha_state(shader)
    return material
