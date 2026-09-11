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

__all__ = ["MetaStep"]

import carb
import omni.usd
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from omni.flux.utils.common.prims import get_omni_prims
from pxr import Gf, Kind, Sdf, Usd, UsdGeom

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import AssetKind, RemixAssetItem

_METERS_PER_UNIT_KEY = "metersPerUnit"
_UNIT_SCALE_TARGET = 1.0


class MetaStep(PipelineStep):
    """Wrap processed model roots and normalize unit scale before final metadata is hashed."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "meta"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Wrap processed model roots and normalize unit scale"

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return whether the context contains any model items."""
        return any(item.kind is AssetKind.MODEL for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no structural wrapping work."""
        return "no model items"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Group model root prims under ReferenceTarget/XForms and normalize unit scale."""
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            stage = await context.open_stage(item.value)

            _wrap_root_prims(stage, "XForms")
            _apply_unit_scale(stage)
            _wrap_root_prims(stage, "ReferenceTarget")

            await context.save_stage()
            carb.log_info(f"[Meta] Wrapped roots and normalized unit scale for {item.value}")


def _get_root_prims(stage: Usd.Stage) -> list[Usd.Prim]:
    """Return top-level content prims eligible for wrapping.

    Args:
        stage: Model stage to inspect.

    Returns:
        Root prims excluding session-layer overrides and reserved Kit prims.
    """
    session_layer = stage.GetSessionLayer()
    omni_prims = get_omni_prims()
    return [
        prim
        for prim in stage.GetPseudoRoot().GetChildren()
        if not session_layer.GetPrimAtPath(prim.GetPath()) and prim.GetPath() not in omni_prims
    ]


def _move_prim(stage: Usd.Stage, from_path: Sdf.Path, to_path: Sdf.Path) -> None:
    """Reparent one composed prim to a new path, merging opinions from every contributing layer.

    Mirrors ``omni.usd``'s non-destructive ``MovePrim`` command logic directly on the stage. That
    command keeps Selection and undo bookkeeping, which is unstable on an isolated background USD
    context inside a long batch run. Its plain ``omni.usd`` and ``Sdf`` building blocks give the
    same correct multi-layer move without that instability. Use the command again if upstream
    makes it stable.

    Args:
        stage: Model stage containing the prim.
        from_path: Current composed prim path.
        to_path: Free destination path.
    """
    edit_target_layer = stage.GetEditTarget().GetLayer()
    layer_stack = stage.GetLayerStack()
    prim = stage.GetPrimAtPath(from_path)

    foreign_layers = [
        layer
        for layer in layer_stack
        if layer != edit_target_layer and not layer.anonymous and layer.GetPrimAtPath(from_path)
    ]

    with Sdf.ChangeBlock():
        if not foreign_layers:
            # Every opinion lives in the edit target (or an anonymous layer): a plain per-layer
            # namespace edit keeps the output free of leftover deactivated prims.
            for prim_spec in prim.GetPrimStack():
                layer = prim_spec.layer
                if layer not in layer_stack:
                    continue
                edit = Sdf.BatchNamespaceEdit()
                edit.Add(from_path, to_path)
                layer.Apply(edit)
                omni.usd.resolve_prim_path_references(layer.identifier, str(from_path), str(to_path))
        else:
            # Opinions live in real on-disk layers (e.g. a collected dependency sublayer) that must
            # not be edited directly: flatten them into the edit target at the new path and
            # deactivate the old composed prim instead.
            omni.usd.stitch_prim_specs(stage, from_path, edit_target_layer, to_path)
            stage.GetPrimAtPath(from_path).SetActive(False)
            omni.usd.resolve_prim_path_references(edit_target_layer.identifier, str(from_path), str(to_path))


def _wrap_root_prims(stage: Usd.Stage, wrap_prim_name: str) -> None:
    """Group current root prims under one new Xform and set it as the default prim.

    The wrapper carries what the legacy ``GroupPrims`` command authored: ``kind = "group"`` and an
    identity translate/rotateXYZ/scale transform. The unit-scale pass then lands on that scale op,
    exactly as ``ApplyUnitScale`` did on the legacy wrapper.

    Args:
        stage: Model stage whose root prims are grouped.
        wrap_prim_name: Name of the new wrapper Xform prim.
    """
    root_prims = _get_root_prims(stage)
    if not root_prims:
        return

    wrap_path = Sdf.Path(omni.usd.get_stage_next_free_path(stage, Sdf.Path(f"/{wrap_prim_name}"), False))
    wrapper = UsdGeom.Xform.Define(stage, wrap_path).GetPrim()
    Usd.ModelAPI(wrapper).SetKind(Kind.Tokens.group)

    for prim in root_prims:
        _move_prim(stage, prim.GetPath(), wrap_path.AppendChild(prim.GetName()))

    common_api = UsdGeom.XformCommonAPI(wrapper)
    common_api.SetTranslate(Gf.Vec3d(0, 0, 0))
    common_api.SetRotate(Gf.Vec3f(0, 0, 0))
    common_api.SetScale(Gf.Vec3f(1, 1, 1))

    stage.SetDefaultPrim(wrapper)


def _apply_unit_scale(stage: Usd.Stage) -> None:
    """Normalize the stage unit scale, proportionally scaling current root prim xformOps.

    Args:
        stage: Model stage whose root prims and unit metadata are normalized.
    """
    meters_per_unit = stage.GetMetadata(_METERS_PER_UNIT_KEY)
    if not meters_per_unit:
        return

    for prim in _get_root_prims(stage):
        if not prim.IsA(UsdGeom.Xform):
            continue
        for xform_op in UsdGeom.Xformable(prim).GetOrderedXformOps():
            if xform_op.GetOpType() != UsdGeom.XformOp.TypeScale:
                continue
            xform_op.Set(xform_op.Get() * (_UNIT_SCALE_TARGET / meters_per_unit))

    stage.SetMetadata(_METERS_PER_UNIT_KEY, 1 / _UNIT_SCALE_TARGET)
