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
import shutil
import tempfile

import omni.kit.test
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.jobs import build_asset_optimization_graph
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_handler import AssetReplaceApplyHandler
from lightspeed.trex.asset_pipeline.core.jobs.asset_replace_apply_target import AssetReplaceApplyTarget
from lightspeed.trex.asset_pipeline.core.jobs.models import MeshOptimizationRequest, ReferenceTarget
from lightspeed.trex.asset_pipeline.core.jobs.reference_apply import (
    reference_state,
    revert_references,
)
from lightspeed.trex.asset_pipeline.core.steps import ReferenceStep
from lightspeed.trex.asset_pipeline.core.tests.e2e.test_job import _run_until_outputs
from lightspeed.trex.asset_replacements.core.shared import Setup
from omni.flux.job_queue.core import handlers
from omni.flux.job_queue.core.apply_executor import ApplyExecutor
from omni.flux.job_queue.core.enums import ApplyDisposition, ApplyOperation
from omni.flux.job_queue.core.errors import ApplyExecutionError
from omni.flux.job_queue.core.interface import QueueInterface
from pxr import Sdf, Usd, UsdGeom


class TestReferenceE2E(omni.kit.test.AsyncTestCase):
    async def test_generated_markers_revert_after_relocation_and_accept_legacy_paths(self):
        """Restore both reference-owner forms from saved jobs, legacy markers, and relocated projects."""
        # Create source and generated assets with both owner forms to exercise both reference restoration paths.
        context = omni.usd.get_context()
        setup = Setup("")
        self.addCleanup(setup.destroy)
        with tempfile.TemporaryDirectory() as directory:
            project_directory = pathlib.Path(directory) / "project"
            (project_directory / "layers").mkdir(parents=True)
            for name in ("source", "generated"):
                asset = Usd.Stage.CreateNew(str(project_directory / f"{name}.usda"))
                asset.SetDefaultPrim(UsdGeom.Xform.Define(asset, "/Asset").GetPrim())
                UsdGeom.Xform.Define(asset, f"/Asset/{name}")
                asset.GetRootLayer().Save()
            edit = Usd.Stage.CreateNew(str(project_directory / "layers/mod.usda"))
            layer = edit.GetRootLayer()
            owners = (
                f"{constants.ROOTNODE_MESHES}/mesh_0123456789ABCDEF",
                f"{constants.ROOTNODE_MESHES}/mesh_0123456789ABCDE0/ref_source",
            )
            for in_place, path in enumerate(owners):
                owner = UsdGeom.Xform.Define(edit, path).GetPrim()
                owner.GetReferences().AddReference("../source.usda")
                if in_place:
                    owner.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
            layer.Save()
            project = Usd.Stage.CreateNew(str(project_directory / "project.usda"))
            project.GetRootLayer().subLayerPaths = ["layers/mod.usda"]
            project.GetRootLayer().Save()
            executor = None
            try:
                # Open the project and process its generated asset so Apply can replace both original references.
                await context.open_stage_async(str(project_directory / "project.usda"))
                stage = context.get_stage()
                targets = tuple(
                    ReferenceTarget(path, Sdf.Reference("../source.usda"), layer.identifier) for path in owners
                )
                target = AssetReplaceApplyTarget("", stage.GetRootLayer().identifier, layer.identifier, targets)
                graph, job = build_asset_optimization_graph(
                    MeshOptimizationRequest(
                        project_directory / "generated.usda",
                        project_directory,
                        output_url=(project_directory / "processed").as_posix(),
                    ),
                    handler_type=AssetReplaceApplyHandler,
                    target=target,
                )
                interface = QueueInterface(str(pathlib.Path(directory) / "queue.sqlite"))
                jobs = {item.job_id: item for item in interface.submit(graph)}
                output = (await _run_until_outputs(jobs[job.job_id], interface))[job.OPTIMIZED_MESH].asset_url
                executor = ApplyExecutor(interface, handlers.get_registry())
                for relocated in (False, True):
                    with self.subTest(relocated=relocated):
                        # Apply the output and expect markers relative to the layer that owns each reference.
                        await executor.apply(job.job_id)
                        for path in owners:
                            marker = next(
                                attribute
                                for prim in Usd.PrimRange(stage.GetPrimAtPath(path))
                                for attribute in prim.GetAttributes()
                                if attribute.GetName().startswith("remix_generated_for")
                            )
                            self.assertEqual(
                                marker.Get(),
                                f"{path} ../{pathlib.Path(output).relative_to(project_directory).as_posix()}",
                            )
                            if not relocated:
                                # Write the legacy absolute marker so the saved job must restore that form.
                                with Usd.EditContext(stage, layer):
                                    marker.Set(f"{path} {output}")
                        # Save the markers and reload the queue so the restored job retains its original Apply target.
                        layer.Save()
                        await executor.shutdown()
                        restored = QueueInterface(interface.db_path)
                        self.assertEqual(restored.get_job(job.job_id).apply_binding.target, target)
                        executor = ApplyExecutor(restored, handlers.get_registry())
                        if relocated:
                            # Move the project and expect queued Revert to reject its different project identity.
                            await context.close_stage_async()
                            moved = pathlib.Path(directory) / "moved"
                            shutil.move(str(project_directory), str(moved))
                            await context.open_stage_async(str(moved / "project.usda"))
                            with self.assertRaisesRegex(ApplyExecutionError, "different project"):
                                await executor.revert(job.job_id)
                            self.assertIn(
                                "different project",
                                executor.get_apply_block_reason(job.job_id, ApplyOperation.REVERTING),
                            )
                            # Resolve relative markers at the new location so direct restoration finds both owners.
                            stage = context.get_stage()
                            layer = Sdf.Layer.FindOrOpen(str(moved / "layers/mod.usda"))
                            output = (moved / pathlib.Path(output).relative_to(project_directory)).as_posix()
                            targets = tuple(
                                ReferenceTarget(path, Sdf.Reference("../source.usda"), layer.identifier)
                                for path in owners
                            )
                            state, children = reference_state(stage, targets, output, replace=True)
                            self.assertEqual(state, "applied")
                            with Usd.EditContext(stage, layer), omni.kit.undo.group():
                                revert_references(
                                    stage, setup, layer, targets, output, children, context_name="", replace=True
                                )
                        else:
                            # Revert the saved job and expect its legacy markers to restore both original references.
                            await executor.revert(job.job_id)
                            self.assertIs(
                                restored.get_job_snapshot(job.job_id).apply_disposition, ApplyDisposition.DECLINED
                            )
                        # Expect both restoration paths to remove the generated asset and restore every source.
                        self.assertEqual(reference_state(stage, targets, output, replace=True)[0], "original")
                        self.assertEqual(sum(prim.GetName() == "source" for prim in stage.Traverse()), len(owners))
            finally:
                # Release the executor and stage before temporary project files are removed.
                if executor is not None:
                    await executor.shutdown()
                await context.close_stage_async()

    async def test_run_makes_asset_paths_and_references_relative(self):
        """The reference step rewrites absolute asset-path attributes and reference arcs to relative paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)

            # Step 1: Author a referenced USD file on disk that the model stage will reference by
            # absolute path.
            ref_path = temp_path / "referenced.usda"
            ref_stage = Usd.Stage.CreateNew(str(ref_path))
            ref_world = UsdGeom.Xform.Define(ref_stage, "/World")
            ref_stage.SetDefaultPrim(ref_world.GetPrim())
            ref_stage.GetRootLayer().Save()

            # Step 2: Author the model stage with an absolute asset-path attribute and an absolute
            # reference arc, which is what a freshly imported asset looks like.
            texture_path = temp_path / "textures" / "texture.png"
            texture_path.parent.mkdir()
            texture_path.write_bytes(b"")
            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            world = UsdGeom.Xform.Define(stage, "/World")
            world.GetPrim().GetReferences().AddReference(str(ref_path))
            texture_attr = world.GetPrim().CreateAttribute("diffuse_texture", Sdf.ValueTypeNames.Asset)
            texture_attr.Set(Sdf.AssetPath(texture_path.as_posix()))
            stage.GetRootLayer().Save()

            item = RemixAssetItem.from_model(model_path)

            async with RemixAssetPipelineContext(items=[item]) as context:
                # Step 3: Run the reference step against the real stage, then release it so the
                # reopen below reads the saved file instead of in-memory state.
                await ReferenceStep().run(context)
                await context.close_stage()

                # Step 4: The asset-path attribute is now relative to the stage root layer.
                reopened = Usd.Stage.Open(str(model_path))
                world_prim = reopened.GetPrimAtPath("/World")
                relative_texture_path = world_prim.GetAttribute("diffuse_texture").Get().path
                self.assertFalse(pathlib.Path(relative_texture_path).is_absolute(), relative_texture_path)

                # Step 5: The reference arc's asset path is now relative too.
                refs_and_layers = omni.usd.get_composed_references_from_prim(world_prim)
                self.assertTrue(refs_and_layers)
                for ref, _ in refs_and_layers:
                    self.assertFalse(pathlib.Path(ref.assetPath).is_absolute(), ref.assetPath)

    async def test_run_preserves_current_and_weaker_layer_references(self):
        """Both references and their contents survive when a weaker absolute reference becomes relative."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            for name in ("current", "weaker"):
                ref_stage = Usd.Stage.CreateNew(str(temp_path / f"{name}.usda"))
                asset = UsdGeom.Xform.Define(ref_stage, "/Asset")
                ref_stage.SetDefaultPrim(asset.GetPrim())
                UsdGeom.Xform.Define(ref_stage, f"/Asset/{name}")
                ref_stage.GetRootLayer().Save()

            sublayer_path = temp_path / "sublayer.usda"
            sublayer_stage = Usd.Stage.CreateNew(str(sublayer_path))
            weaker_prim = UsdGeom.Xform.Define(sublayer_stage, "/World").GetPrim()
            weaker_prim.GetReferences().AddReference((temp_path / "weaker.usda").as_posix())
            sublayer_stage.GetRootLayer().Save()

            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            world = UsdGeom.Xform.Define(stage, "/World").GetPrim()
            world.GetReferences().AddReference("./current.usda")
            stage.GetRootLayer().subLayerPaths.append(sublayer_path.name)
            stage.GetRootLayer().Save()
            self.assertEqual({child.GetName() for child in world.GetChildren()}, {"current", "weaker"})
            world = None
            stage = None

            async with RemixAssetPipelineContext(items=[RemixAssetItem.from_model(model_path)]) as context:
                await ReferenceStep().run(context)
                await context.close_stage()

            reopened = Usd.Stage.Open(str(model_path))
            world = reopened.GetPrimAtPath("/World")
            refs_and_layers = omni.usd.get_composed_references_from_prim(world)
            self.assertEqual(
                {
                    pathlib.Path(Sdf.ComputeAssetPathRelativeToLayer(layer, ref.assetPath)).resolve()
                    for ref, layer in refs_and_layers
                },
                {(temp_path / "current.usda").resolve(), (temp_path / "weaker.usda").resolve()},
            )
            self.assertEqual({child.GetName() for child in world.GetChildren()}, {"current", "weaker"})
            for ref, _ in refs_and_layers:
                self.assertFalse(pathlib.Path(ref.assetPath).is_absolute(), ref.assetPath)

    async def test_run_makes_child_layer_asset_path_relative_to_owning_layer(self):
        """The reference step resolves an asset path against its own authoring layer, not the stage root."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)

            # Step 1: Write a real texture file that the child layer's absolute attribute points to.
            texture_path = temp_path / "textures" / "texture.png"
            texture_path.parent.mkdir()
            texture_path.write_bytes(b"")

            # Step 2: Author a child USD nested under SubUSDs/ that carries the absolute asset-path
            # attribute, so the fix must resolve against the child layer rather than the root.
            sub_usds_dir = temp_path / "SubUSDs"
            sub_usds_dir.mkdir()
            child_path = sub_usds_dir / "child.usda"
            child_stage = Usd.Stage.CreateNew(str(child_path))
            child_world = UsdGeom.Xform.Define(child_stage, "/World")
            child_stage.SetDefaultPrim(child_world.GetPrim())
            texture_attr = child_world.GetPrim().CreateAttribute("diffuse_texture", Sdf.ValueTypeNames.Asset)
            texture_attr.Set(Sdf.AssetPath(texture_path.as_posix()))
            child_stage.GetRootLayer().Save()

            # Step 3: Author the parent model, which already references the child by a path relative
            # to the parent.
            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            world = UsdGeom.Xform.Define(stage, "/World")
            world.GetPrim().GetReferences().AddReference("./SubUSDs/child.usda")
            stage.GetRootLayer().Save()

            item = RemixAssetItem.from_model(model_path)

            async with RemixAssetPipelineContext(items=[item]) as context:
                # Step 4: Run the reference step, then release the stage so the reopen reads disk.
                await ReferenceStep().run(context)
                await context.close_stage()

                # Step 5: The child layer's own attribute is now relative, not relative to the
                # stage root.
                reopened_child = Usd.Stage.Open(str(child_path))
                child_world_prim = reopened_child.GetPrimAtPath("/World")
                relative_texture_path = child_world_prim.GetAttribute("diffuse_texture").Get().path
                self.assertFalse(pathlib.Path(relative_texture_path).is_absolute(), relative_texture_path)

                # Step 6: The relative path resolves correctly from the child layer's own directory.
                resolved_from_child = (sub_usds_dir / relative_texture_path).resolve()
                self.assertEqual(resolved_from_child, texture_path.resolve())

    async def test_run_raises_on_unfixable_paths(self):
        """The reference step raises when an absolute path cannot be made relative to its layer."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)

            # Step 1: Author an asset-path attribute pointing off the model's own root -- make_relative_url
            # cannot express a UNC host as relative to a local layer identifier, so this is a no-op.
            unc_texture_path = "//unreachable-host/share/texture.png"
            model_path = temp_path / "model.usda"
            stage = Usd.Stage.CreateNew(str(model_path))
            world = UsdGeom.Xform.Define(stage, "/World")
            texture_attr = world.GetPrim().CreateAttribute("diffuse_texture", Sdf.ValueTypeNames.Asset)
            texture_attr.Set(Sdf.AssetPath(unc_texture_path))
            UsdGeom.Xform.Define(stage, "/World/Child")
            stage.GetRootLayer().Save()

            # Step 2: Author a referenced USD file for the session-layer reference arc below.
            ref_path = temp_path / "referenced.usda"
            ref_stage = Usd.Stage.CreateNew(str(ref_path))
            ref_world = UsdGeom.Xform.Define(ref_stage, "/World")
            ref_stage.SetDefaultPrim(ref_world.GetPrim())
            ref_stage.GetRootLayer().Save()

            item = RemixAssetItem.from_model(model_path)

            async with RemixAssetPipelineContext(items=[item]) as context:
                # Step 3: Author the reference arc in the session layer of the pipeline's own cached
                # stage, so ReferenceStep's later `context.open_stage` reuses it instead of a fresh
                # session layer -- the edit target (root layer) can never be stronger than this arc.
                pipeline_stage = await context.open_stage(model_path)
                child_prim = pipeline_stage.GetPrimAtPath("/World/Child")
                with Usd.EditContext(pipeline_stage, pipeline_stage.GetSessionLayer()):
                    child_prim.GetReferences().AddReference(str(ref_path))

                # Step 4: Running the step must fail loudly and name both unfixable locations.
                with self.assertRaises(RuntimeError) as ctx:
                    await ReferenceStep().run(context)
                message = str(ctx.exception)
                self.assertIn("/World.diffuse_texture", message)
                self.assertIn("/World/Child", message)
