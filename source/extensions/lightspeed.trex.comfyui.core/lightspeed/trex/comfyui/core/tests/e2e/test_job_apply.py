"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import dataclasses
import pathlib
import tempfile
from unittest.mock import patch

import omni.usd
from lightspeed.trex.asset_pipeline.core.models import ProcessedTexture, TextureProcessingResult
from lightspeed.trex.comfyui.core.apply_handler import ComfyUIJobApplyHandler
from lightspeed.trex.comfyui.core.models import ComfyUIApplyTarget
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.errors import ApplyExecutionError
from omni.kit import undo
from omni.kit.test import AsyncTestCase
from pxr import Sdf, UsdShade


class TestComfyUIJobApplyE2E(AsyncTestCase):
    """Exercise durable ComfyUI Apply semantics against real local USD layers."""

    async def setUp(self) -> None:
        """Open a saved default-context stage with distinct target and stronger local layers."""
        self._context = omni.usd.get_context("")
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="comfyui-apply-")
        temp_path = pathlib.Path(self._temp_dir.name)
        root_layer = Sdf.Layer.CreateNew(str(temp_path / "project.usda"))
        target_layer = Sdf.Layer.CreateNew(str(temp_path / "target.usda"))
        stronger_layer = Sdf.Layer.CreateNew(str(temp_path / "stronger.usda"))
        root_layer.subLayerPaths = [stronger_layer.identifier, target_layer.identifier]
        root_layer.Save()
        await self._context.open_stage_async(root_layer.identifier)

        self._stage = self._context.get_stage()
        self._target_layer = next(
            layer for layer in self._stage.GetLayerStack(False) if layer.identifier == target_layer.identifier
        )
        self._stronger_layer = next(
            layer for layer in self._stage.GetLayerStack(False) if layer.identifier == stronger_layer.identifier
        )
        self._albedo_path = "/World/Looks/Material/Shader.inputs:diffuse_texture"
        self._normal_path = "/World/Looks/Material/Shader.inputs:normalmap_texture"
        self._stage.SetEditTarget(self._target_layer)
        shader = UsdShade.Shader.Define(self._stage, "/World/Looks/Material/Shader")
        shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath("textures/original-albedo.dds")
        )
        shader.CreateInput("normalmap_texture", Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath("textures/original-normal.dds")
        )
        self._target_layer.Save()
        self._stage.SetEditTarget(self._stronger_layer)
        undo.clear_stack()
        self._ingested_patch = patch(
            "lightspeed.trex.texture_replacements.core.shared.data_models.validators.is_asset_ingested",
            return_value=True,
        )
        self._ingested_patch.start()

    async def tearDown(self) -> None:
        """Close the stage and release the temporary saved layers."""
        self._ingested_patch.stop()
        undo.clear_stack()
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        self._temp_dir.cleanup()

    def _target(self, texture_targets: tuple[tuple[str, str], ...]) -> ComfyUIApplyTarget:
        """Create an Apply target for the saved default-context project.

        Args:
            texture_targets: Workflow keys paired with shader input paths.

        Returns:
            Exact persisted Apply target.
        """
        return ComfyUIApplyTarget(
            context_name="",
            project_path=str(self._stage.GetRootLayer().identifier),
            edit_target_layer=str(self._target_layer.identifier),
            material_path="/World/Looks/Material",
            texture_targets=texture_targets,
        )

    def _result(self, entries: tuple[tuple[str, str, TextureTypes], ...]) -> TextureProcessingResult:
        """Build processed textures in the requested result order.

        Args:
            entries: Stable keys, asset URLs, and exact texture semantics.

        Returns:
            Typed processed-textures result.
        """
        for _, asset_url, _ in entries:
            pathlib.Path(asset_url).touch()
        return TextureProcessingResult(
            items=tuple(
                ProcessedTexture(
                    key=key,
                    source_path=pathlib.Path(self._temp_dir.name) / f"{key}.png",
                    asset_url=asset_url,
                    texture_type=texture_type,
                )
                for key, asset_url, texture_type in entries
            )
        )

    async def test_apply_uses_saved_layer_from_default_context(self):
        """Receipt capture is non-mutating and Apply authors only the saved layer."""
        target = self._target((("albedo", self._albedo_path),))
        applied_url = str(pathlib.Path(self._temp_dir.name) / "processed-albedo.dds")
        value = self._result((("albedo", applied_url, TextureTypes.DIFFUSE),))
        expected_original = Sdf.ComputeAssetPathRelativeToLayer(
            self._target_layer,
            "textures/original-albedo.dds",
        )

        handler = ComfyUIJobApplyHandler()
        original_layer = self._target_layer.ExportToString()

        # Capture the baseline without authoring, then apply the processed texture through the real USD command.
        receipt = await handler.capture_receipt(value, target)
        layer_after_capture = self._target_layer.ExportToString()
        result = await handler.apply(value, target, receipt)

        # Receipt capture is inert and Apply writes only the persisted target layer, preserving the active edit target.
        self.assertEqual(layer_after_capture, original_layer)
        self.assertIsNone(result)
        self.assertEqual(
            receipt.original_authored_values,
            ((self._albedo_path, "textures/original-albedo.dds"),),
        )
        self.assertEqual(receipt.original_compare_values, ((self._albedo_path, expected_original),))
        self.assertIs(self._stage.GetEditTarget().GetLayer(), self._stronger_layer)
        self.assertEqual(
            self._target_layer.GetAttributeAtPath(self._albedo_path).default.path,
            "./processed-albedo.dds",
        )

    async def test_apply_retry_after_interrupted_completion_is_idempotent(self):
        """A retry after mutation does not add a second undoable replacement command."""
        target = self._target((("albedo", self._albedo_path),))
        applied_url = str(pathlib.Path(self._temp_dir.name) / "processed-albedo.dds")
        value = self._result((("albedo", applied_url, TextureTypes.DIFFUSE),))
        handler = ComfyUIJobApplyHandler()
        receipt = await handler.capture_receipt(value, target)

        # Apply once, then repeat the exact request as recovery from an interrupted completion acknowledgement.
        await handler.apply(value, target, receipt)

        retry_result = await handler.apply(value, target, receipt)
        undo_succeeded = undo.undo()

        # The retry is idempotent: one undo restores the original authored texture.
        self.assertIsNone(retry_result)
        self.assertTrue(undo_succeeded)
        self.assertEqual(
            self._target_layer.GetAttributeAtPath(self._albedo_path).default.path,
            "textures/original-albedo.dds",
        )

    async def test_revert_restores_missing_original_on_saved_layer(self):
        """Revert restores the receipt-recorded original even when its source file is unavailable."""
        target = self._target((("albedo", self._albedo_path),))
        applied_url = str(pathlib.Path(self._temp_dir.name) / "processed-albedo.dds")
        value = self._result((("albedo", applied_url, TextureTypes.DIFFUSE),))
        handler = ComfyUIJobApplyHandler()
        receipt = await handler.capture_receipt(value, target)

        # Apply even though the receipt's original relative asset does not exist on disk.
        await handler.apply(value, target, receipt)
        self.assertFalse((pathlib.Path(self._target_layer.realPath).parent / "textures/original-albedo.dds").exists())

        # Revert uses the durable receipt, not filesystem existence, to restore the original authored value.
        await ComfyUIJobApplyHandler().revert(value, target, receipt)

        self.assertIs(self._stage.GetEditTarget().GetLayer(), self._stronger_layer)
        self.assertEqual(
            self._target_layer.GetAttributeAtPath(self._albedo_path).default.path,
            "textures/original-albedo.dds",
        )

    async def test_reapply_detects_target_layer_edit_hidden_by_stronger_opinion(self):
        """A stronger composed value cannot hide an external edit on the persisted target layer."""
        target = self._target((("albedo", self._albedo_path),))
        applied_url = str(pathlib.Path(self._temp_dir.name) / "processed-albedo.dds")
        value = self._result((("albedo", applied_url, TextureTypes.DIFFUSE),))
        handler = ComfyUIJobApplyHandler()
        receipt = await handler.capture_receipt(value, target)
        await handler.apply(value, target, receipt)

        # Hide an external target-layer edit beneath an unchanged stronger composed opinion.
        self._stage.SetEditTarget(self._stronger_layer)
        self._stage.GetAttributeAtPath(self._albedo_path).Set(Sdf.AssetPath(applied_url))
        self._stage.SetEditTarget(self._target_layer)
        self._stage.GetAttributeAtPath(self._albedo_path).Set(Sdf.AssetPath("textures/external.dds"))
        self._stage.SetEditTarget(self._stronger_layer)

        # Reapply inspects the owning layer directly and rejects the hidden conflict without overwriting it.
        self.assertEqual(self._stage.GetAttributeAtPath(self._albedo_path).Get().path, applied_url)
        with self.assertRaises(ApplyExecutionError) as error_context:
            await handler.apply(value, target, receipt)
        self.assertIn("changed outside", error_context.exception.reason)
        self.assertEqual(
            self._target_layer.GetAttributeAtPath(self._albedo_path).default.path,
            "textures/external.dds",
        )

    async def test_revert_rejects_target_layer_edit_without_changing_stage(self):
        """Revert leaves an externally edited target layer and the current edit target unchanged."""
        target = self._target((("albedo", self._albedo_path),))
        applied_url = str(pathlib.Path(self._temp_dir.name) / "processed-albedo.dds")
        value = self._result((("albedo", applied_url, TextureTypes.DIFFUSE),))
        handler = ComfyUIJobApplyHandler()
        receipt = await handler.capture_receipt(value, target)
        await handler.apply(value, target, receipt)

        # Replace the target-layer value outside the handler while leaving a stronger edit target active.
        self._stage.SetEditTarget(self._target_layer)
        self._stage.GetAttributeAtPath(self._albedo_path).Set(Sdf.AssetPath("textures/external.dds"))
        self._stage.SetEditTarget(self._stronger_layer)
        target_layer_before = self._target_layer.ExportToString()
        stronger_layer_before = self._stronger_layer.ExportToString()

        # Revert rejects the conflict and leaves both layers plus the current edit target unchanged.
        with self.assertRaises(ApplyExecutionError) as error_context:
            await ComfyUIJobApplyHandler().revert(value, target, receipt)

        self.assertIn("changed outside", error_context.exception.reason)
        self.assertEqual(self._target_layer.ExportToString(), target_layer_before)
        self.assertEqual(self._stronger_layer.ExportToString(), stronger_layer_before)
        self.assertIs(self._stage.GetEditTarget().GetLayer(), self._stronger_layer)

    async def test_reapply_uses_receipt_order_for_multi_output_target_set(self):
        """Reapply preserves receipt order when target metadata and processed results are reordered."""
        target = self._target((("normal_ogl", self._normal_path), ("albedo", self._albedo_path)))
        albedo_url = str(pathlib.Path(self._temp_dir.name) / "processed-albedo.dds")
        normal_url = str(pathlib.Path(self._temp_dir.name) / "processed-normal.dds")
        first_value = self._result(
            (
                ("albedo", albedo_url, TextureTypes.DIFFUSE),
                ("normal_ogl", normal_url, TextureTypes.NORMAL_OTH),
            )
        )
        handler = ComfyUIJobApplyHandler()
        receipt = await handler.capture_receipt(first_value, target)

        # Apply a two-texture result, then reorder only the target metadata before reapplying.
        await handler.apply(first_value, target, receipt)
        reordered_target = dataclasses.replace(
            target,
            texture_targets=(("albedo", self._albedo_path), ("normal_ogl", self._normal_path)),
        )

        result = await handler.apply(first_value, reordered_target, receipt)

        # Receipt order remains the durable authority for original and applied values.
        receipt_paths = [path for path, _ in receipt.applied_compare_values]
        self.assertIsNone(result)
        self.assertEqual(receipt_paths, [self._normal_path, self._albedo_path])
        self.assertEqual(
            receipt.original_authored_values,
            (
                (self._normal_path, "textures/original-normal.dds"),
                (self._albedo_path, "textures/original-albedo.dds"),
            ),
        )
        self.assertEqual(
            receipt.original_compare_values,
            tuple(
                (path, Sdf.ComputeAssetPathRelativeToLayer(self._target_layer, original))
                for path, original in (
                    (self._normal_path, "textures/original-normal.dds"),
                    (self._albedo_path, "textures/original-albedo.dds"),
                )
            ),
        )
