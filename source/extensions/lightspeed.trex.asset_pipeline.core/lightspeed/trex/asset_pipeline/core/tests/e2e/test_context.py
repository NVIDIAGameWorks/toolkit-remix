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
import tempfile
from unittest.mock import patch

import omni.kit.app
import omni.kit.test
import omni.usd
from pxr import Usd, UsdGeom, UsdShade, Vt

import lightspeed.trex.asset_pipeline.core.pipeline.context as pipeline_context_module
from lightspeed.trex.asset_pipeline.core import RemixAssetItem, RemixAssetPipelineContext
from lightspeed.trex.asset_pipeline.core.steps import MaterialCleanupStep


_DEFAULT_CONTEXT_MARKER = "/DefaultContextMarker"
_FIRST_MODEL_PRIM = "/World/FirstModel"
_SECOND_MODEL_PRIM = "/World/SecondModel"
_SESSION_ONLY_PROBE = "/SessionOnlyProbe"
_MATERIALLESS_MESH = "/World/MateriallessMesh"
_ORPHAN_MATERIAL = "/World/Looks/OrphanMaterial"
_TRIANGLE_POINTS = Vt.Vec3fArray([(0, 0, 0), (1, 0, 0), (0, 1, 0)])


class TestRemixAssetPipelineContextE2E(omni.kit.test.AsyncTestCase):
    """Drive the real ingestion USD context of a pipeline run against USD files on disk."""

    async def test_open_stage_creates_isolated_ingestion_context(self):
        """The pipeline leaves the app's default context and its stage untouched."""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / "first.usda"
            _author_stage(model_path, _FIRST_MODEL_PRIM)

            default_context = omni.usd.get_context()
            await default_context.new_stage_async()
            default_stage = default_context.get_stage()
            UsdGeom.Xform.Define(default_stage, _DEFAULT_CONTEXT_MARKER)

            try:
                async with RemixAssetPipelineContext() as context:
                    stage = await context.open_stage(model_path)

                    self.assertTrue(stage.GetPrimAtPath(_FIRST_MODEL_PRIM).IsValid())
                    self.assertFalse(stage.GetPrimAtPath(_DEFAULT_CONTEXT_MARKER).IsValid())
                    self.assertEqual(default_context.get_stage(), default_stage)
                    self.assertTrue(default_stage.GetPrimAtPath(_DEFAULT_CONTEXT_MARKER).IsValid())
                    self.assertFalse(default_stage.GetPrimAtPath(_FIRST_MODEL_PRIM).IsValid())
            finally:
                if default_context.can_close_stage():
                    await default_context.close_stage_async()

    async def test_open_stage_with_another_path_replaces_the_open_stage(self):
        """One lease has one stage, so a second path replaces the first stage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            first_path = temp_path / "first.usda"
            second_path = temp_path / "second.usda"
            _author_stage(first_path, _FIRST_MODEL_PRIM)
            _author_stage(second_path, _SECOND_MODEL_PRIM)

            async with RemixAssetPipelineContext() as context:
                first_stage = await context.open_stage(first_path)
                self.assertTrue(first_stage.GetPrimAtPath(_FIRST_MODEL_PRIM).IsValid())

                second_stage = await context.open_stage(second_path)
                self.assertTrue(second_stage.GetPrimAtPath(_SECOND_MODEL_PRIM).IsValid())
                self.assertFalse(second_stage.GetPrimAtPath(_FIRST_MODEL_PRIM).IsValid())

    async def test_open_stage_reuses_cached_ingestion_context(self):
        """The same path keeps its open stage and does not reread the file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / "first.usda"
            _author_stage(model_path, _FIRST_MODEL_PRIM)

            async with RemixAssetPipelineContext() as context:
                first_stage = await context.open_stage(model_path)
                with Usd.EditContext(first_stage, first_stage.GetSessionLayer()):
                    UsdGeom.Xform.Define(first_stage, _SESSION_ONLY_PROBE)

                second_stage = await context.open_stage(model_path)
                self.assertEqual(second_stage, first_stage)
                self.assertTrue(second_stage.GetPrimAtPath(_SESSION_ONLY_PROBE).IsValid())

    async def test_close_stage_keeps_the_ingestion_context_for_the_next_open(self):
        """A step can close a stage and reuse its lease for the next layer open."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            first_path = temp_path / "first.usda"
            second_path = temp_path / "second.usda"
            _author_stage(first_path, _FIRST_MODEL_PRIM)
            _author_stage(second_path, _SECOND_MODEL_PRIM)

            async with RemixAssetPipelineContext() as context:
                await context.open_stage(first_path)
                context_name = context.stage_context_name

                await context.close_stage()

                stage_context = omni.usd.get_context(context_name)
                self.assertIsNotNone(stage_context)
                self.assertIsNone(stage_context.get_stage())

                reopened_stage = await context.open_stage(second_path)
                self.assertTrue(reopened_stage.GetPrimAtPath(_SECOND_MODEL_PRIM).IsValid())

    async def test_scope_exit_leaves_its_context_without_an_open_stage(self):
        """A completed scope leaves no stray stage in the returned lease."""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / "first.usda"
            _author_stage(model_path, _FIRST_MODEL_PRIM)
            context = RemixAssetPipelineContext()

            async with context:
                await context.open_stage(model_path)
                context_name = context.stage_context_name

            stage_context = omni.usd.get_context(context_name)
            self.assertIsNotNone(stage_context)
            self.assertIsNone(stage_context.get_stage())

    async def test_two_live_scopes_lease_different_contexts(self):
        """Two live scopes never share one ingestion context lease."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            first_path = temp_path / "first.usda"
            second_path = temp_path / "second.usda"
            _author_stage(first_path, _FIRST_MODEL_PRIM)
            _author_stage(second_path, _SECOND_MODEL_PRIM)

            first_context = RemixAssetPipelineContext()
            second_context = RemixAssetPipelineContext()
            async with first_context:
                await first_context.open_stage(first_path)
                async with second_context:
                    await second_context.open_stage(second_path)
                    self.assertNotEqual(first_context.stage_context_name, second_context.stage_context_name)
                    self.assertIsNot(first_context._stage_context, second_context._stage_context)

    async def test_sequential_scopes_reuse_a_context_without_prior_stage_or_layer_state(self):
        """A reused lease exposes neither the prior stage nor the prior session layer state."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            first_path = temp_path / "first.usda"
            second_path = temp_path / "second.usda"
            _author_stage(first_path, _FIRST_MODEL_PRIM)
            _author_stage(second_path, _SECOND_MODEL_PRIM)

            first_context = RemixAssetPipelineContext()
            async with first_context:
                first_stage = await first_context.open_stage(first_path)
                context_name = first_context.stage_context_name
                with Usd.EditContext(first_stage, first_stage.GetSessionLayer()):
                    UsdGeom.Xform.Define(first_stage, _SESSION_ONLY_PROBE)

            second_context = RemixAssetPipelineContext()
            async with second_context:
                second_stage = await second_context.open_stage(second_path)
                self.assertEqual(second_context.stage_context_name, context_name)
                self.assertTrue(second_stage.GetPrimAtPath(_SECOND_MODEL_PRIM).IsValid())
                self.assertFalse(second_stage.GetPrimAtPath(_FIRST_MODEL_PRIM).IsValid())
                self.assertFalse(second_stage.GetPrimAtPath(_SESSION_ONLY_PROBE).IsValid())

    async def test_sequential_reuse_does_not_grow_the_free_pool(self):
        """Sequential scopes reuse one lease, so the pool does not grow per processed asset."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            first_path = temp_path / "first.usda"
            second_path = temp_path / "second.usda"
            _author_stage(first_path, _FIRST_MODEL_PRIM)
            _author_stage(second_path, _SECOND_MODEL_PRIM)
            free_count_before = len(pipeline_context_module._INGESTION_CONTEXT_FREE_LIST)

            first_context = RemixAssetPipelineContext()
            async with first_context:
                await first_context.open_stage(first_path)
                context_name = first_context.stage_context_name
            free_count_after_first = len(pipeline_context_module._INGESTION_CONTEXT_FREE_LIST)

            second_context = RemixAssetPipelineContext()
            async with second_context:
                await second_context.open_stage(second_path)
                self.assertEqual(second_context.stage_context_name, context_name)
            free_count_after_second = len(pipeline_context_module._INGESTION_CONTEXT_FREE_LIST)

            self.assertGreaterEqual(free_count_after_first, free_count_before)
            self.assertEqual(free_count_after_second, free_count_after_first)

    async def test_only_outermost_exit_returns_the_lease(self):
        """A nested scope leaves its lease held until the outermost scope exits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / "first.usda"
            _author_stage(model_path, _FIRST_MODEL_PRIM)
            context = RemixAssetPipelineContext()

            async with context:
                stage = await context.open_stage(model_path)
                context_name = context.stage_context_name
                async with context:
                    self.assertEqual(context.stage_context_name, context_name)

                self.assertEqual(omni.usd.get_context(context_name).get_stage(), stage)

            self.assertIsNone(omni.usd.get_context(context_name).get_stage())
            reuser = RemixAssetPipelineContext()
            async with reuser:
                await reuser.open_stage(model_path)
                self.assertEqual(reuser.stage_context_name, context_name)

    async def test_close_failure_returns_the_closed_lease_for_reuse(self):
        """A close error after closure still returns a usable stage-free lease to the pool."""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / "first.usda"
            _author_stage(model_path, _FIRST_MODEL_PRIM)
            context = RemixAssetPipelineContext()
            await context.__aenter__()
            try:
                await context.open_stage(model_path)
                context_name = context.stage_context_name
                original_close = RemixAssetPipelineContext.close_stage

                async def _close_then_raise(closing_context: RemixAssetPipelineContext):
                    await original_close(closing_context)
                    raise RuntimeError("simulated close failure")

                with patch.object(RemixAssetPipelineContext, "close_stage", new=_close_then_raise):
                    with self.assertRaisesRegex(RuntimeError, "simulated close failure"):
                        await context.__aexit__(None, None, None)
            finally:
                if context._scope_depth:
                    await context.__aexit__(None, None, None)

            returned_context = omni.usd.get_context(context_name)
            self.assertIsNotNone(returned_context)
            self.assertIsNone(returned_context.get_stage())
            reuser = RemixAssetPipelineContext()
            async with reuser:
                stage = await reuser.open_stage(model_path)
                self.assertEqual(reuser.stage_context_name, context_name)
                self.assertTrue(stage.GetPrimAtPath(_FIRST_MODEL_PRIM).IsValid())

    async def test_a_lease_whose_stage_fails_to_close_is_reused_and_its_stage_replaced(self):
        """A close error before closure returns the lease; the next open on it replaces the leftover stage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            first_model_path = temp_path / "first.usda"
            second_model_path = temp_path / "second.usda"
            _author_stage(first_model_path, _FIRST_MODEL_PRIM)
            _author_stage(second_model_path, _SECOND_MODEL_PRIM)
            context = RemixAssetPipelineContext()
            await context.__aenter__()
            try:
                await context.open_stage(first_model_path)
                context_name = context.stage_context_name

                async def _raise_before_close(_closing_context: RemixAssetPipelineContext):
                    raise RuntimeError("simulated close failure")

                with patch.object(RemixAssetPipelineContext, "close_stage", new=_raise_before_close):
                    with self.assertRaisesRegex(RuntimeError, "simulated close failure"):
                        await context.__aexit__(None, None, None)
            finally:
                if context._scope_depth:
                    await context.__aexit__(None, None, None)

            self.assertIsNone(context._stage_context)
            self.assertIsNotNone(omni.usd.get_context(context_name).get_stage())

            reuser = RemixAssetPipelineContext()
            async with reuser:
                stage = await reuser.open_stage(second_model_path)
                self.assertEqual(reuser.stage_context_name, context_name)
                self.assertTrue(stage.GetPrimAtPath(_SECOND_MODEL_PRIM).IsValid())
                self.assertFalse(stage.GetPrimAtPath(_FIRST_MODEL_PRIM).IsValid())

            await _pump_kit_updates()

    async def test_reused_context_does_not_apply_a_previous_lease_to_the_next_stage(self):
        """A deferred event from one lease cannot change the next lease's open model."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            mutating_model_path = temp_path / "mutating.usda"
            sentinel_model_path = temp_path / "sentinel.usda"
            _author_cleanup_model(mutating_model_path, include_bound_material=True)
            _author_cleanup_model(sentinel_model_path, include_bound_material=False)

            mutating_item = RemixAssetItem.from_model(mutating_model_path)
            async with RemixAssetPipelineContext(items=[mutating_item], output_dir=temp_path / "processed") as context:
                await MaterialCleanupStep().run(context)
                context_name = context.stage_context_name

            async with RemixAssetPipelineContext() as sentinel_context:
                sentinel_stage = await sentinel_context.open_stage(sentinel_model_path)
                self.assertEqual(sentinel_context.stage_context_name, context_name)
                sentinel_hash = hashlib.sha256(sentinel_model_path.read_bytes()).digest()

                await _pump_kit_updates()

                self.assertEqual(hashlib.sha256(sentinel_model_path.read_bytes()).digest(), sentinel_hash)
                self.assertTrue(sentinel_stage.GetPrimAtPath(_ORPHAN_MATERIAL).IsValid())
                material, _ = UsdShade.MaterialBindingAPI(
                    sentinel_stage.GetPrimAtPath(_MATERIALLESS_MESH)
                ).ComputeBoundMaterial()
                self.assertFalse(material)

    async def test_leaving_the_scope_without_an_open_stage_leaves_the_pool_unchanged(self):
        """A scope that opens no stage leases no context and does not grow the pool."""
        free_count_before = len(pipeline_context_module._INGESTION_CONTEXT_FREE_LIST)
        context = RemixAssetPipelineContext()

        async with context:
            pass

        self.assertEqual(context.stage_context_name, "")
        self.assertEqual(len(pipeline_context_module._INGESTION_CONTEXT_FREE_LIST), free_count_before)

    async def test_open_stage_outside_a_scope_raises_without_leasing_a_context(self):
        """An invalid stage open cannot take a lease that another scope might need."""
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = pathlib.Path(temp_dir) / "first.usda"
            _author_stage(model_path, _FIRST_MODEL_PRIM)
            free_count_before = len(pipeline_context_module._INGESTION_CONTEXT_FREE_LIST)
            context = RemixAssetPipelineContext()

            with self.assertRaises(RuntimeError) as error:
                await context.open_stage(model_path)

            self.assertIn("async with", str(error.exception))
            self.assertEqual(context.stage_context_name, "")
            self.assertEqual(len(pipeline_context_module._INGESTION_CONTEXT_FREE_LIST), free_count_before)


def _author_stage(stage_path: pathlib.Path, prim_path: str) -> None:
    """Author one small USD file on disk and release every handle to it."""
    stage = Usd.Stage.CreateNew(str(stage_path))
    UsdGeom.Xform.Define(stage, prim_path)
    stage.GetRootLayer().Save()


def _author_cleanup_model(model_path: pathlib.Path, *, include_bound_material: bool) -> None:
    """Author cleanup inputs with an orphan material and a materialless mesh."""
    stage = Usd.Stage.CreateNew(str(model_path))
    if include_bound_material:
        bound_material = UsdShade.Material.Define(stage, "/World/Looks/BoundMaterial")
        bound_mesh = UsdGeom.Mesh.Define(stage, "/World/BoundMesh")
        bound_mesh.CreatePointsAttr(_TRIANGLE_POINTS)
        UsdShade.MaterialBindingAPI(bound_mesh.GetPrim()).Bind(bound_material)

    materialless_mesh = UsdGeom.Mesh.Define(stage, _MATERIALLESS_MESH)
    materialless_mesh.CreatePointsAttr(_TRIANGLE_POINTS)
    UsdShade.Material.Define(stage, _ORPHAN_MATERIAL)
    stage.GetRootLayer().Save()


async def _pump_kit_updates() -> None:
    """Process the deferred event after the next lease has opened its sentinel stage."""
    app = omni.kit.app.get_app()
    for _ in range(20):
        await app.next_update_async()
