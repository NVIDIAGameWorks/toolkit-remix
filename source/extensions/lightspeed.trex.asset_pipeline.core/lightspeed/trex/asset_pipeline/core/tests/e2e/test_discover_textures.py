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

import hashlib
import pathlib
import shutil
import tempfile

import omni.kit.test
from lightspeed.common.constants import MATERIAL_INPUTS_NORMALMAP_ENCODING
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import Sdf, Usd, UsdShade

from lightspeed.trex.asset_pipeline.core import RemixAssetItem
from lightspeed.trex.asset_pipeline.core.pipeline.context import RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps.discover_textures import DiscoverTexturesStep

_PROJECT_STAGE = "usd/project_example/combined.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"


def _hash_file(path: pathlib.Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_textured_stage(stage_path: pathlib.Path, texture_file: pathlib.Path, input_name: str) -> None:
    """Create a minimal USD stage with one Material, one Shader, and one texture input.

    Args:
        stage_path: Output path for the USD stage file.
        texture_file: Existing texture file to reference from the shader input.
        input_name: Authored shader input name, such as ``inputs:diffuse_texture``.
    """
    stage = Usd.Stage.CreateNew(str(stage_path))
    material_path = Sdf.Path("/Model/Material")
    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, material_path.AppendChild("Shader"))
    shader.CreateIdAttr("AperturePBR_Opacity")
    # Connect the shader to the material's mdl surface output. Without the connection
    # ``omni.usd.get_shader_from_material`` resolves nothing, so the step sees no shader at all.
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    # ``CreateInput`` adds the ``inputs:`` namespace itself, so pass the base name only.
    attr = shader.CreateInput(input_name.removeprefix("inputs:"), Sdf.ValueTypeNames.Asset)
    attr.Set(Sdf.AssetPath(str(texture_file)))
    stage.GetRootLayer().Save()


class TestDiscoverTexturesE2E(omni.kit.test.AsyncTestCase):
    """Test DiscoverTexturesStep against real model stages."""

    async def test_discovers_normal_map_as_normal_type(self):
        """A shader with a normal-map input is typed as a normal texture, not DIFFUSE or OTHER."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Step 1: Author a real model stage on disk with a normal-map shader input that points
            # at a real texture file.
            temp_path = pathlib.Path(temp_dir)
            stage_path = temp_path / "model.usda"
            texture_file = temp_path / "normal.png"
            texture_file.write_bytes(b"fake_normal_data")
            _create_textured_stage(stage_path, texture_file, "inputs:normalmap_texture")
            # Step 2: Author a DX normal-map encoding on the shader, so the step must read the
            # encoding instead of guessing from the file name.
            stage = Usd.Stage.Open(str(stage_path))
            shader_prim = stage.GetPrimAtPath("/Model/Material/Shader")
            encoding_attr = shader_prim.CreateAttribute("inputs:normalmap_encoding", Sdf.ValueTypeNames.Int)
            encoding_attr.Set(2)  # DX encoding
            stage.GetRootLayer().Save()

            item = RemixAssetItem.from_model(stage_path)
            item.value = stage_path
            step = DiscoverTexturesStep()

            async with RemixAssetPipelineContext(items=[item], source_root=temp_path) as context:
                # Step 3: Run discovery against the real stage through the pipeline USD context.
                await step.run(context)

            # Step 4: Verify the discovered record carries the DX normal type from the encoding.
            self.assertEqual(len(item.textures), 1, "Expected exactly one discovered texture")
            discovered = item.textures[0]
            self.assertEqual(discovered.path, texture_file)
            self.assertEqual(discovered.texture_type, TextureTypes.NORMAL_DX)
            self.assertNotEqual(discovered.texture_type, TextureTypes.OTHER)
            self.assertNotEqual(discovered.texture_type, TextureTypes.DIFFUSE)

    async def test_discovers_udim_pattern_through_its_tiles_beside_the_source_model(self):
        """A relative <UDIM> pattern resolves through its concrete tiles next to the source model."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Step 1: Author the model in a source directory with two concrete tiles beside it. The
            # shader references the tiles through a relative <UDIM> pattern, which never exists as a
            # file itself.
            temp_path = pathlib.Path(temp_dir)
            source_dir = temp_path / "source"
            source_dir.mkdir()
            for tile in ("1001", "1002"):
                (source_dir / f"albedo.{tile}.png").write_bytes(b"fake_tile_data")
            source_model = source_dir / "model.usda"
            _create_textured_stage(source_model, pathlib.Path("./albedo.<UDIM>.png"), "inputs:diffuse_texture")

            # Step 2: The pipeline works on a copy in a different directory, as the prepare phase does,
            # so the stage-relative pattern resolves to a place with no tiles.
            work_dir = temp_path / "work"
            work_dir.mkdir()
            work_model = work_dir / "model.usda"
            shutil.copy2(source_model, work_model)
            item = RemixAssetItem.from_model(source_model)
            item.value = work_model
            step = DiscoverTexturesStep()

            async with RemixAssetPipelineContext(items=[item], source_root=temp_path) as context:
                # Step 3: Discovery must fall back to the source directory and accept the pattern there.
                await step.run(context)

            # Step 4: The record keeps the pattern path, anchored beside the source model.
            self.assertEqual(len(item.textures), 1, "Expected exactly one discovered texture")
            self.assertEqual(item.textures[0].path, (source_dir / "albedo.<UDIM>.png").resolve())
            self.assertEqual(item.textures[0].texture_type, TextureTypes.DIFFUSE)

    async def test_discovery_fails_on_udim_pattern_without_tiles(self):
        """A <UDIM> pattern with no concrete tile anywhere is a missing texture, not a silent pass."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            stage_path = temp_path / "model.usda"
            _create_textured_stage(stage_path, pathlib.Path("./albedo.<UDIM>.png"), "inputs:diffuse_texture")
            item = RemixAssetItem.from_model(stage_path)
            item.value = stage_path
            step = DiscoverTexturesStep()

            with self.assertRaises(FileNotFoundError):
                async with RemixAssetPipelineContext(items=[item], source_root=temp_path) as context:
                    await step.run(context)

    async def test_leaves_stage_unmodified(self):
        """The discovery step does not write to or save the stage file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Step 1: Author a real model stage on disk and record its digest before the run.
            temp_path = pathlib.Path(temp_dir)
            stage_path = temp_path / "model.usda"
            texture_file = temp_path / "diffuse.png"
            texture_file.write_bytes(b"fake_diffuse_data")
            _create_textured_stage(stage_path, texture_file, "inputs:diffuse_texture")

            hash_before = _hash_file(stage_path)

            item = RemixAssetItem.from_model(stage_path)
            item.value = stage_path
            step = DiscoverTexturesStep()

            async with RemixAssetPipelineContext(items=[item], source_root=temp_path) as context:
                # Step 2: Run discovery against the real stage through the pipeline USD context.
                await step.run(context)

            # Step 3: Verify the file on disk is byte-identical, so discovery stayed read-only.
            hash_after = _hash_file(stage_path)
            self.assertEqual(hash_before, hash_after, "Stage file was modified by DiscoverTexturesStep")

    async def test_records_referenced_layers(self):
        """The discovery step records composed layer identifiers on the context."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            # Step 1: Author a standalone sublayer file the model stage will reference.
            sublayer_path = temp_path / "sublayer.usda"
            sub_stage = Usd.Stage.CreateNew(str(sublayer_path))
            sub_stage.GetRootLayer().Save()

            # Step 2: Author the model stage with a texture input.
            stage_path = temp_path / "model.usda"
            texture_file = temp_path / "diffuse.png"
            texture_file.write_bytes(b"fake_diffuse_data")
            _create_textured_stage(stage_path, texture_file, "inputs:diffuse_texture")
            # Step 3: Reference the sublayer from the root prim so the composed stage spans two files.
            stage = Usd.Stage.Open(str(stage_path))
            root_prim = stage.GetPrimAtPath(Sdf.Path("/Model"))
            if root_prim:
                root_prim.GetReferences().AddReference(str(sublayer_path))
            stage.GetRootLayer().Save()

            item = RemixAssetItem.from_model(stage_path)
            item.value = stage_path
            step = DiscoverTexturesStep()

            async with RemixAssetPipelineContext(items=[item], source_root=temp_path) as context:
                # Step 4: Run discovery against the real composed stage.
                await step.run(context)

            # Step 5: Verify the context recorded the composed layer identifiers as strings.
            referenced = getattr(context, "referenced_layers", ())
            self.assertIsInstance(referenced, tuple)
            self.assertGreater(len(referenced), 0, "Expected at least one referenced layer")
            self.assertTrue(all(isinstance(layer, str) for layer in referenced))
            # Step 6: The root layer must be among the referenced layers.
            root_identifiers = [layer for layer in referenced if "model" in layer]
            self.assertTrue(root_identifiers, "Root layer not found in referenced layers")

    async def test_discovers_normal_map_as_directx_when_no_encoding_is_authored(self):
        """An unauthored normal-map encoding defaults to DirectX, not an unknown or OGL type."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            stage_path = temp_path / "model.usda"
            texture_file = temp_path / "normal.png"
            texture_file.write_bytes(b"fake_normal_data")
            _create_textured_stage(stage_path, texture_file, "inputs:normalmap_texture")

            item = RemixAssetItem.from_model(stage_path)
            item.value = stage_path
            step = DiscoverTexturesStep()

            async with RemixAssetPipelineContext(items=[item], source_root=temp_path) as context:
                await step.run(context)

            self.assertEqual(len(item.textures), 1, "Expected exactly one discovered texture")
            self.assertEqual(item.textures[0].texture_type, TextureTypes.NORMAL_DX)

    async def test_discovery_fails_on_unknown_normal_encoding(self):
        """Discovery rejects an authored normal encoding value it does not recognize."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            stage_path = temp_path / "model.usda"
            texture_file = temp_path / "normal.png"
            texture_file.write_bytes(b"fake_normal_data")
            _create_textured_stage(stage_path, texture_file, "inputs:normalmap_texture")
            stage = Usd.Stage.Open(str(stage_path))
            shader_prim = stage.GetPrimAtPath("/Model/Material/Shader")
            encoding_attr = shader_prim.CreateAttribute(MATERIAL_INPUTS_NORMALMAP_ENCODING, Sdf.ValueTypeNames.Int)
            encoding_attr.Set(999)
            stage.GetRootLayer().Save()

            item = RemixAssetItem.from_model(stage_path)
            item.value = stage_path
            step = DiscoverTexturesStep()

            with self.assertRaises(ValueError) as error:
                async with RemixAssetPipelineContext(items=[item], source_root=temp_path) as context:
                    await step.run(context)

            self.assertIn("Unknown normal map encoding", str(error.exception))

    async def test_discovers_every_texture_type_from_the_canonical_input_map(self):
        """A real multi-material project surfaces diffuse, metallic, normal, and roughness types."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            stage_path = pathlib.Path(project_url.path)
            item = RemixAssetItem.from_model(stage_path)
            item.value = stage_path
            step = DiscoverTexturesStep()

            async with RemixAssetPipelineContext(items=[item], source_root=stage_path.parent) as context:
                await step.run(context)

            discovered_types = {texture.texture_type for texture in item.textures}
            self.assertEqual(
                discovered_types,
                {TextureTypes.DIFFUSE, TextureTypes.METALLIC, TextureTypes.NORMAL_DX, TextureTypes.ROUGHNESS},
            )
