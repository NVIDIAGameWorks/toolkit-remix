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
import omni.usd
from lightspeed.common.constants import NormalMapEncodings
from lightspeed.trex.asset_pipeline.core import (
    AssetKind,
    RemixAssetItem,
    RemixAssetPipelineContext,
    TextureAsset,
    TextureBinding,
)
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    ProcessedTexture,
    TextureLedgerEntry,
    TextureProcessingResult,
    derive_texture_key,
    resolve_processed_textures,
)
from lightspeed.trex.asset_pipeline.core.steps import ApplyProcessedTexturesStep
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.utils.common.path_utils import get_absolute_path_from_relative, is_udim_texture
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import Sdf, Usd, UsdShade


_PROJECT_STAGE = "usd/project_example/combined.usda"
_RESOURCE_CONTEXT = "asset_pipeline_resource_project"


def _build_minimal_stage(
    stage_path: pathlib.Path,
    texture_inputs: dict[str, str],
    *,
    materials: tuple[str, ...] = ("/Root/Material",),
) -> Usd.Stage:
    """Create a minimal USD stage with materials, shaders, and authored texture inputs.

    Each material gets its own shader at ``<material_path>/Shader``. Every texture input
    in ``texture_inputs`` is authored on every shader. Values are relative asset paths
    resolved against the stage root layer.

    Args:
        stage_path: Where to write the .usda file.
        texture_inputs: Mapping from bare input name (e.g. ``"diffuse_texture"``) to
            relative asset path value (e.g. ``"textures/albedo.png"``).
        materials: Material prim paths to create. Defaults to a single ``/Root/Material``.

    Returns:
        The saved stage, still open.
    """
    stage = Usd.Stage.CreateNew(str(stage_path))
    for material_path in materials:
        material = UsdShade.Material.Define(stage, material_path)
        shader_path = f"{material_path}/Shader"
        shader = UsdShade.Shader.Define(stage, shader_path)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        for input_name, asset_path in texture_inputs.items():
            shader.CreateInput(input_name, Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(asset_path))
    stage.Save()
    return stage


class TestApplyProcessedTexturesE2E(omni.kit.test.AsyncTestCase):
    """Tests for the merged texture resolution, correlation, and application step.

    The step merges what were previously three separate steps into one pass that walks
    model stages directly and writes processed texture paths onto authoring layers.
    """

    async def test_apply_processed_textures_creates_texture_records_and_bindings(self):
        """Texture collection reads shader input names and records typed model bindings."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            project_path = pathlib.Path(project_url.path).parent
            work_dir = project_path / "work"
            work_dir.mkdir()
            output_dir = project_path / "output"
            output_dir.mkdir()

            # Step 1: Use the shared Remix resource project with authored texture overrides.
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path))

            async with RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir) as context:
                # Step 2: Walk shader inputs with an empty processed-texture set.
                await ApplyProcessedTexturesStep({}).run(context)

            # Step 3: Verify texture collection produced typed records from the shared project assets.
            self.assertEqual(len(item.textures), 4)
            self.assertEqual(len(item.texture_bindings), 4)
            self.assertEqual(
                {binding.input_name for binding in item.texture_bindings},
                {
                    "inputs:diffuse_texture",
                    "inputs:metallic_texture",
                    "inputs:normalmap_texture",
                    "inputs:reflectionroughness_texture",
                },
            )
            self.assertTrue(all(texture.path.exists() for texture in item.textures))

    async def test_apply_processed_textures_fails_on_unresolved_texture_path(self):
        """Opaque or missing imported texture references fail instead of silently skipping."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            project_path = pathlib.Path(project_url.path).parent
            work_dir = project_path / "work"
            work_dir.mkdir()
            output_dir = project_path / "output"
            output_dir.mkdir()

            # Step 1: Remove a texture file that the stage references so the walk cannot resolve it.
            (project_path / "sources" / "textures" / "T_MetalPanelWall_HeavyRust_normal.png").unlink()
            item = RemixAssetItem.from_model(pathlib.Path(project_url.path))

            async with RemixAssetPipelineContext(items=[item], work_dir=work_dir, output_dir=output_dir) as context:
                # Step 2: Walking shader inputs should fail clearly.
                with self.assertRaises(FileNotFoundError):
                    await ApplyProcessedTexturesStep({}).run(context)

    async def test_apply_processed_textures_writes_processed_paths(self):
        """Texture application writes processed texture paths back into model bindings."""
        async with open_test_project(_PROJECT_STAGE, context_name=_RESOURCE_CONTEXT) as project_url:
            project_path = pathlib.Path(project_url.path).parent
            processed_path = project_path / "processed" / "metallic.dds"
            processed_path.parent.mkdir()
            work_dir = project_path / "work"
            work_dir.mkdir()

            item = RemixAssetItem.from_model(pathlib.Path(project_url.path))

            async with RemixAssetPipelineContext(
                items=[item], work_dir=work_dir, output_dir=processed_path.parent
            ) as context:
                # Step 1: Find the material prim and its metallic texture input to build the ledger entry.
                stage = await context.open_stage(item.value)
                material_path: str | None = None
                shader_prim_path: Sdf.Path | None = None
                source_path: pathlib.Path | None = None
                for prim in stage.Traverse():
                    if not prim.IsA(UsdShade.Material):
                        continue
                    shader_prim = omni.usd.get_shader_from_material(prim, get_prim=True)
                    if shader_prim is None or not shader_prim.IsValid():
                        continue
                    metallic_attr = shader_prim.GetAttribute("inputs:metallic_texture")
                    if metallic_attr and metallic_attr.HasAuthoredValue():
                        material_path = str(prim.GetPath())
                        shader_prim_path = shader_prim.GetPath()
                        asset = metallic_attr.Get()
                        if isinstance(asset, Sdf.AssetPath) and asset.path:
                            source_path = pathlib.Path(
                                asset.resolvedPath or get_absolute_path_from_relative(asset.path, stage.GetRootLayer())
                            )
                        break
                self.assertIsNotNone(material_path, "Fixture must contain a material with metallic_texture")
                self.assertIsNotNone(source_path, "Metallic texture must resolve to a file")
                self.assertIsNotNone(shader_prim_path)

                texture_key = derive_texture_key(material_path, TextureTypes.METALLIC)

                # Step 2: Run texture application with a ledger entry that points the metallic
                # binding at the processed output.
                processed = ProcessedTexture(
                    key=texture_key,
                    source_path=source_path,
                    asset_url=str(processed_path),
                    texture_type=TextureTypes.METALLIC,
                )
                ledger_entry = TextureLedgerEntry(
                    material_path=material_path,
                    texture_type=TextureTypes.METALLIC,
                    texture_key=texture_key,
                )
                processed_textures = resolve_processed_textures(
                    (ledger_entry,), TextureProcessingResult(items=(processed,))
                )
                step = ApplyProcessedTexturesStep(processed_textures)
                await step.run(context)

                # Step 3: Release the stage so the reopen reads the saved file, not in-memory state,
                # and verify the saved USD shader input now points at the processed texture path in
                # the ``./`` relative form legacy wrote.
                await context.close_stage()
                stage = await context.open_stage(pathlib.Path(project_url.path))
                attr = stage.GetPrimAtPath(shader_prim_path).GetAttribute("inputs:metallic_texture")
                self.assertEqual(attr.Get().path, "./metallic.dds")

    # ------------------------------------------------------------------
    # Run (stage-walking correlation)
    # ------------------------------------------------------------------

    async def test_run_matches_binding_to_processed_texture_by_ledger(self):
        """A stage-authored binding is matched to its processed output through the ledger."""
        with tempfile.TemporaryDirectory() as tmp:
            # Step 1: Author a real model stage on disk that binds one diffuse texture, plus the
            # processed DDS file the ledger will point at.
            tmp_path = pathlib.Path(tmp)
            stage_path = tmp_path / "model.usda"
            tex_path = tmp_path / "textures" / "albedo.png"
            tex_path.parent.mkdir()
            tex_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header so pathlib.Path.exists is True
            output_dir = tmp_path / "output"
            output_dir.mkdir()
            processed_path = output_dir / "albedo.dds"
            processed_path.write_bytes(b"DDS ")

            _build_minimal_stage(stage_path, {"diffuse_texture": "textures/albedo.png"})

            item = RemixAssetItem.from_model(stage_path)

            # Step 2: Build the ledger that ties the material's diffuse slot to the processed file.
            processed = ProcessedTexture(
                key="tex_0",
                source_path=tex_path,
                asset_url=str(processed_path),
                texture_type=TextureTypes.DIFFUSE,
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="tex_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            async with RemixAssetPipelineContext(items=[item], work_dir=tmp_path, output_dir=output_dir) as context:
                # Step 3: Walk the real stage through the pipeline USD context.
                await step.run(context)

            # Step 4: The item records the processed DDS, and the binding points at that record.
            self.assertEqual(len(item.textures), 1)
            self.assertEqual(item.textures[0].path, processed_path)
            self.assertEqual(item.textures[0].texture_type, TextureTypes.DIFFUSE)
            self.assertEqual(len(item.texture_bindings), 1)
            self.assertIs(item.texture_bindings[0].texture, item.textures[0])

    async def test_run_two_bindings_share_one_texture(self):
        """Two bindings whose shaders reference the same source share one TextureAsset."""
        with tempfile.TemporaryDirectory() as tmp:
            # Step 1: Author a real model stage with two materials that bind the same source texture.
            tmp_path = pathlib.Path(tmp)
            stage_path = tmp_path / "model.usda"
            tex_path = tmp_path / "textures" / "shared.png"
            tex_path.parent.mkdir()
            tex_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            output_dir = tmp_path / "output"
            output_dir.mkdir()
            processed_path = output_dir / "shared.dds"
            processed_path.write_bytes(b"DDS ")

            _build_minimal_stage(
                stage_path,
                {"diffuse_texture": "textures/shared.png"},
                materials=("/Root/MaterialA", "/Root/MaterialB"),
            )

            item = RemixAssetItem.from_model(stage_path)

            # Step 2: Give both materials a ledger entry that resolves to the same processed output.
            processed = ProcessedTexture(
                key="tex_0",
                source_path=tex_path,
                asset_url=str(processed_path),
                texture_type=TextureTypes.DIFFUSE,
            )
            ledger_a = TextureLedgerEntry(
                material_path="/Root/MaterialA",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="tex_0",
            )
            ledger_b = TextureLedgerEntry(
                material_path="/Root/MaterialB",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="tex_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_a, ledger_b), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            async with RemixAssetPipelineContext(items=[item], work_dir=tmp_path, output_dir=output_dir) as context:
                # Step 3: Walk the real stage through the pipeline USD context.
                await step.run(context)

            # Step 4: One shared texture record, identity-preserving reference from both bindings.
            self.assertEqual(len(item.textures), 1)
            self.assertEqual(len(item.texture_bindings), 2)
            self.assertIs(item.texture_bindings[0].texture, item.textures[0])
            self.assertIs(item.texture_bindings[1].texture, item.textures[0])

    async def test_run_binding_missing_from_ledger_keeps_resolved_source(self):
        """A binding with no ledger entry keeps the resolved source file as its texture.

        The merged step does resolution and correlation in one pass. When the ledger does not
        cover a binding, the step falls back to the resolved source instead of raising.
        """
        with tempfile.TemporaryDirectory() as tmp:
            # Step 1: Author a real model stage that binds one diffuse texture.
            tmp_path = pathlib.Path(tmp)
            stage_path = tmp_path / "model.usda"
            tex_path = tmp_path / "textures" / "albedo.png"
            tex_path.parent.mkdir()
            tex_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            output_dir = tmp_path / "output"
            output_dir.mkdir()

            _build_minimal_stage(stage_path, {"diffuse_texture": "textures/albedo.png"})

            item = RemixAssetItem.from_model(stage_path)

            # Step 2: Point the ledger at a different material, so the binding's identity is uncovered.
            processed = ProcessedTexture(
                key="tex_0",
                source_path=tex_path,
                asset_url=str(output_dir / "albedo.dds"),
                texture_type=TextureTypes.DIFFUSE,
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/OtherMaterial",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="tex_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            async with RemixAssetPipelineContext(items=[item], work_dir=tmp_path, output_dir=output_dir) as context:
                # Step 3: Walking the real stage must not raise on the uncovered binding.
                await step.run(context)

            # Step 4: The binding keeps the resolved source, not the processed output.
            self.assertEqual(len(item.textures), 1)
            self.assertEqual(item.textures[0].texture_type, TextureTypes.DIFFUSE)
            self.assertEqual(len(item.texture_bindings), 1)
            self.assertIs(item.texture_bindings[0].texture, item.textures[0])

    async def test_run_injects_udim_tiles_from_processed_texture(self):
        """A processed texture carrying UDIM tiles populates the item record with every tile."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            stage_path = tmp_path / "model.usda"
            output_dir = tmp_path / "output"
            output_dir.mkdir()

            # Step 1: Author a real model stage whose shader input holds a <UDIM> token path -- no
            # real file is needed because the guard skips the exists check for token paths.
            _build_minimal_stage(stage_path, {"diffuse_texture": "textures/toto.<UDIM>.png"})

            item = RemixAssetItem.from_model(stage_path)

            # Step 2: Build a ledger whose processed texture carries three concrete tiles.
            processed = ProcessedTexture(
                key="tex_0",
                source_path=tmp_path / "textures" / "toto.1001.png",
                asset_url=str(output_dir / "toto.1001.dds"),
                texture_type=TextureTypes.DIFFUSE,
                udim_tiles=(
                    str(output_dir / "toto.1001.dds"),
                    str(output_dir / "toto.1002.dds"),
                    str(output_dir / "toto.1003.dds"),
                ),
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="tex_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            async with RemixAssetPipelineContext(items=[item], work_dir=tmp_path, output_dir=output_dir) as context:
                # Step 3: Walk the real stage through the pipeline USD context.
                await step.run(context)

            # Step 4: All three tile paths land on the item texture record, first tile leading.
            self.assertEqual(len(item.textures), 1)
            texture = item.textures[0]
            self.assertEqual(len(texture.udim_tiles), 3)
            self.assertEqual(texture.udim_tiles[0], pathlib.Path(output_dir / "toto.1001.dds"))
            self.assertEqual(texture.udim_tiles[1], pathlib.Path(output_dir / "toto.1002.dds"))
            self.assertEqual(texture.udim_tiles[2], pathlib.Path(output_dir / "toto.1003.dds"))
            self.assertEqual(texture.path, texture.udim_tiles[0])

    async def test_run_non_udim_texture_has_empty_udim_tiles(self):
        """A plain texture ends with an empty udim_tiles tuple."""
        with tempfile.TemporaryDirectory() as tmp:
            # Step 1: Author a real model stage that binds one plain, non-tiled diffuse texture.
            tmp_path = pathlib.Path(tmp)
            stage_path = tmp_path / "model.usda"
            tex_path = tmp_path / "textures" / "albedo.png"
            tex_path.parent.mkdir()
            tex_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            output_dir = tmp_path / "output"
            output_dir.mkdir()
            processed_path = output_dir / "albedo.dds"
            processed_path.write_bytes(b"DDS ")

            _build_minimal_stage(stage_path, {"diffuse_texture": "textures/albedo.png"})

            item = RemixAssetItem.from_model(stage_path)

            # Step 2: Declare the processed output with no tiles at all.
            processed = ProcessedTexture(
                key="tex_0",
                source_path=tex_path,
                asset_url=str(processed_path),
                texture_type=TextureTypes.DIFFUSE,
                udim_tiles=(),
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="tex_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            async with RemixAssetPipelineContext(items=[item], work_dir=tmp_path, output_dir=output_dir) as context:
                # Step 3: Walk the real stage through the pipeline USD context.
                await step.run(context)

            # Step 4: The record stays tile-free instead of inventing a single-tile list.
            self.assertEqual(len(item.textures), 1)
            self.assertEqual(item.textures[0].udim_tiles, ())

    async def test_run_udim_token_skips_file_check(self):
        """A shader whose authored asset path contains ``<UDIM>`` does not raise FileNotFoundError.

        The guard at line 211 of the merged step skips the ``resolved_path.exists`` check for
        ``<UDIM>`` token paths because they name a pattern, not a concrete file. The step still
        applies its processed texture.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            stage_path = tmp_path / "model.usda"
            output_dir = tmp_path / "output"
            output_dir.mkdir()
            processed_path = output_dir / "albedo.dds"
            processed_path.write_bytes(b"DDS ")

            # Step 1: Author a real model stage whose shader input holds a <UDIM> token path. No
            # matching file exists, so only the guard can prevent a FileNotFoundError.
            _build_minimal_stage(stage_path, {"diffuse_texture": "textures/toto.<UDIM>.png"})

            item = RemixAssetItem.from_model(stage_path)

            # Step 2: Build the ledger that covers the token binding.
            processed = ProcessedTexture(
                key="tex_0",
                source_path=tmp_path / "textures" / "toto.1001.png",
                asset_url=str(processed_path),
                texture_type=TextureTypes.DIFFUSE,
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="tex_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            async with RemixAssetPipelineContext(items=[item], work_dir=tmp_path, output_dir=output_dir) as context:
                # Step 3: Walking the real stage must not raise FileNotFoundError.
                await step.run(context)

            # Step 4: The processed texture was applied despite the <UDIM> token.
            self.assertEqual(len(item.textures), 1)
            self.assertEqual(item.textures[0].path, processed_path)
            self.assertEqual(item.textures[0].texture_type, TextureTypes.DIFFUSE)
            self.assertIs(item.texture_bindings[0].texture, item.textures[0])

    # ------------------------------------------------------------------
    # UDIM shader attribute rewrite (ledger → token)
    # ------------------------------------------------------------------

    async def test_udim_shader_attribute_receives_token_derived_from_ledger(self):
        """ApplyProcessedTexturesStep derives the <UDIM> token from the first tile and writes it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            # The step skips existence checks for <UDIM> paths; tiles are the concrete files.
            udim_source = temp_path / "toto.<UDIM>.png"
            for name in ("toto.1001.png", "toto.1002.png", "toto.1003.png"):
                (temp_path / name).write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            # Build a stage with a Material wrapping a Shader so the walk finds it.
            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            material = UsdShade.Material.Define(stage, "/Root/Material")
            shader = UsdShade.Shader.Define(stage, "/Root/Material/Shader")
            diffuse_input = shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset)
            diffuse_input.GetAttr().Set(Sdf.AssetPath("toto.<UDIM>.png"))
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "mdl_surface")
            stage.Save()

            # Simulate the DDS tiles that ConvertDDSStep would have produced.
            tile_dir = work_dir / "abc123"
            tile_dir.mkdir(parents=True)
            tile_dds = [
                tile_dir / "toto.1001.a.rtex.dds",
                tile_dir / "toto.1002.a.rtex.dds",
                tile_dir / "toto.1003.a.rtex.dds",
            ]
            for tp in tile_dds:
                tp.write_bytes(b"dds")

            processed = ProcessedTexture(
                key="texture_0",
                source_path=udim_source,
                asset_url=str(tile_dds[0]),
                texture_type=TextureTypes.DIFFUSE,
                udim_tiles=tuple(str(tp) for tp in tile_dds),
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="texture_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            item = RemixAssetItem(
                value=model_path,
                kind=AssetKind.MODEL,
                source_path=model_path,
            )
            async with RemixAssetPipelineContext(
                items=[item], work_dir=work_dir, output_dir=output_dir, source_root=temp_path
            ) as context:
                await step.run(context)

                stage2 = await context.open_stage(model_path)
                attr = stage2.GetPrimAtPath("/Root/Material/Shader").GetAttribute("inputs:diffuse_texture")
                written = attr.Get()
                self.assertTrue(is_udim_texture(written.path))
                self.assertIn(".a.rtex.dds", written.path)

    async def test_udim_shader_attribute_empty_when_replace_flag_true_and_tiles_still_exist(self):
        """replace_udim_textures_by_empty clears the shader attribute; concrete tiles remain."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            udim_source = temp_path / "toto.<UDIM>.png"
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            # Author a model that refers to a tiled diffuse texture.
            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            material = UsdShade.Material.Define(stage, "/Root/Material")
            shader = UsdShade.Shader.Define(stage, "/Root/Material/Shader")
            diffuse_input = shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset)
            diffuse_input.GetAttr().Set(Sdf.AssetPath("toto.<UDIM>.png"))
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "mdl_surface")
            stage.Save()

            tile_dir = work_dir / "abc123"
            tile_dir.mkdir(parents=True)
            tile_dds = [
                tile_dir / "toto.1001.a.rtex.dds",
                tile_dir / "toto.1002.a.rtex.dds",
                tile_dir / "toto.1003.a.rtex.dds",
            ]
            for tp in tile_dds:
                tp.write_bytes(b"dds")

            processed = ProcessedTexture(
                key="texture_0",
                source_path=udim_source,
                asset_url=str(tile_dds[0]),
                texture_type=TextureTypes.DIFFUSE,
                udim_tiles=tuple(str(tp) for tp in tile_dds),
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.DIFFUSE,
                texture_key="texture_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            item = RemixAssetItem(
                value=model_path,
                kind=AssetKind.MODEL,
                source_path=model_path,
            )
            async with RemixAssetPipelineContext(
                items=[item],
                work_dir=work_dir,
                output_dir=output_dir,
                source_root=temp_path,
                replace_udim_textures_by_empty=True,
            ) as context:
                # Apply the processed tiles with empty shader paths enabled.
                await step.run(context)

                # Verify that the shader path is empty and the tile files remain.
                stage2 = await context.open_stage(model_path)
                attr = stage2.GetPrimAtPath("/Root/Material/Shader").GetAttribute("inputs:diffuse_texture")
                written = attr.Get()
                self.assertEqual(written.path, "")
                for tp in tile_dds:
                    self.assertTrue(tp.exists())

    # ------------------------------------------------------------------
    # Encoding attribute authoring (ledger-aware)
    # ------------------------------------------------------------------

    async def test_authors_encoding_attr_after_normal_conversion(self):
        """ApplyProcessedTexturesStep writes inputs:encoding = 0 when the processed texture is NORMAL_OTH."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            source_path = temp_path / "normal.png"
            source_path.write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            material = UsdShade.Material.Define(stage, "/Root/Material")
            shader = UsdShade.Shader.Define(stage, "/Root/Material/Shader")
            normal_input = shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset)
            normal_input.GetAttr().Set(Sdf.AssetPath("normal.png"))
            encoding_input = shader.CreateInput("encoding", Sdf.ValueTypeNames.Int)
            encoding_input.GetAttr().Set(1)  # TANGENT_SPACE_OGL — not octahedral
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "mdl_surface")
            stage.Save()

            processed = ProcessedTexture(
                key="texture_0",
                source_path=source_path,
                asset_url=str(source_path),
                texture_type=TextureTypes.NORMAL_OTH,
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.NORMAL_OGL,
                texture_key="texture_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            # Pre-populate bindings so the step applies without walking the stage.
            texture_asset = TextureAsset(
                path=source_path,
                texture_type=TextureTypes.NORMAL_OGL,
                original_path=source_path,
            )
            item = RemixAssetItem(
                value=model_path,
                kind=AssetKind.MODEL,
                source_path=model_path,
                textures=[texture_asset],
                texture_bindings=[
                    TextureBinding(
                        shader_path=Sdf.Path("/Root/Material/Shader"),
                        input_name="inputs:normalmap_texture",
                        original_asset_path=Sdf.AssetPath("normal.png"),
                        texture=texture_asset,
                        material_path="/Root/Material",
                    )
                ],
            )
            async with RemixAssetPipelineContext(
                items=[item], work_dir=work_dir, output_dir=output_dir, source_root=temp_path
            ) as context:
                await step.run(context)

                stage2 = await context.open_stage(model_path)
                encoding_attr = stage2.GetPrimAtPath("/Root/Material/Shader").GetAttribute("inputs:encoding")
                self.assertEqual(encoding_attr.Get(), NormalMapEncodings.OCTAHEDRAL.value)

    async def test_udim_shader_normal_attribute_receives_token_from_ledger(self):
        """ApplyProcessedTexturesStep derives the <UDIM> token from the first tile and writes it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            udim_source = temp_path / "toto.<UDIM>.png"
            for name in ("toto.1001.png", "toto.1002.png", "toto.1003.png"):
                (temp_path / name).write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            material = UsdShade.Material.Define(stage, "/Root/Material")
            shader = UsdShade.Shader.Define(stage, "/Root/Material/Shader")
            normal_input = shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset)
            normal_input.GetAttr().Set(Sdf.AssetPath("toto.<UDIM>.png"))
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "mdl_surface")
            stage.Save()

            # Simulate the tiles that ConvertNormalStep would have produced.
            tile_dir = work_dir / "abc123"
            tile_dir.mkdir(parents=True)
            tile_paths = [
                tile_dir / "toto.1001_OTH_Normal.png",
                tile_dir / "toto.1002_OTH_Normal.png",
                tile_dir / "toto.1003_OTH_Normal.png",
            ]
            for tp in tile_paths:
                tp.write_bytes(b"png")

            processed = ProcessedTexture(
                key="texture_0",
                source_path=udim_source,
                asset_url=str(tile_paths[0]),
                texture_type=TextureTypes.NORMAL_OTH,
                udim_tiles=tuple(str(tp) for tp in tile_paths),
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.NORMAL_DX,
                texture_key="texture_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            # Pre-populate bindings so the step applies without walking the stage.
            texture_asset = TextureAsset(
                path=tile_paths[0],
                texture_type=TextureTypes.NORMAL_DX,
                original_path=udim_source,
            )
            item = RemixAssetItem(
                value=model_path,
                kind=AssetKind.MODEL,
                source_path=model_path,
                textures=[texture_asset],
                texture_bindings=[
                    TextureBinding(
                        shader_path=Sdf.Path("/Root/Material/Shader"),
                        input_name="inputs:normalmap_texture",
                        original_asset_path=Sdf.AssetPath("toto.<UDIM>.png"),
                        texture=texture_asset,
                        material_path="/Root/Material",
                    )
                ],
            )
            async with RemixAssetPipelineContext(
                items=[item], work_dir=work_dir, output_dir=output_dir, source_root=temp_path
            ) as context:
                await step.run(context)

            self.assertEqual(len(item.textures), 1)
            self.assertEqual(len(item.textures[0].udim_tiles), 3)
            self.assertIn("_OTH_Normal", str(item.textures[0].path))

    async def test_udim_shader_normal_attribute_empty_when_replace_flag_true_and_tiles_exist(self):
        """replace_udim_textures_by_empty clears the normal attribute; tiles still exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            udim_source = temp_path / "toto.<UDIM>.png"
            for name in ("toto.1001.png", "toto.1002.png", "toto.1003.png"):
                (temp_path / name).write_bytes(b"png")
            output_dir = temp_path / "processed"
            output_dir.mkdir()
            work_dir = temp_path / "work"
            work_dir.mkdir()

            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            material = UsdShade.Material.Define(stage, "/Root/Material")
            shader = UsdShade.Shader.Define(stage, "/Root/Material/Shader")
            normal_input = shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset)
            normal_input.GetAttr().Set(Sdf.AssetPath("toto.<UDIM>.png"))
            encoding_input = shader.CreateInput("encoding", Sdf.ValueTypeNames.Int)
            encoding_input.GetAttr().Set(0)  # OCTAHEDRAL
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "mdl_surface")
            stage.Save()

            tile_dir = work_dir / "abc123"
            tile_dir.mkdir(parents=True)
            tile_paths = [
                tile_dir / "toto.1001_OTH_Normal.png",
                tile_dir / "toto.1002_OTH_Normal.png",
                tile_dir / "toto.1003_OTH_Normal.png",
            ]
            for tp in tile_paths:
                tp.write_bytes(b"png")

            processed = ProcessedTexture(
                key="texture_0",
                source_path=udim_source,
                asset_url=str(tile_paths[0]),
                texture_type=TextureTypes.NORMAL_OTH,
                udim_tiles=tuple(str(tp) for tp in tile_paths),
            )
            ledger_entry = TextureLedgerEntry(
                material_path="/Root/Material",
                texture_type=TextureTypes.NORMAL_OTH,
                texture_key="texture_0",
            )
            processed_textures = resolve_processed_textures(
                (ledger_entry,), TextureProcessingResult(items=(processed,))
            )
            step = ApplyProcessedTexturesStep(processed_textures)

            # Pre-populate bindings so the step applies without walking the stage.
            texture_asset = TextureAsset(
                path=tile_paths[0],
                texture_type=TextureTypes.NORMAL_OTH,
                original_path=udim_source,
            )
            item = RemixAssetItem(
                value=model_path,
                kind=AssetKind.MODEL,
                source_path=model_path,
                textures=[texture_asset],
                texture_bindings=[
                    TextureBinding(
                        shader_path=Sdf.Path("/Root/Material/Shader"),
                        input_name="inputs:normalmap_texture",
                        original_asset_path=Sdf.AssetPath("toto.<UDIM>.png"),
                        texture=texture_asset,
                        material_path="/Root/Material",
                    )
                ],
            )
            async with RemixAssetPipelineContext(
                items=[item],
                work_dir=work_dir,
                output_dir=output_dir,
                source_root=temp_path,
                replace_udim_textures_by_empty=True,
            ) as context:
                await step.run(context)

                stage2 = await context.open_stage(model_path)
                attr = stage2.GetPrimAtPath("/Root/Material/Shader").GetAttribute("inputs:normalmap_texture")
                written = attr.Get()
                self.assertEqual(written.path, "")
                for tp in tile_paths:
                    self.assertTrue(tp.exists())
