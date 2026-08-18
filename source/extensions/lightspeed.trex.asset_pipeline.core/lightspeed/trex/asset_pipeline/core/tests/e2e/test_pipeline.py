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

import json
import pathlib
import tempfile

import omni.kit.app
import omni.usd
import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import Sdf, Usd, UsdGeom, UsdShade

from lightspeed.trex.asset_pipeline.core import (
    MaterialType,
    RemixAssetItem,
    RemixAssetPipelineConfig,
    RemixAssetPipelineContext,
    run_remix_asset_pipeline,
)


class TestRemixAssetPipelineE2E(omni.kit.test.AsyncTestCase):
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
            )

            final_texture = output_dir / "Normal_Map_Test_DirectX.normal_dx.octahedral.normal_oth.dds"
            final_metadata = final_texture.with_suffix(".dds.meta")

            # The pipeline publishes the octahedral DDS and updates the item to reference that final asset.
            self.assertEqual(item.textures[0].path, final_texture)
            self.assertEqual(item.textures[0].texture_type, TextureTypes.NORMAL_OTH)
            self.assertTrue(final_texture.exists())
            self.assertEqual(final_texture.read_bytes()[:4], b"DDS ")

            # Publication writes validation metadata beside the final texture.
            self.assertTrue(final_metadata.exists())
            metadata = json.loads(final_metadata.read_text())
            self.assertRegex(metadata["base_hash"], r"^[0-9a-f]{32}$")
            self.assertTrue(metadata["validation_passed"])

            # Successful completion removes both the intermediate PNG and the pipeline working directory.
            self.assertFalse((output_dir / "Normal_Map_Test_DirectX.normal_dx.octahedral.png").exists())
            self.assertEqual(_remaining_work_dirs(temp_path), [])
            self.assertIsNone(context.work_dir)

    async def test_texture_pipeline_records_real_step_execution_state(self):
        """The canonical pipeline reports run and skip state for a real texture."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            item = RemixAssetItem.from_texture(_get_normal_fixture_path(), TextureTypes.NORMAL_DX)
            context = RemixAssetPipelineContext(items=[item])

            # Process a texture-only item so model-specific stages have nothing to consume.
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=temp_path / "processed", texture_type=TextureTypes.NORMAL_DX),
                context,
            )

            # Texture stages report execution while model stages explain why they were skipped.
            self.assertTrue(context.execution_state["convert_normal"].did_run)
            self.assertTrue(context.execution_state["convert_dds"].did_run)
            self.assertTrue(context.execution_state["write_metadata"].did_run)
            self.assertEqual(context.execution_state["triangulate_meshes"].skip_reason, "no model items")
            self.assertEqual(context.execution_state["update_textures"].skip_reason, "no model items")

    async def test_normal_conventions_keep_distinct_outputs_for_shared_source(self):
        """DirectX and OpenGL interpretations of one source never overwrite each other."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = _get_normal_fixture_path()
            batch_output_dir = temp_path / "batch"
            batch_items = [
                RemixAssetItem.from_texture(source_path, TextureTypes.NORMAL_DX),
                RemixAssetItem.from_texture(source_path, TextureTypes.NORMAL_OGL),
            ]

            # Process both interpretations in one real batch.
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=batch_output_dir, texture_type=None),
                RemixAssetPipelineContext(items=batch_items, source_root=source_path.parent),
            )

            batch_paths = [item.textures[0].path for item in batch_items]
            self.assertEqual(
                [path.name for path in batch_paths],
                [
                    "Normal_Map_Test_DirectX.normal_dx.octahedral.normal_oth.dds",
                    "Normal_Map_Test_DirectX.normal_ogl.octahedral.normal_oth.dds",
                ],
            )
            self.assertNotEqual(batch_paths[0].read_bytes(), batch_paths[1].read_bytes())

            # Process each interpretation in an independent context that shares one durable destination.
            separate_output_dir = temp_path / "separate"
            separate_paths = []
            for texture_type in (TextureTypes.NORMAL_DX, TextureTypes.NORMAL_OGL):
                item = RemixAssetItem.from_texture(source_path, texture_type)
                await run_remix_asset_pipeline(
                    RemixAssetPipelineConfig(output_dir=separate_output_dir, texture_type=None),
                    RemixAssetPipelineContext(items=[item], source_root=source_path.parent),
                )
                separate_paths.append(item.textures[0].path)

            # Stable semantic filenames preserve both convention-specific byte streams across runs.
            self.assertEqual([path.name for path in separate_paths], [path.name for path in batch_paths])
            self.assertNotEqual(separate_paths[0].read_bytes(), separate_paths[1].read_bytes())

    async def test_fbx_model_pipeline_processes_real_textures_to_usd_with_dds_references(self):
        """The canonical pipeline processes a real textured FBX through every model and texture step."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_model = _get_textured_fbx_fixture_path()
            output_dir = temp_path / "processed"
            item = RemixAssetItem.from_model(source_model, MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            # Process the real textured FBX through import, conversion, publication, and cleanup.
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                context,
            )

            final_model = output_dir / "SM_Fixture_Elevator_Interior_Textured.opaque.usd"

            # The resulting item references one published USD plus its converted DDS textures and metadata.
            self.assertEqual(item.value, final_model)
            self.assertTrue(final_model.exists())
            self.assertTrue(final_model.with_suffix(".usd.meta").exists())
            self.assertGreater(len(item.textures), 0)
            self.assertGreater(len(item.texture_bindings), 0)
            for texture in item.textures:
                self.assertEqual(texture.path.parent, output_dir)
                self.assertEqual(texture.path.suffix, ".dds")
                self.assertTrue(texture.path.exists(), str(texture.path))
                self.assertEqual(texture.path.read_bytes()[:4], b"DDS ")
                self.assertTrue(texture.path.with_suffix(".dds.meta").exists(), str(texture.path))
            self.assertTrue(any(texture.texture_type is TextureTypes.NORMAL_OTH for texture in item.textures))
            # No temporary texture or work-directory state survives successful publication.
            self.assertFalse(any(path.suffix == ".png" for path in output_dir.iterdir()))
            self.assertEqual(_remaining_work_dirs(temp_path), [])
            self.assertIsNone(context.work_dir)

    async def test_fbx_model_pipeline_authors_triangulated_usd_with_dds_references(self):
        """A published model stage contains triangulated geometry and final DDS bindings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            item = RemixAssetItem.from_model(_get_textured_fbx_fixture_path(), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            # Build the final stage through the real pipeline before inspecting authored USD data.
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                context,
            )
            final_model = output_dir / "SM_Fixture_Elevator_Interior_Textured.opaque.usd"

            final_stage = Usd.Stage.Open(str(final_model))

            # The published stage uses triangulated meshes, Remix materials, and resolvable DDS bindings.
            self.assertIsNotNone(final_stage)
            self.assertGreater(_count_meshes(final_stage), 0)
            self.assertTrue(_all_meshes_are_triangulated(final_stage))
            self.assertTrue(_all_materials_use_shader(final_stage, "AperturePBR_Opacity"))
            for binding in item.texture_bindings:
                shader_prim = final_stage.GetPrimAtPath(binding.shader_path)
                self.assertTrue(shader_prim.IsValid(), str(binding.shader_path))
                asset_path = shader_prim.GetAttribute(binding.input_name).Get()
                self.assertIsInstance(asset_path, Sdf.AssetPath)
                self.assertEqual(pathlib.Path(asset_path.path).suffix, ".dds")
                self.assertTrue(_resolve_relative_asset_path(final_model, asset_path.path).exists(), asset_path.path)

    async def test_fbx_model_pipeline_records_every_canonical_step(self):
        """The canonical pipeline reports every model and texture step for a real FBX."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            item = RemixAssetItem.from_model(_get_textured_fbx_fixture_path(), MaterialType.OPAQUE)
            context = RemixAssetPipelineContext(items=[item])

            # A model with bound textures exercises every stage in the canonical production chain.
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=temp_path / "processed", texture_type=TextureTypes.DIFFUSE),
                context,
            )

            # Each canonical stage records that it handled the model instead of silently bypassing work.
            self.assertTrue(context.execution_state["standardize_input"].did_run)
            self.assertTrue(context.execution_state["triangulate_meshes"].did_run)
            self.assertTrue(context.execution_state["convert_materials"].did_run)
            self.assertTrue(context.execution_state["collect_textures"].did_run)
            self.assertTrue(context.execution_state["convert_normal"].did_run)
            self.assertTrue(context.execution_state["convert_dds"].did_run)
            self.assertTrue(context.execution_state["update_textures"].did_run)
            self.assertTrue(context.execution_state["write_metadata"].did_run)
            self.assertEqual(set(context.execution_state), _CANONICAL_STEP_NAMES)

    async def test_repeated_usd_collection_keeps_stable_dependency_outputs(self):
        """Collected USD dependencies keep their project-relative identity across runs."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            with tempfile.TemporaryDirectory() as temp_dir:
                source_model = pathlib.Path(project_url.path)
                source_root = source_model.parent
                output_dir = pathlib.Path(temp_dir) / "processed"
                completed_paths = []

                # Process the same real textured USD twice through independent pipeline contexts.
                for _run_index in range(2):
                    item = RemixAssetItem.from_model(source_model, MaterialType.OPAQUE)
                    await run_remix_asset_pipeline(
                        RemixAssetPipelineConfig(output_dir=output_dir, texture_type=None),
                        RemixAssetPipelineContext(items=[item], source_root=source_root),
                    )
                    completed_paths.append(tuple(texture.path for texture in item.textures))

                # Both runs reuse the same readable destinations without UUID-derived external folders.
                self.assertEqual(completed_paths[0], completed_paths[1])
                self.assertTrue(completed_paths[0])
                self.assertTrue(all(path.exists() for path in completed_paths[0]))
                self.assertFalse(any("_external" in path.parts for path in output_dir.rglob("*")))
                self.assertEqual(
                    set(output_dir.rglob("*.dds")),
                    set(completed_paths[0]),
                )

    async def test_repeated_fbx_collection_keeps_stable_dependency_outputs(self):
        """Imported model dependencies keep stable source identities across independent runs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_model = _get_textured_fbx_fixture_path()
            source_root = source_model.parent
            output_dir = pathlib.Path(temp_dir) / "processed"
            completed_paths = []

            # Import and process the same real textured FBX twice through independent workspaces.
            for _run_index in range(2):
                item = RemixAssetItem.from_model(source_model, MaterialType.OPAQUE)
                await run_remix_asset_pipeline(
                    RemixAssetPipelineConfig(output_dir=output_dir, texture_type=None),
                    RemixAssetPipelineContext(items=[item], source_root=source_root),
                )
                completed_paths.append(tuple(texture.path for texture in item.textures))

            # Both runs reuse the same model-relative outputs without UUID-derived external folders.
            self.assertEqual(completed_paths[0], completed_paths[1])
            self.assertTrue(completed_paths[0])
            self.assertTrue(all(path.exists() for path in completed_paths[0]))
            self.assertFalse(any("_external" in path.parts for path in output_dir.rglob("*")))
            self.assertEqual(set(output_dir.rglob("*.dds")), set(completed_paths[0]))


def _get_normal_fixture_path() -> pathlib.Path:
    extension_root = pathlib.Path(
        omni.kit.app.get_app()
        .get_extension_manager()
        .get_extension_path_by_module("omni.flux.utils.octahedral_converter")
    )
    return extension_root / "data" / "tests" / "textures" / "Normal_Map_Test_DirectX.png"


def _get_textured_fbx_fixture_path() -> pathlib.Path:
    extension_root = pathlib.Path(
        omni.kit.app.get_app().get_extension_manager().get_extension_path_by_module("omni.flux.asset_importer.core")
    )
    return (
        extension_root / "data" / "tests" / "SM_Fixture_Elevator_Interior" / "SM_Fixture_Elevator_Interior_Textured.fbx"
    )


def _remaining_work_dirs(parent: pathlib.Path) -> list[pathlib.Path]:
    return sorted(path for path in parent.iterdir() if path.name.startswith("remix_asset_pipeline_"))


def _count_meshes(stage: Usd.Stage) -> int:
    return sum(1 for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh))


def _all_meshes_are_triangulated(stage: Usd.Stage) -> bool:
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        face_counts = UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get()
        if face_counts is None or set(face_counts) != {3}:
            return False
    return True


def _all_materials_use_shader(stage: Usd.Stage, shader_name: str) -> bool:
    material_prims = [prim for prim in stage.Traverse() if prim.IsA(UsdShade.Material)]
    if not material_prims:
        return False
    for material_prim in material_prims:
        shader_prim = omni.usd.get_shader_from_material(material_prim, get_prim=True)
        if shader_prim is None or not shader_prim.IsValid():
            return False
        subidentifier_attr = shader_prim.GetAttribute("info:mdl:sourceAsset:subIdentifier")
        if not subidentifier_attr or subidentifier_attr.Get() != shader_name:
            return False
    return True


def _resolve_relative_asset_path(model_path: pathlib.Path, asset_path: str) -> pathlib.Path:
    texture_path = pathlib.Path(asset_path)
    if texture_path.is_absolute():
        return texture_path
    return model_path.parent / texture_path


_CANONICAL_STEP_NAMES = {
    "standardize_input",
    "triangulate_meshes",
    "convert_materials",
    "collect_textures",
    "convert_normal",
    "convert_dds",
    "update_textures",
    "write_metadata",
    "publish_outputs",
}

_PROJECT_STAGE = "usd/project_example/combined.usda"
_RESOURCE_CONTEXT = "asset_pipeline_stable_dependency_project"
