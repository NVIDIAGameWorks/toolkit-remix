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

__all__ = ["ConvertMaterialsStep"]

import contextlib
import re
import threading
from collections.abc import Iterator

import carb
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.material_converter import MaterialConverterCore, get_converter_builder
from omni.flux.utils.material_converter.utils import SupportedShaderInputs, SupportedShaderOutputs
from pxr import Usd, UsdShade

from ..constants import ORPHAN_PARAMETER_CLEANUP_SETTING_PATH
from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import AssetKind, RemixAssetItem
from ..utils import get_material_shader_prim


_ORPHAN_PARAMETER_CLEANUP_LOCK = threading.Lock()
_ORPHAN_PARAMETER_CLEANUP_DISABLE_COUNT = 0
_ORPHAN_PARAMETER_CLEANUP_PREVIOUS_VALUE: object | None = None


class ConvertMaterialsStep(PipelineStep):
    """Convert model materials with legacy name rules and glTF shader controls."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "convert_materials"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Prepare model materials"

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return whether the context contains any model items."""
        return any(item.kind is AssetKind.MODEL for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no material conversion work."""
        return "no model items"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Convert every material in every model item to AperturePBR.

        Raises:
            RuntimeError: If no converter supports an authored material or conversion fails.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            stage = await context.open_stage(item.value)

            material_paths = [prim.GetPath() for prim in stage.Traverse() if prim.IsA(UsdShade.Material)]

            with _orphan_parameter_cleanup_disabled():
                changed = False
                for prim_path in material_paths:
                    prim = stage.GetPrimAtPath(prim_path)
                    if prim and prim.IsValid():
                        changed = await _convert_material_if_needed(context.stage_context_name, prim) or changed

            if changed:
                await context.save_stage()
                carb.log_info(f"[ConvertMaterials] Saved converted stage {item.value}")


@contextlib.contextmanager
def _orphan_parameter_cleanup_disabled() -> Iterator[None]:
    """Keep MDL parameter cleanup disabled while material definitions change.

    Yields:
        Control while nested material conversions hold the process-wide setting.
    """
    global _ORPHAN_PARAMETER_CLEANUP_DISABLE_COUNT
    global _ORPHAN_PARAMETER_CLEANUP_PREVIOUS_VALUE

    settings = carb.settings.get_settings()
    with _ORPHAN_PARAMETER_CLEANUP_LOCK:
        if _ORPHAN_PARAMETER_CLEANUP_DISABLE_COUNT == 0:
            _ORPHAN_PARAMETER_CLEANUP_PREVIOUS_VALUE = settings.get(ORPHAN_PARAMETER_CLEANUP_SETTING_PATH)
            settings.set(ORPHAN_PARAMETER_CLEANUP_SETTING_PATH, True)
        _ORPHAN_PARAMETER_CLEANUP_DISABLE_COUNT += 1
    try:
        yield
    finally:
        with _ORPHAN_PARAMETER_CLEANUP_LOCK:
            _ORPHAN_PARAMETER_CLEANUP_DISABLE_COUNT -= 1
            if _ORPHAN_PARAMETER_CLEANUP_DISABLE_COUNT == 0:
                settings.set(
                    ORPHAN_PARAMETER_CLEANUP_SETTING_PATH,
                    _ORPHAN_PARAMETER_CLEANUP_PREVIOUS_VALUE
                    if _ORPHAN_PARAMETER_CLEANUP_PREVIOUS_VALUE is not None
                    else False,
                )
                _ORPHAN_PARAMETER_CLEANUP_PREVIOUS_VALUE = None


async def _convert_material_if_needed(
    context_name: str,
    material_prim: Usd.Prim,
) -> bool:
    """Convert a material with the legacy model shader selection rules.

    Args:
        context_name: USD context used by the material converter.
        material_prim: Material prim whose shader should be inspected and converted.

    Returns:
        True when conversion changed the material.

    Raises:
        RuntimeError: If no converter supports the shader or conversion fails.
    """
    shader_prim = get_material_shader_prim(material_prim)
    if shader_prim is None:
        input_subidentifier = None
        builder = get_converter_builder(None)
        target_output = SupportedShaderOutputs.APERTURE_PBR_OPACITY
    else:
        input_subidentifier = _get_authored_shader_subidentifier(shader_prim)
        if input_subidentifier in {output.value for output in SupportedShaderOutputs}:
            return False
        builder = get_converter_builder(input_subidentifier)
        if builder is None:
            raise RuntimeError(
                f"Unsupported material shader '{input_subidentifier}' on {material_prim.GetPath()}; "
                "cannot select an AperturePBR output"
            )
        target_output = (
            builder.select_output(shader_prim)
            if input_subidentifier == SupportedShaderInputs.GLTF.value
            else SupportedShaderOutputs.APERTURE_PBR_OPACITY
        )

    if re.search("translucent|glass|trans", material_prim.GetName(), re.IGNORECASE):
        target_output = SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT
        if input_subidentifier not in {SupportedShaderInputs.OMNI_GLASS.value, SupportedShaderInputs.GLTF.value}:
            builder = get_converter_builder(None)

    converter = builder.build(material_prim, target_output.value)
    if converter is None:
        raise RuntimeError(
            f"Unsupported material shader '{input_subidentifier}' on {material_prim.GetPath()}; "
            f"cannot convert to {target_output.value}"
        )

    success, message, was_skipped = await MaterialConverterCore.convert(context_name, converter)
    if not success:
        raise RuntimeError(message or f"Failed to convert material {material_prim.GetPath()} to {target_output.value}")
    return not was_skipped


def _get_authored_shader_subidentifier(shader_prim: Usd.Prim) -> str | None:
    """Return the normalized shader identifier authored by one shader prim.

    Args:
        shader_prim: Shader prim carrying MDL or shader-id metadata.

    Returns:
        Normalized authored identifier, or ``None`` when unavailable.
    """
    shader = UsdShade.Shader(shader_prim)
    subidentifier_attr = shader_prim.GetAttribute("info:mdl:sourceAsset:subIdentifier")
    if subidentifier_attr and subidentifier_attr.HasAuthoredValue():
        return _normalize_shader_identifier(subidentifier_attr.Get())

    shader_id = shader.GetShaderId() if shader else None
    if shader_id:
        return _normalize_shader_identifier(shader_id)
    return None


def _normalize_shader_identifier(value: object) -> str | None:
    """Remove MDL decorations from one authored shader identifier.

    Args:
        value: Authored shader identifier value.

    Returns:
        Normalized identifier, or ``None`` for an absent value.
    """
    if value is None:
        return None
    return str(value).split("(", maxsplit=1)[0].removesuffix(".mdl")
