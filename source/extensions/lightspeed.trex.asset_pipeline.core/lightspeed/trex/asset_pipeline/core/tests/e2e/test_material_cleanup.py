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

import pathlib
import tempfile

import omni.kit.test
from pxr import Usd, UsdGeom, UsdShade, Vt

from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import MaterialCleanupStep


_BOUND_MATERIAL = "/World/Looks/BoundMaterial"
_BOUND_MESH = "/World/BoundMesh"
_FALLBACK_ROOT = "/AssetImporter/Looks/"
_MATERIALLESS_MESH = "/World/MateriallessMesh"
_ORPHAN_MATERIAL = "/World/Looks/OrphanMaterial"
_SUBSET_MESH = "/World/SubsetMesh"
_TRIANGLE_POINTS = Vt.Vec3fArray([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)])


class TestMaterialCleanupE2E(omni.kit.test.AsyncTestCase):
    """Run the material cleanup step against real model files on disk."""

    async def test_material_cleanup_deletes_orphans_and_binds_fallbacks_on_a_real_model(self):
        """Cleanup removes unbound materials, keeps bound ones, and gives bare meshes a fallback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Author one model that holds all three conditions at once, then save it to disk.
            temp_path = pathlib.Path(temp_dir)
            model_path = temp_path / "model.usda"
            _author_mixed_material_model(model_path)

            item = RemixAssetItem.from_model(model_path)
            async with RemixAssetPipelineContext(items=[item], output_dir=temp_path / "processed") as context:
                await MaterialCleanupStep().run(context)

            # Read the saved file back through a fresh pipeline run so every check sees the published USD.
            async with RemixAssetPipelineContext() as verify_context:
                stage = await verify_context.open_stage(model_path)

                # The material that nothing referenced is gone from the file.
                self.assertFalse(stage.GetPrimAtPath(_ORPHAN_MATERIAL).IsValid())

                # The already-bound mesh still resolves the very material it started with.
                self.assertTrue(stage.GetPrimAtPath(_BOUND_MATERIAL).IsValid())
                kept_material, _ = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(_BOUND_MESH)).ComputeBoundMaterial()
                self.assertTrue(kept_material)
                self.assertEqual(str(kept_material.GetPrim().GetPath()), _BOUND_MATERIAL)

                # The mesh that had no material now resolves a runner-created fallback instead.
                fallback_material, _ = UsdShade.MaterialBindingAPI(
                    stage.GetPrimAtPath(_MATERIALLESS_MESH)
                ).ComputeBoundMaterial()
                self.assertTrue(fallback_material)
                self.assertTrue(str(fallback_material.GetPrim().GetPath()).startswith(_FALLBACK_ROOT))

    async def test_material_cleanup_binds_a_fallback_to_every_materialless_geom_subset(self):
        """A mesh split into geom subsets gets one fallback for each unbound subset, not one for the mesh."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Author a two-triangle mesh whose faces belong to two geom subsets with no material at all.
            temp_path = pathlib.Path(temp_dir)
            model_path = temp_path / "subsets.usda"
            _author_geom_subset_model(model_path)

            item = RemixAssetItem.from_model(model_path)
            async with RemixAssetPipelineContext(items=[item], output_dir=temp_path / "processed") as context:
                await MaterialCleanupStep().run(context)

            async with RemixAssetPipelineContext() as verify_context:
                stage = await verify_context.open_stage(model_path)

                # Each subset carries its own fallback material.
                subset_material_paths = []
                for subset_name in ("first", "second"):
                    subset_prim = stage.GetPrimAtPath(f"{_SUBSET_MESH}/{subset_name}")
                    subset_material, _ = UsdShade.MaterialBindingAPI(subset_prim).ComputeBoundMaterial()
                    self.assertTrue(subset_material, f"{subset_name} has no bound material")
                    subset_material_path = str(subset_material.GetPrim().GetPath())
                    self.assertTrue(subset_material_path.startswith(_FALLBACK_ROOT))
                    subset_material_paths.append(subset_material_path)

                # The two subsets do not share one material, and the mesh itself received no binding.
                self.assertNotEqual(subset_material_paths[0], subset_material_paths[1])
                mesh_material, _ = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(_SUBSET_MESH)).ComputeBoundMaterial()
                self.assertFalse(mesh_material)


def _author_mixed_material_model(model_path: pathlib.Path) -> None:
    """Author a model with a bound material, a bare mesh, and an orphan material, then save it."""
    stage = Usd.Stage.CreateNew(str(model_path))

    bound_material = UsdShade.Material.Define(stage, _BOUND_MATERIAL)
    # These meshes deliberately omit faceVertexCounts. Adding topology masks the crash in step isolation.
    # The pipeline-level test is the topology-independent guard.
    bound_mesh = UsdGeom.Mesh.Define(stage, _BOUND_MESH)
    bound_mesh.CreatePointsAttr(_TRIANGLE_POINTS)
    UsdShade.MaterialBindingAPI(bound_mesh.GetPrim()).Bind(bound_material)

    materialless_mesh = UsdGeom.Mesh.Define(stage, _MATERIALLESS_MESH)
    materialless_mesh.CreatePointsAttr(_TRIANGLE_POINTS)

    UsdShade.Material.Define(stage, _ORPHAN_MATERIAL)

    stage.GetRootLayer().Save()


def _author_geom_subset_model(model_path: pathlib.Path) -> None:
    """Author a two-triangle mesh split into two geom subsets that bind no material, then save it."""
    stage = Usd.Stage.CreateNew(str(model_path))

    mesh = UsdGeom.Mesh.Define(stage, _SUBSET_MESH)
    mesh.CreatePointsAttr(_TRIANGLE_POINTS)
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3, 3]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2, 1, 3, 2]))
    for subset_name, face_index in (("first", 0), ("second", 1)):
        UsdGeom.Subset.CreateGeomSubset(
            mesh,
            subset_name,
            UsdGeom.Tokens.face,
            Vt.IntArray([face_index]),
            UsdShade.Tokens.materialBind,
        )

    stage.GetRootLayer().Save()
