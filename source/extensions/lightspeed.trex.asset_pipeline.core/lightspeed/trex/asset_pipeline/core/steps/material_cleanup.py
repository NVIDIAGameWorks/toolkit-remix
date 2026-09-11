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

__all__ = ["MaterialCleanupStep"]

import carb
import omni.kit.commands
import omni.usd
import omni.usd.commands
from omni.flux.asset_pipeline.core import PipelineContext, PipelineStep
from pxr import Sdf, Usd, UsdGeom, UsdShade

from ..pipeline.context import RemixAssetPipelineContext
from ..pipeline.item import AssetKind, RemixAssetItem


class MaterialCleanupStep(PipelineStep):
    """Delete orphaned materials, then bind fallback OmniPBR materials to materialless meshes."""

    context_type = RemixAssetPipelineContext
    item_types = (RemixAssetItem,)

    @property
    def name(self) -> str:
        """Return the step identifier."""
        return "material_cleanup"

    @property
    def description(self) -> str:
        """Return a human-readable description."""
        return "Remove orphaned materials and add fallback materials"

    def validate(self, context: PipelineContext) -> list[str]:
        """Require a runner-owned output directory before creating fallback materials."""
        errors = super().validate(context)
        if errors:
            return errors
        if any(item.kind is AssetKind.MODEL for item in context.items):
            errors.extend(context.validate_output_dir(self.name))
        return errors

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        """Return whether the context contains any model items."""
        return any(item.kind is AssetKind.MODEL for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        """Return why this step has no material cleanup work."""
        return "no model items"

    async def run(self, context: RemixAssetPipelineContext) -> None:
        """Delete orphaned materials and bind fallback materials for every model item."""
        for item in context.items:
            if item.kind is not AssetKind.MODEL:
                continue

            stage = await context.open_stage(item.value)
            deleted = _clear_unassigned_materials(stage)
            created = _create_default_materials(stage)

            if deleted or created:
                await context.save_stage()
                carb.log_info(
                    f"[MaterialCleanup] Deleted {deleted} orphaned and created {created} "
                    f"fallback materials in {item.value}"
                )


def _clear_unassigned_materials(stage: Usd.Stage) -> int:
    """Delete every material prim that is not bound to any mesh or geom subset.

    Args:
        stage: Model stage to clean up.

    Returns:
        Number of deleted material prims.
    """
    bound_materials: set[Sdf.Path] = set()
    for prim in stage.Traverse():
        if not (prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Subset)):
            continue
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if material:
            bound_materials.add(material.GetPrim().GetPath())

    to_delete = [
        prim.GetPath()
        for prim in stage.TraverseAll()
        if prim.IsA(UsdShade.Material)
        and prim.GetPath() not in bound_materials
        and omni.usd.commands.prim_can_be_removed_without_destruction(stage, prim.GetPath())
    ]
    if to_delete:
        omni.kit.commands.execute("DeletePrims", paths=to_delete, stage=stage)
    return len(to_delete)


def _create_default_materials(stage: Usd.Stage) -> int:
    """Bind a fallback OmniPBR material to every mesh or geom subset without one.

    Args:
        stage: Model stage to update.

    Returns:
        Number of fallback materials created.
    """
    created = 0
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        for materialless in _get_materialless_prims(prim):
            _create_default_material(stage, materialless)
            created += 1
    return created


def _get_materialless_prims(mesh_prim: Usd.Prim) -> list[Usd.Prim]:
    """Return the geom subsets, or the mesh itself, that need a fallback material.

    Args:
        mesh_prim: Mesh prim to inspect.

    Returns:
        Geom subset prims without a bound material, or ``[mesh_prim]`` when the mesh
        has no geom subsets and is not empty. Empty when the mesh already has a
        bound material.
    """
    bound_material, _ = UsdShade.MaterialBindingAPI(mesh_prim).ComputeBoundMaterial()
    if bound_material:
        return []

    materialless: list[Usd.Prim] = []
    has_geom_subset = False
    for child_prim in mesh_prim.GetChildren():
        if not child_prim.IsA(UsdGeom.Subset):
            continue
        has_geom_subset = True
        subset_bound_material, _ = UsdShade.MaterialBindingAPI(child_prim).ComputeBoundMaterial()
        if not subset_bound_material:
            materialless.append(child_prim)

    if not has_geom_subset and UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get():
        materialless.append(mesh_prim)

    return materialless


def _create_default_material(stage: Usd.Stage, prim: Usd.Prim) -> None:
    """Create and bind a unique-path fallback OmniPBR material for one prim.

    Args:
        stage: Model stage that owns ``prim``.
        prim: Mesh or geom subset prim needing a fallback material.
    """
    mtl_path = omni.usd.get_stage_next_free_path(stage, f"/AssetImporter/Looks/{prim.GetName()}", False)

    omni.kit.commands.execute(
        "CreateMdlMaterialPrim",
        mtl_url="OmniPBR.mdl",
        mtl_name="OmniPBR",
        mtl_path=mtl_path,
        stage=stage,
    )
    omni.kit.commands.execute(
        "BindMaterial",
        prim_path=prim.GetPath(),
        material_path=mtl_path,
        strength=UsdShade.Tokens.strongerThanDescendants,
        stage=stage,
    )
