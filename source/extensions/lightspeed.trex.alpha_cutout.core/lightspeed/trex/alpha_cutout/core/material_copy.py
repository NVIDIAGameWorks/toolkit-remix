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
    "get_surface_shader",
]

import os
import shutil

import omni.client
from lightspeed.common import constants
from lightspeed.trex.utils.common.asset_utils import is_texture_from_capture
from pxr import Sdf, Usd, UsdShade

from .metadata import write_ingestion_metadata

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
_MDL_SUFFIX = ".mdl"
_SOURCE_ASSET_ATTR = "info:mdl:sourceAsset"


def author_opaque_alpha_state(shader: UsdShade.Shader) -> None:
    """Author the inputs that make the runtime treat a material as fully opaque.

    Args:
        shader: Surface shader to edit.
    """
    for name, type_name, value in OPAQUE_ALPHA_STATE_INPUTS:
        shader.CreateInput(name, type_name).Set(value)


def get_surface_shader(material: UsdShade.Material) -> UsdShade.Shader | None:
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


def _is_inside(path: str, folder: str | None) -> bool:
    if not folder:
        return False
    normalized = omni.client.normalize_url(path).lower().rstrip("/") + "/"
    root = omni.client.normalize_url(folder).lower().rstrip("/") + "/"
    return normalized.startswith(root)


class _AssetPathRewriter:
    """Rewrite the asset paths of a material copy so they resolve from the generated file.

    MDL modules resolve through search paths, so they are written as bare module names. Textures that live
    inside the project are referenced relative to the generated file. Textures outside the project or under its
    ``deps`` folder, such as capture textures, are copied into the texture folder next to the generated file when
    one is given.
    """

    def __init__(self, output_file: str, texture_dir: str | None, project_dir: str | None):
        self._output_file = omni.client.normalize_url(output_file)
        self._texture_dir = omni.client.normalize_url(texture_dir) if texture_dir else None
        self._project_dir = project_dir
        self._dependencies_dir = (
            f"{project_dir.rstrip('/')}/{constants.REMIX_DEPENDENCIES_FOLDER}" if project_dir else None
        )

    def rewrite(self, asset: Sdf.AssetPath, source_attribute: Usd.Attribute) -> Sdf.AssetPath:
        """Return the asset path to author in the copy.

        Args:
            asset: Composed asset value.
            source_attribute: Attribute the value was read from.

        Returns:
            The rewritten asset path.
        """
        if asset.path.lower().endswith(_MDL_SUFFIX):
            return Sdf.AssetPath(os.path.basename(asset.path))
        absolute = asset.resolvedPath
        if not absolute:
            stack = source_attribute.GetPropertyStack(Usd.TimeCode.Default())
            if stack and asset.path:
                absolute = stack[0].layer.ComputeAbsolutePath(asset.path)
        if not absolute:
            return Sdf.AssetPath(asset.path)
        absolute = omni.client.normalize_url(absolute)
        if self._texture_dir and os.path.isfile(absolute) and self._needs_copy(absolute):
            absolute = self._copy_texture(absolute)
        relative = omni.client.make_relative_url(self._output_file, absolute)
        return Sdf.AssetPath(omni.client.normalize_url(relative).replace("\\", "/"))

    def _needs_copy(self, texture: str) -> bool:
        """Return whether a texture is not part of the mod and must be copied next to the generated file.

        Capture textures live under the project's ``deps`` folder, which is not packaged with the mod.

        Args:
            texture: Absolute texture path.

        Returns:
            ``True`` for textures outside the project, inside its dependencies folder or from a capture.
        """
        return (
            not _is_inside(texture, self._project_dir)
            or _is_inside(texture, self._dependencies_dir)
            or is_texture_from_capture(texture)
        )

    def _copy_texture(self, source: str) -> str:
        """Copy a texture into the texture folder, writing its ingestion sidecar.

        Args:
            source: Absolute texture path.

        Returns:
            Absolute path of the copy.
        """
        os.makedirs(self._texture_dir, exist_ok=True)
        destination = f"{self._texture_dir.rstrip('/')}/{os.path.basename(source)}"
        if not os.path.isfile(destination) or os.path.getsize(destination) != os.path.getsize(source):
            shutil.copyfile(source, destination)
            write_ingestion_metadata(destination)
        return destination


def _copy_attribute(source: Usd.Attribute, destination_prim: Usd.Prim, rewriter: _AssetPathRewriter) -> None:
    """Copy one composed attribute value and its color space onto a destination prim.

    Args:
        source: Attribute to copy.
        destination_prim: Prim that receives the attribute.
        rewriter: Rewrites asset path values.
    """
    destination = destination_prim.CreateAttribute(
        source.GetName(), source.GetTypeName(), custom=source.IsCustom(), variability=source.GetVariability()
    )
    value = source.Get(Usd.TimeCode.Default())
    if isinstance(value, Sdf.AssetPath):
        value = rewriter.rewrite(value, source)
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
    texture_dir: str | None = None,
    project_dir: str | None = None,
) -> UsdShade.Material:
    """Define a standalone copy of a material from its composed values.

    Every authored attribute of the surface shader is copied with its composed value, so overrides the user
    authored on the captured material are baked into the copy. MDL modules are written as bare module names,
    textures inside the project are referenced relative to the output file, and textures outside it are copied
    into ``texture_dir`` when one is given. The copy optionally authors the opaque alpha state the runtime needs
    to skip alpha testing.

    Args:
        source_material: Material to copy, usually the captured ``mat_HASH``.
        destination_stage: Stage of the generated file.
        destination_path: Path of the new material prim, which must not use the captured naming scheme.
        output_file: Absolute path of the generated file.
        disable_alpha_test: Whether to author ``use_legacy_alpha_state``, ``blend_enabled`` and
            ``alpha_test_type`` so the mesh renders fully opaque.
        texture_dir: Folder that receives copies of textures from outside the project, or ``None`` to only
            reference them.
        project_dir: Project folder; textures inside it are never copied.

    Returns:
        The new material.
    """
    destination_material = UsdShade.Material.Define(destination_stage, destination_path)
    destination_shader = UsdShade.Shader.Define(destination_stage, f"{destination_path}/{_SHADER_NAME}")
    source_shader = get_surface_shader(source_material)
    if source_shader is not None:
        source_prim = source_shader.GetPrim()
        kind = source_prim.GetMetadata(_KIND_KEY)
        if kind:
            destination_shader.GetPrim().SetMetadata(_KIND_KEY, kind)
        rewriter = _AssetPathRewriter(output_file, texture_dir, project_dir)
        for attribute in source_prim.GetAuthoredAttributes():
            _copy_attribute(attribute, destination_shader.GetPrim(), rewriter)
        module = (
            source_prim.GetAttribute(_SOURCE_ASSET_ATTR).Get() if source_prim.HasAttribute(_SOURCE_ASSET_ATTR) else None
        )
        if module:
            # Author the implementation source alongside the module so the runtime loads the MDL by name.
            destination_shader.SetSourceAsset(Sdf.AssetPath(os.path.basename(module.path)), _MDL_RENDER_CONTEXT)
        for output in source_material.GetOutputs():
            source, source_name, _ = output.GetConnectedSource()
            if not source or source.GetPrim() != source_prim:
                continue
            destination_output = destination_material.CreateOutput(output.GetBaseName(), output.GetTypeName())
            destination_output.ConnectToSource(destination_shader.ConnectableAPI(), source_name)
    if disable_alpha_test:
        author_opaque_alpha_state(destination_shader)
    return destination_material
