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
import threading
from collections.abc import Iterator
from typing import TYPE_CHECKING

import carb
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.material_converter import MaterialConverterCore
from omni.flux.utils.material_converter import NoneToAperturePBRConverterBuilder
from omni.flux.utils.material_converter import OmniGlassToAperturePBRConverterBuilder
from omni.flux.utils.material_converter import OmniPBRToAperturePBRConverterBuilder
from omni.flux.utils.material_converter import USDPreviewSurfaceToAperturePBRConverterBuilder
from omni.flux.utils.material_converter.utils import SupportedShaderInputs, SupportedShaderOutputs
from omni.usd import get_shader_from_material
from pxr import Usd, UsdShade

from ..constants import ORPHAN_PARAMETER_CLEANUP_SETTING_PATH
from ..pipeline_context import RemixAssetPipelineContext
from ..pipeline_item import AssetKind, MaterialType, RemixAssetItem

if TYPE_CHECKING:
    from omni.flux.utils.material_converter.base.converter_base import ConverterBase


_ORPHAN_PARAMETER_CLEANUP_LOCK = threading.Lock()
_ORPHAN_PARAMETER_CLEANUP_DISABLE_COUNT = 0
_ORPHAN_PARAMETER_CLEANUP_PREVIOUS_VALUE: object | None = None


class ConvertMaterialsStep(PipelineStep):
    """Convert model materials to the AperturePBR shader for the selected material type."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier.

        Returns:
            Stable pipeline step name.
        """
        return "convert_materials"

    @property
    def description(self) -> str:
        """Return a human-readable description.

        Returns:
            User-facing phase description.
        """
        return "Prepare model materials"

    def validate(self, context: PipelineContext) -> list[str]:
        """Require callers to provide the material type for model items.

        Args:
            context: Pipeline state to validate.

        Returns:
            Ordered validation errors.
        """
        errors = super().validate(context)

        for index, item in enumerate(context.items):
            if isinstance(item, RemixAssetItem) and item.kind is AssetKind.MODEL and item.material_type is None:
                errors.append(f"{self.name}: item {index} must provide material_type")
        return errors

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return whether the context contains any model items.

        Args:
            context: Pipeline state containing the candidate asset items.

        Returns:
            True when at least one model requires material inspection.
        """
        return any(item.kind is AssetKind.MODEL for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no material conversion work.

        Args:
            context: Pipeline state without model items.

        Returns:
            User-readable skip reason.
        """
        return "no model items"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Convert every material in every model item to AperturePBR.

        Args:
            context: Remix pipeline state containing standardized model stages.

        Raises:
            RuntimeError: If no converter supports an authored material or conversion fails.
            ValueError: If a model requests an unsupported material type.
        """
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            stage = context.open_stage(item.value)
            target_output = _get_target_shader_output(item.material_type)
            material_paths = [prim.GetPath() for prim in stage.Traverse() if prim.IsA(UsdShade.Material)]

            with _orphan_parameter_cleanup_disabled():
                changed = False
                for prim_path in material_paths:
                    prim = stage.GetPrimAtPath(prim_path)
                    if prim and prim.IsValid():
                        changed = (
                            await _convert_material_if_needed(context.stage_context_name, prim, target_output)
                            or changed
                        )

            if changed:
                context.save_stage()
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
    target_output: SupportedShaderOutputs,
) -> bool:
    """Convert a material unless it already authors the target shader.

    Args:
        context_name: USD context used by the material converter.
        material_prim: Material prim whose shader should be inspected and converted.
        target_output: AperturePBR shader variant required by the asset.

    Returns:
        True when conversion changed the material.

    Raises:
        RuntimeError: If no converter supports the shader or conversion fails.
        ValueError: If ``target_output`` is unsupported.
    """
    input_subidentifier = _get_material_shader_subidentifier(material_prim)
    if input_subidentifier == target_output.value:
        return False

    converter = await _build_converter(material_prim, input_subidentifier, target_output)
    if converter is None:
        raise RuntimeError(
            f"Unsupported material shader '{input_subidentifier}' on {material_prim.GetPath()}; "
            f"cannot convert to {target_output.value}"
        )

    success, message, _was_skipped = await MaterialConverterCore.convert(context_name, converter)
    if not success:
        raise RuntimeError(message or f"Failed to convert material {material_prim.GetPath()} to {target_output.value}")
    return not _was_skipped


def _get_material_shader_subidentifier(material_prim: Usd.Prim) -> str | None:
    """Return the normalized shader identifier authored by a material.

    Args:
        material_prim: Material prim whose connected shader should be inspected.

    Returns:
        Authored shader identifier without MDL decorations, or None when no valid shader is connected.
    """
    shader_prim = get_shader_from_material(material_prim, get_prim=True)
    if shader_prim is None or not shader_prim.IsValid():
        return None
    return _get_authored_shader_subidentifier(shader_prim)


async def _build_converter(
    material_prim: Usd.Prim, input_subidentifier: str | None, target_output: SupportedShaderOutputs
) -> ConverterBase | None:
    """Build a converter for a material and target AperturePBR shader.

    Args:
        material_prim: Material prim to pass to the matching converter builder.
        input_subidentifier: Normalized authored shader identifier, if known.
        target_output: AperturePBR shader variant required by the asset.

    Returns:
        Converter for the supported input shader, or None when no converter matches.

    Raises:
        ValueError: If ``target_output`` is not a supported AperturePBR variant.
    """
    if target_output not in (
        SupportedShaderOutputs.APERTURE_PBR_OPACITY,
        SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT,
    ):
        raise ValueError(f"Unsupported material shader output: {target_output}")

    target_subidentifier = target_output.value
    supported_inputs = {shader_input.value for shader_input in SupportedShaderInputs}

    if input_subidentifier not in supported_inputs:
        shader_prim = get_shader_from_material(material_prim, get_prim=True)
        if shader_prim is None or not shader_prim.IsValid():
            return None

        _matching_builder, matching_input = await MaterialConverterCore.find_matching_supported_material(shader_prim)
        if matching_input is None:
            return None
        input_subidentifier = matching_input.value

    if input_subidentifier == SupportedShaderInputs.OMNI_GLASS.value:
        return OmniGlassToAperturePBRConverterBuilder().build(material_prim, target_subidentifier)

    match input_subidentifier:
        case SupportedShaderInputs.OMNI_PBR.value | SupportedShaderInputs.OMNI_PBR_OPACITY.value:
            return OmniPBRToAperturePBRConverterBuilder().build(material_prim, target_subidentifier)
        case SupportedShaderInputs.USD_PREVIEW_SURFACE.value:
            return USDPreviewSurfaceToAperturePBRConverterBuilder().build(material_prim, target_subidentifier)
        case SupportedShaderInputs.NONE.value:
            return NoneToAperturePBRConverterBuilder().build(material_prim, target_subidentifier)

    carb.log_warn(
        f"[ConvertMaterials] No converter registered for material shader '{input_subidentifier}' "
        f"on {material_prim.GetPath()}"
    )
    return None


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


def _get_target_shader_output(material_type: MaterialType) -> SupportedShaderOutputs:
    """Map one Remix material semantic to its AperturePBR shader output.

    Args:
        material_type: Material opacity semantic.

    Returns:
        Matching AperturePBR shader output.

    Raises:
        ValueError: If the material type is unsupported.
    """
    if material_type is MaterialType.OPAQUE:
        return SupportedShaderOutputs.APERTURE_PBR_OPACITY
    if material_type is MaterialType.TRANSLUCENT:
        return SupportedShaderOutputs.APERTURE_PBR_TRANSLUCENT
    raise ValueError(f"Unsupported material type: {material_type}")
