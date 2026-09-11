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

import omni.kit.app
import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from pxr import Usd, UsdGeom, UsdShade, Vt

from lightspeed.trex.asset_pipeline.core import (
    RemixAssetItem,
    RemixAssetPipelineConfig,
    RemixAssetPipelineContext,
    build_remix_mesh_pipeline,
    build_remix_texture_pipeline,
    run_remix_asset_pipeline,
)


class TestPipelineRunnerE2E(omni.kit.test.AsyncTestCase):
    async def test_texture_pipeline_processes_real_normal_map_to_final_dds(self):
        """The canonical pipeline processes a real normal texture into final published outputs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            source_path = _get_normal_fixture_path()
            item = RemixAssetItem.from_texture(source_path, TextureTypes.NORMAL_DX)
            context = RemixAssetPipelineContext(items=[item])

            # Send a real DirectX normal-map fixture through the public production pipeline.
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.NORMAL_DX),
                context,
                steps=build_remix_texture_pipeline(),
            )

            final_texture = output_dir / "Normal_Map_Test_DirectX_OTH_Normal.n.rtex.dds"

            # The pipeline publishes the octahedral DDS and updates the item to reference that final asset.
            self.assertEqual(item.textures[0].path, final_texture)
            self.assertEqual(item.textures[0].texture_type, TextureTypes.NORMAL_OTH)
            self.assertTrue(final_texture.exists())
            self.assertEqual(final_texture.read_bytes()[:4], b"DDS ")

            # Successful completion removes both the intermediate PNG and the pipeline working directory.
            self.assertFalse((output_dir / "Normal_Map_Test_DirectX_OTH_Normal.png").exists())
            self.assertEqual(
                sorted(path for path in temp_path.iterdir() if path.name.startswith("remix_asset_pipeline_")),
                [],
            )
            self.assertIsNone(context.work_dir)

    async def test_texture_pipeline_records_real_step_execution_state(self):
        """The canonical pipeline reports run and skip state for a real texture."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            item = RemixAssetItem.from_texture(_get_normal_fixture_path(), TextureTypes.NORMAL_DX)
            context = RemixAssetPipelineContext(items=[item])

            # Process a texture-only item with the texture pipeline plus metadata.
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=temp_path / "processed", texture_type=TextureTypes.NORMAL_DX),
                context,
                steps=build_remix_texture_pipeline(),
            )

            # Texture stages report execution.
            self.assertTrue(context.execution_state["convert_normal"].did_run)
            self.assertTrue(context.execution_state["convert_dds"].did_run)

    async def test_mesh_pipeline_publishes_material_cleanup_changes(self):
        """The full mesh pipeline publishes no orphan and preserves both required material bindings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "model.usda"
            output_dir = temp_path / "processed"
            _author_mesh_pipeline_material_model(source_path)
            item = RemixAssetItem.from_model(source_path)
            config = RemixAssetPipelineConfig(output_dir=output_dir, texture_type=None)

            await run_remix_asset_pipeline(
                config,
                RemixAssetPipelineContext(items=[item]),
                steps=build_remix_mesh_pipeline(config, {}),
            )

            self.assertTrue(item.value.exists())
            async with RemixAssetPipelineContext() as verify_context:
                stage = await verify_context.open_stage(item.value)

                self.assertIsNone(_find_prim_by_name(stage, "OrphanMaterial"))
                bound_mesh = _find_prim_by_name(stage, "BoundMesh")
                materialless_mesh = _find_prim_by_name(stage, "MateriallessMesh")
                bound_material = _find_prim_by_name(stage, "BoundMaterial")
                self.assertIsNotNone(bound_mesh)
                self.assertIsNotNone(materialless_mesh)
                self.assertIsNotNone(bound_material)

                kept_material, _ = UsdShade.MaterialBindingAPI(bound_mesh).ComputeBoundMaterial()
                self.assertTrue(kept_material)
                self.assertEqual(kept_material.GetPrim().GetName(), "BoundMaterial")

                fallback_material, _ = UsdShade.MaterialBindingAPI(materialless_mesh).ComputeBoundMaterial()
                self.assertTrue(fallback_material)
                self.assertEqual(fallback_material.GetPrim().GetName(), "MateriallessMesh")


def _get_normal_fixture_path() -> pathlib.Path:
    extension_root = pathlib.Path(
        omni.kit.app.get_app()
        .get_extension_manager()
        .get_extension_path_by_module("omni.flux.utils.octahedral_converter")
    )
    return extension_root / "data" / "tests" / "textures" / "Normal_Map_Test_DirectX.png"


def _author_mesh_pipeline_material_model(model_path: pathlib.Path) -> None:
    """Author topology-complete bound, bare, and orphan material conditions for the mesh pipeline."""
    stage = Usd.Stage.CreateNew(str(model_path))

    bound_material = UsdShade.Material.Define(stage, "/World/Looks/BoundMaterial")
    shader = UsdShade.Shader.Define(stage, "/World/Looks/BoundMaterial/Shader")
    shader.CreateIdAttr("AperturePBR_Opacity")
    bound_material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    bound_mesh = _define_triangle_mesh(stage, "/World/BoundMesh")
    UsdShade.MaterialBindingAPI(bound_mesh.GetPrim()).Bind(bound_material)
    _define_triangle_mesh(stage, "/World/MateriallessMesh")
    orphan_material = UsdShade.Material.Define(stage, "/World/Looks/OrphanMaterial")
    orphan_shader = UsdShade.Shader.Define(stage, "/World/Looks/OrphanMaterial/Shader")
    orphan_shader.CreateIdAttr("AperturePBR_Opacity")
    orphan_material.CreateSurfaceOutput().ConnectToSource(orphan_shader.ConnectableAPI(), "surface")

    stage.GetRootLayer().Save()


def _define_triangle_mesh(stage: Usd.Stage, path: str) -> UsdGeom.Mesh:
    """Define one topology-complete triangle mesh for the full mesh pipeline."""
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([(0, 0, 0), (1, 0, 0), (0, 1, 0)]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2]))
    return mesh


def _find_prim_by_name(stage: Usd.Stage, name: str) -> Usd.Prim | None:
    """Return the one composed prim with ``name``, or None when the pipeline removed it."""
    return next((prim for prim in stage.TraverseAll() if prim.GetName() == name), None)
