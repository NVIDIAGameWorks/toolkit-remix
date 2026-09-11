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

import dataclasses
import json
import pathlib
import tempfile
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import lightspeed.trex.comfyui.core.apply_handler as apply_handler_module
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    ProcessedTexture,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)
from lightspeed.trex.asset_pipeline.core.jobs.texture_processing import TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.metadata import MetadataApplyReceipt
from lightspeed.trex.comfyui.core.api import ComfyUIImageResult
from lightspeed.trex.comfyui.core.connection import set_connected_endpoint
from lightspeed.trex.comfyui.core.enums import WorkflowCategory, WorkflowSourceType
from lightspeed.trex.comfyui.core.apply_handler import ComfyUIJobApplyHandler, _get_apply_stage, _to_asset_url
from lightspeed.trex.comfyui.core.job import ComfyUIJob
from lightspeed.trex.comfyui.core.models import (
    ComfyUIApplyReceipt,
    ComfyUIApplyTarget,
    ComfyUIWorkflowRequest,
    Workflow,
    WorkflowOutput,
)
from lightspeed.trex.comfyui.core.resolvers import (
    ConstantResolver,
    LayerIdentifierResolver,
    SelectedPrimPathResolver,
    SelectedTextureResolver,
)
from lightspeed.trex.comfyui.core.tests.unit.fixtures import get_test_workflow_pair
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.enums import ApplyOperation
from omni.flux.job_queue.core.errors import ApplyExecutionError, JobExecutionError
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import (
    ApplyBinding,
    JobGraph,
    JobInputs,
    JobOutputs,
    JobProgress,
)
from omni.flux.job_queue.core.serializer import deserialize, serialize
from omni.kit.test import AsyncTestCase
from pxr import Sdf


def _make_workflow_request(
    *,
    prompt: dict[str, Any] | None = None,
    input_bindings: tuple[tuple[str, str], ...] = (),
    client_id: str = "",
    timeout: float = 300.0,
    output_url: str = "C:/project/assets/ingested/comfyui/test",
    workflow: Workflow | None = None,
) -> ComfyUIWorkflowRequest:
    """Create a complete typed workflow request for job behavior tests.

    Args:
        prompt: Resolved API workflow, or an empty prompt when omitted.
        input_bindings: Workflow port and source texture pairs.
        client_id: Client identifier stored with the prompt.
        timeout: Prompt completion timeout in seconds.
        output_url: Project destination for processed textures.
        workflow: Complete workflow metadata, or an empty workflow when omitted.

    Returns:
        Valid workflow request with independent default values.
    """
    return ComfyUIWorkflowRequest(
        prompt={} if prompt is None else prompt,
        input_bindings=input_bindings,
        client_id=client_id,
        timeout=timeout,
        output_url=output_url,
        workflow=Workflow() if workflow is None else workflow,
    )


class TestComfyUIJob(AsyncTestCase):
    """Test ComfyUI execution and persisted result behavior."""

    async def setUp(self) -> None:
        """Clear connected endpoints before each test."""
        set_connected_endpoint("texturecraft", None)

    async def tearDown(self) -> None:
        """Clear connected endpoints after each test."""
        set_connected_endpoint("texturecraft", None)

    async def test_construction_declares_workflow_request_input_and_generated_textures_output(self):
        """Generation consumes one typed workflow request and exposes raw textures without owning Apply."""
        # Arrange
        expected_input = ComfyUIJob.WORKFLOW_REQUEST
        expected_output = ComfyUIJob.GENERATED_TEXTURES

        # Act
        job = ComfyUIJob()

        # Assert
        self.assertEqual(expected_input.name, "workflow_request")
        self.assertEqual(job.input_ports, (expected_input,))
        self.assertIs(expected_output.value_type, TextureProcessingRequest)
        self.assertEqual(job.output_ports, (expected_output,))
        self.assertIsNone(job.apply_binding)
        job_fields = {field.name for field in dataclasses.fields(job)}
        for execution_field in ("prompt", "client_id", "input_mappings", "timeout", "output_url", "workflow"):
            with self.subTest(execution_field=execution_field):
                self.assertNotIn(execution_field, job_fields)

    async def test_schedule_block_reason_requires_exact_connected_endpoint(self):
        """A job runs only while its saved ComfyUI server is the verified connection."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="HTTP", host="Comfy-A", port=8188)
        cases = (
            (
                None,
                "Connect to the ComfyUI server at http://comfy-a:8188 to run this job.",
            ),
            (
                ("http", "comfy-b", 8188),
                "This job is waiting for http://comfy-a:8188. The current connection is http://comfy-b:8188. "
                "Connect to the original server or use Change Server for this job.",
            ),
            (("http", "COMFY-A", 8188), None),
        )

        for connected_endpoint, expected in cases:
            with self.subTest(connected_endpoint=connected_endpoint):
                set_connected_endpoint("texturecraft", connected_endpoint)

                # Act
                reason = job.get_schedule_block_reason()

                # Assert
                self.assertEqual(reason, expected)

    async def test_schedule_block_reason_formats_ipv6_endpoint(self):
        """The waiting reason renders an IPv6 endpoint as a valid URL."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="http", host="2001:db8::1", port=8188)

        # Act
        reason = job.get_schedule_block_reason()

        # Assert
        self.assertEqual(reason, "Connect to the ComfyUI server at http://[2001:db8::1]:8188 to run this job.")

    async def test_schedule_block_reason_reports_invalid_saved_server(self):
        """A malformed saved server waits with user-facing recovery guidance instead of raising."""
        # Arrange
        job = ComfyUIJob(context_name="texturecraft", scheme="invalid", host="bad host", port=0)

        # Act
        reason = job.get_schedule_block_reason()

        # Assert
        self.assertEqual(
            reason,
            "This job has an invalid ComfyUI server address. Connect to a server, then change the server for this job.",
        )

    async def test_apply_target_rejects_malformed_persisted_identity(self):
        """Apply targets reject blank identities, malformed tuples, duplicate keys, and invalid USD paths."""
        # Arrange
        valid = {
            "context_name": "texturecraft",
            "project_path": "C:/project/project.usda",
            "edit_target_layer": "C:/project/mod.usda",
            "material_path": "/World/Looks/Material",
            "texture_targets": (("albedo", "/Shader.inputs:diffuse_texture"),),
        }
        cases = (
            ({"context_name": None}, TypeError),
            ({"project_path": ""}, ValueError),
            ({"material_path": "Material"}, ValueError),
            ({"texture_targets": [("albedo", "/Shader.inputs:diffuse_texture")]}, TypeError),
            ({"texture_targets": (("", "/Shader.inputs:diffuse_texture"),)}, ValueError),
            ({"texture_targets": (("albedo", "Shader.inputs:diffuse_texture"),)}, ValueError),
            (
                {
                    "texture_targets": (
                        ("albedo", "/Shader.inputs:diffuse_texture"),
                        ("albedo", "/Shader.inputs:other_texture"),
                    )
                },
                ValueError,
            ),
        )

        for override, error_type in cases:
            with self.subTest(override=override):
                # Act
                with self.assertRaises(error_type) as error_context:
                    ComfyUIApplyTarget(**(valid | override))

                # Assert
                self.assertIs(type(error_context.exception), error_type)

        self.assertEqual(ComfyUIApplyTarget(**(valid | {"context_name": ""})).context_name, "")

    async def test_apply_receipt_rejects_malformed_snapshots(self):
        """Apply receipts require exact path-value tuples over one matching unique target set."""
        # Arrange
        original = (("/Shader.inputs:diffuse_texture", None),)
        applied = (("/Shader.inputs:diffuse_texture", "C:/project/albedo.dds"),)
        valid = {
            "original_authored_values": original,
            "original_compare_values": original,
            "applied_compare_values": applied,
        }
        cases = (
            ({"original_authored_values": list(original)}, TypeError),
            ({"original_compare_values": (("/Shader.inputs:diffuse_texture",),)}, TypeError),
            ({"original_authored_values": (("relative.inputs:texture", None),)}, ValueError),
            ({"applied_compare_values": (("/Shader.inputs:other_texture", "x"),)}, ValueError),
            (
                {"applied_compare_values": (("/Shader.inputs:diffuse_texture", 42),)},
                TypeError,
            ),
        )

        for fields, error_type in cases:
            with self.subTest(fields=fields):
                # Act
                with self.assertRaises(error_type) as error_context:
                    ComfyUIApplyReceipt(**(valid | fields))

                # Assert
                self.assertIs(type(error_context.exception), error_type)

    async def test_apply_rejects_processed_texture_incompatible_with_material_input(self):
        """A processed normal map cannot be applied through an albedo target key."""
        # Arrange
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        value = TextureProcessingResult(
            items=(
                ProcessedTexture(
                    key="albedo",
                    source_path=pathlib.Path("C:/queue/albedo.png"),
                    asset_url="C:/project/albedo.dds",
                    texture_type=TextureTypes.NORMAL_OTH,
                ),
            )
        )

        # Act
        with self.assertRaisesRegex(ValueError, "incompatible with its material input") as error_context:
            ComfyUIJobApplyHandler._get_replacements(value, target)

        # Assert
        self.assertIsInstance(error_context.exception, ValueError)

    async def test_apply_rejects_other_texture_through_albedo_target(self):
        """A generic texture cannot be applied through an albedo target key."""
        # Arrange
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        value = TextureProcessingResult(
            items=(
                ProcessedTexture(
                    key="albedo",
                    source_path=pathlib.Path("C:/queue/albedo.png"),
                    asset_url="C:/project/albedo.dds",
                    texture_type=TextureTypes.OTHER,
                ),
            )
        )

        # Act
        with self.assertRaisesRegex(ValueError, "incompatible with its material input") as error_context:
            ComfyUIJobApplyHandler._get_replacements(value, target)

        # Assert
        self.assertIsInstance(error_context.exception, ValueError)

    async def test_apply_rejects_external_edit_without_authoring(self):
        """Apply leaves the stage untouched when the target differs from its durable receipt."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        value = TextureProcessingResult(
            items=(
                ProcessedTexture(
                    key="albedo",
                    source_path=pathlib.Path("C:/queue/albedo.png"),
                    asset_url="applied.dds",
                    texture_type=TextureTypes.DIFFUSE,
                ),
            )
        )
        layer = MagicMock()
        layer.anonymous = True
        receipt = ComfyUIApplyReceipt(
            original_authored_values=(("/Shader.inputs:diffuse_texture", "old.dds"),),
            original_compare_values=(("/Shader.inputs:diffuse_texture", "old.dds"),),
            applied_compare_values=(("/Shader.inputs:diffuse_texture", "applied.dds"),),
        )
        with (
            patch("lightspeed.trex.comfyui.core.apply_handler._get_apply_stage", return_value=(MagicMock(), layer)),
            patch(
                "lightspeed.trex.comfyui.core.apply_handler._read_compare_values",
                return_value=(("/Shader.inputs:diffuse_texture", "external.dds"),),
            ) as read_compare,
        ):
            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                await handler.apply(value, target, receipt)

        # Assert
        self.assertIn("texture target changed", error_context.exception.reason)
        self.assertIn("changed outside", error_context.exception.reason)
        self.assertIn("durable Apply receipt", str(error_context.exception.diagnostic))
        read_compare.assert_called_once_with(layer, ("/Shader.inputs:diffuse_texture",))

    async def test_apply_wrong_project_exposes_safe_reason_and_diagnostic(self):
        """Apply separates actionable project guidance from the exact diagnostic."""
        # Arrange
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/submitted/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        stage = MagicMock()
        stage.GetRootLayer.return_value.anonymous = False
        stage.GetRootLayer.return_value.identifier = "D:/opened/project.usda"

        with patch("lightspeed.trex.comfyui.core.apply_handler.get_context") as get_context:
            get_context.return_value.get_stage.return_value = stage

            # Act
            with self.assertRaises(ApplyExecutionError) as error_context:
                _get_apply_stage(target)

        # Assert
        self.assertEqual(
            error_context.exception.reason,
            "This job belongs to a different project. Open the project used to create it before applying its processed textures.\n"
            "Job project: C:/submitted/project.usda\n"
            "Opened project: D:/opened/project.usda",
        )
        self.assertIn("open project differs", str(error_context.exception.diagnostic))

    async def test_apply_block_reason_explains_missing_project_without_mutating_state(self):
        """Every Apply operation exposes missing-project guidance before work is claimed."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        expected_reason = "Open the project used to create this job before applying its processed textures."

        with patch("lightspeed.trex.comfyui.core.apply_handler.get_context") as get_context:
            get_context.return_value.get_stage.return_value = None

            # Act
            reasons = {
                operation: handler.get_apply_block_reason(target, operation)
                for operation in (
                    ApplyOperation.APPLYING,
                    ApplyOperation.REAPPLYING,
                    ApplyOperation.REVERTING,
                )
            }

        # Assert
        self.assertEqual(
            reasons,
            {
                ApplyOperation.APPLYING: expected_reason,
                ApplyOperation.REAPPLYING: expected_reason,
                ApplyOperation.REVERTING: expected_reason,
            },
        )

    async def test_applied_result_block_reason_identifies_the_original_project(self):
        """Reapply and Revert reuse the project mismatch reason."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/submitted/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        expected_reason = (
            "This job belongs to a different project. "
            "Open the project used to create it before applying its processed textures.\n"
            "Job project: C:/submitted/project.usda\n"
            "Opened project: D:/opened/project.usda"
        )
        expected_reasons = {
            ApplyOperation.REAPPLYING: expected_reason,
            ApplyOperation.REVERTING: expected_reason,
        }
        with patch("lightspeed.trex.comfyui.core.apply_handler.get_context") as get_context:
            stage = get_context.return_value.get_stage.return_value
            stage.GetRootLayer.return_value.identifier = "D:/opened/project.usda"

            # Act
            reasons = {operation: handler.get_apply_block_reason(target, operation) for operation in expected_reasons}

        # Assert
        self.assertEqual(reasons, expected_reasons)

    async def test_apply_resolves_matching_live_anonymous_layers(self):
        """Apply accepts exact live layer identities without requiring either layer to be saved."""
        # Arrange
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="anon:submitted-stage",
            edit_target_layer="anon:submitted-edit-target",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        stage = MagicMock()
        root_layer = stage.GetRootLayer.return_value
        root_layer.anonymous = True
        root_layer.identifier = "anon:submitted-stage"
        edit_layer = MagicMock(anonymous=True, identifier="anon:submitted-edit-target")
        stage.GetLayerStack.return_value = [root_layer, edit_layer]

        with patch("lightspeed.trex.comfyui.core.apply_handler.get_context") as get_context:
            get_context.return_value.get_stage.return_value = stage

            # Act
            resolved_stage, resolved_layer = _get_apply_stage(target)

        # Assert
        self.assertIs(resolved_stage, stage)
        self.assertIs(resolved_layer, edit_layer)

    async def test_revert_restores_original_values_with_one_forced_undo_group(self):
        """Revert uses the canonical replacement API for original non-ingested values."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        receipt = ComfyUIApplyReceipt(
            original_authored_values=(("/Shader.inputs:diffuse_texture", "../original/source.png"),),
            original_compare_values=(("/Shader.inputs:diffuse_texture", "C:/original/source.png"),),
            applied_compare_values=(("/Shader.inputs:diffuse_texture", "C:/project/albedo.dds"),),
        )
        stage = MagicMock()
        layer = MagicMock()
        replacements = MagicMock()
        value = MagicMock(spec=TextureProcessingResult)
        with (
            patch("lightspeed.trex.comfyui.core.apply_handler._get_apply_stage", return_value=(stage, layer)),
            patch(
                "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                return_value=receipt.applied_compare_values,
            ),
            patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore", return_value=replacements),
        ):
            # Act
            await handler.revert(value, target, receipt)

        # Assert
        replacements.replace_textures.assert_called_once_with(
            [("/Shader.inputs:diffuse_texture", "../original/source.png")],
            force=True,
            target_layer=layer,
            expected_current_textures=list(receipt.applied_compare_values),
        )

    async def test_capture_receipt_and_revert_round_trip_real_sidecars(self):
        """Capture reads real prior sidecars; Revert restores or deletes them exactly after a real Apply write."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        albedo_path = "/Shader.inputs:diffuse_texture"
        normal_path = "/Shader.inputs:normalmap_texture"
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", albedo_path), ("normal_ogl", normal_path)),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            albedo_output = temp_path / "albedo.dds"
            albedo_output.write_bytes(b"DDS")
            albedo_sidecar = albedo_output.with_suffix(".dds.meta")
            albedo_sidecar.write_text('{"prior": "albedo"}')
            normal_output = temp_path / "normal.dds"
            normal_output.write_bytes(b"DDS")
            normal_sidecar = normal_output.with_suffix(".dds.meta")
            self.assertFalse(normal_sidecar.exists())

            value = TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/queue/albedo.png"),
                        asset_url=str(albedo_output),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="normal_ogl",
                        source_path=pathlib.Path("C:/queue/normal.png"),
                        asset_url=str(normal_output),
                        texture_type=TextureTypes.NORMAL_OTH,
                    ),
                )
            )
            layer = MagicMock()
            layer.anonymous = True
            replacements = MagicMock()
            original_authored_values = ((albedo_path, "old-albedo.dds"), (normal_path, "old-normal.dds"))
            applied_authored_values = ((albedo_path, str(albedo_output)), (normal_path, str(normal_output)))
            with (
                patch("lightspeed.trex.comfyui.core.apply_handler._get_apply_stage", return_value=(MagicMock(), layer)),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                    side_effect=[original_authored_values, applied_authored_values],
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._canonicalize_asset_url",
                    side_effect=lambda _layer, asset_url: asset_url,
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_compare_values",
                    return_value=original_authored_values,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore", return_value=replacements),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler.get_current_validation_extensions",
                    return_value=[],
                ),
            ):
                # Act
                receipt = await handler.capture_receipt(value, target)
                await handler.apply(value, target, receipt)
                albedo_after_apply = albedo_sidecar.read_text()
                normal_after_apply = normal_sidecar.read_text()

                await handler.revert(value, target, receipt)

            # Assert: capture read the real prior sidecar for the output that had one, and recorded none otherwise.
            self.assertEqual(
                dict(receipt.prior_metadata.prior_meta),
                {albedo_sidecar: '{"prior": "albedo"}', normal_sidecar: None},
            )
            # Apply overwrote both sidecars with real hashed metadata before Revert ran.
            self.assertNotEqual(albedo_after_apply, '{"prior": "albedo"}')
            self.assertTrue(normal_after_apply)
            # Revert restored the exact prior sidecar bytes and deleted the sidecar absent before Apply.
            self.assertEqual(albedo_sidecar.read_text(), '{"prior": "albedo"}')
            self.assertFalse(normal_sidecar.exists())

    async def test_apply_restores_sidecars_when_metadata_write_fails(self):
        """A partial metadata write restores both prior sidecars."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        shader_path = "/Shader.inputs:diffuse_texture"
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", shader_path), ("normal_ogl", "/Shader.inputs:normalmap_texture")),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "albedo.dds"
            output.write_bytes(b"DDS")
            sidecar = output.with_suffix(".dds.meta")
            sidecar.write_bytes(b'{"prior": "first Apply"}')
            normal_output = pathlib.Path(temp_dir) / "normal.dds"
            normal_output.write_bytes(b"DDS")
            normal_sidecar = normal_output.with_suffix(".dds.meta")
            normal_before = {"prior": "normal"}
            normal_sidecar.write_text(json.dumps(normal_before))
            value = TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/queue/albedo.png"),
                        asset_url=str(output),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="normal_ogl",
                        source_path=pathlib.Path("C:/queue/normal.png"),
                        asset_url=str(normal_output),
                        texture_type=TextureTypes.NORMAL_OTH,
                    ),
                ),
            )
            original_values = ((shader_path, "old.dds"), ("/Shader.inputs:normalmap_texture", "old_normal.dds"))
            metadata_error = RuntimeError("Metadata write failed")

            def fail_metadata_write(*_args):
                sidecar.write_text(json.dumps({"partial": "write"}))
                raise metadata_error

            with (
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._get_apply_stage",
                    return_value=(MagicMock(), MagicMock()),
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                    return_value=original_values,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler._read_compare_values", return_value=original_values),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._canonicalize_asset_url",
                    side_effect=lambda _layer, url: url,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler.get_current_validation_extensions", return_value=[]),
                patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore"),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler.write_metadata_for_paths",
                    side_effect=fail_metadata_write,
                ),
            ):
                receipt = await handler.capture_receipt(value, target)
                # A later attempt must preserve its own baseline, not the first Apply baseline.
                before_apply = {"prior": "this Apply attempt"}
                sidecar.write_text(json.dumps(before_apply))

                # Act
                with self.assertRaises(RuntimeError) as error_context:
                    await handler.apply(value, target, receipt)

            # Assert
            self.assertIs(error_context.exception, metadata_error)
            self.assertEqual(json.loads(sidecar.read_text()), before_apply)
            self.assertEqual(json.loads(normal_sidecar.read_text()), normal_before)

    async def test_apply_restores_sidecar_when_shader_changes_during_metadata_write(self):
        """An external shader edit stops Apply and restores prior metadata."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        shader_path = "/Shader.inputs:diffuse_texture"
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", shader_path),),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "albedo.dds"
            output.write_bytes(b"DDS")
            sidecar = output.with_suffix(".dds.meta")
            sidecar.write_bytes(b'{"prior": "first Apply"}')
            value = TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/queue/albedo.png"),
                        asset_url=str(output),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                ),
            )
            original_values = ((shader_path, "old.dds"),)
            with (
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._get_apply_stage",
                    return_value=(MagicMock(), MagicMock()),
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                    return_value=original_values,
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_compare_values",
                    side_effect=[original_values, ((shader_path, "edited.dds"),)],
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._canonicalize_asset_url",
                    side_effect=lambda _layer, url: url,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler.get_current_validation_extensions", return_value=[]),
                patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore") as replacements,
            ):
                receipt = await handler.capture_receipt(value, target)
                # A later attempt must preserve its own baseline, not the first Apply baseline.
                before_apply = {"prior": "this Apply attempt"}
                sidecar.write_text(json.dumps(before_apply))

                # Act
                with self.assertRaises(ApplyExecutionError):
                    await handler.apply(value, target, receipt)

            # Assert
            replacements.return_value.replace_textures.assert_not_called()
            self.assertEqual(json.loads(sidecar.read_text()), before_apply)

    async def test_revert_restores_sidecar_when_shader_already_matches_original(self):
        """Revert restores prior metadata when the shader already has its original value."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        shader_path = "/Shader.inputs:diffuse_texture"
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", shader_path),),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "albedo.dds"
            output.write_bytes(b"DDS")
            sidecar = output.with_suffix(".dds.meta")
            sidecar.write_bytes(b'{"prior": "first Apply"}')
            value = TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/queue/albedo.png"),
                        asset_url=str(output),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                ),
            )
            original_values = ((shader_path, "old.dds"),)
            with (
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._get_apply_stage",
                    return_value=(MagicMock(), MagicMock()),
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                    return_value=original_values,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler._read_compare_values", return_value=original_values),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._canonicalize_asset_url",
                    side_effect=lambda _layer, url: url,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler.get_current_validation_extensions", return_value=[]),
                patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore") as replacements,
            ):
                receipt = await handler.capture_receipt(value, target)
                before_apply = json.loads(sidecar.read_text())
                await handler.apply(value, target, receipt)
                replacements.return_value.replace_textures.reset_mock()

                # Act
                await handler.revert(value, target, receipt)

            # Assert
            replacements.return_value.replace_textures.assert_not_called()
            self.assertEqual(json.loads(sidecar.read_text()), before_apply)

    async def test_apply_restores_sidecar_when_shader_update_fails(self):
        """A failed shader update restores the sidecar data from before this Apply attempt."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        shader_path = "/Shader.inputs:diffuse_texture"
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", shader_path),),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "albedo.dds"
            output.write_bytes(b"DDS")
            sidecar = output.with_suffix(".dds.meta")
            sidecar.write_bytes(b'{"prior": "first Apply"}')
            value = TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/queue/albedo.png"),
                        asset_url=str(output),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                ),
            )
            original_values = ((shader_path, "old.dds"),)
            shader_error = RuntimeError("Shader update failed")
            with (
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._get_apply_stage",
                    return_value=(MagicMock(), MagicMock()),
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                    return_value=original_values,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler._read_compare_values", return_value=original_values),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._canonicalize_asset_url",
                    side_effect=lambda _layer, url: url,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler.get_current_validation_extensions", return_value=[]),
                patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore") as replacements,
            ):
                receipt = await handler.capture_receipt(value, target)
                # A later attempt must preserve its own baseline, not the first Apply baseline.
                before_apply = {"prior": "this Apply attempt"}
                sidecar.write_text(json.dumps(before_apply))
                replacements.return_value.replace_textures.side_effect = shader_error

                # Act
                with self.assertRaises(RuntimeError) as error_context:
                    await handler.apply(value, target, receipt)

            # Assert
            self.assertIs(error_context.exception, shader_error)
            self.assertEqual(json.loads(sidecar.read_text()), before_apply)

    async def test_revert_restores_sidecar_when_shader_restore_fails(self):
        """A failed shader restore retains the sidecar data from the applied state."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        shader_path = "/Shader.inputs:diffuse_texture"
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", shader_path),),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "albedo.dds"
            output.write_bytes(b"DDS")
            sidecar = output.with_suffix(".dds.meta")
            value = TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/queue/albedo.png"),
                        asset_url=str(output),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                ),
            )
            original_values = ((shader_path, "old.dds"),)
            applied_values = ((shader_path, str(output)),)
            shader_error = RuntimeError("Shader restore failed")
            with (
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._get_apply_stage",
                    return_value=(MagicMock(), MagicMock()),
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                    side_effect=[original_values, applied_values],
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler._read_compare_values", return_value=original_values),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._canonicalize_asset_url",
                    side_effect=lambda _layer, url: url,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler.get_current_validation_extensions", return_value=[]),
                patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore") as replacements,
            ):
                receipt = await handler.capture_receipt(value, target)
                await handler.apply(value, target, receipt)
                before_revert = json.loads(sidecar.read_text())
                replacements.return_value.replace_textures.side_effect = shader_error

                # Act
                with self.assertRaises(RuntimeError) as error_context:
                    await handler.revert(value, target, receipt)

            # Assert
            self.assertIs(error_context.exception, shader_error)
            self.assertTrue(sidecar.is_file())
            self.assertEqual(json.loads(sidecar.read_text()), before_revert)

    async def test_revert_restores_both_sidecars_when_one_metadata_restore_fails(self):
        """A metadata restore that fails on the second sidecar leaves neither sidecar partly restored."""
        # Arrange
        handler = ComfyUIJobApplyHandler()
        albedo_shader = "/Shader.inputs:diffuse_texture"
        roughness_shader = "/Shader.inputs:reflectionroughness_texture"
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", albedo_shader), ("roughness", roughness_shader)),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            outputs = {}
            for key in ("albedo", "roughness"):
                output = temp_path / f"{key}.dds"
                output.write_bytes(b"DDS")
                sidecar = output.with_suffix(".dds.meta")
                sidecar.write_text(json.dumps({"prior": key}))
                outputs[key] = (output, sidecar)
            value = TextureProcessingResult(
                items=tuple(
                    ProcessedTexture(
                        key=key,
                        source_path=pathlib.Path(f"C:/queue/{key}.png"),
                        asset_url=str(outputs[key][0]),
                        texture_type=texture_type,
                    )
                    for key, texture_type in (("albedo", TextureTypes.DIFFUSE), ("roughness", TextureTypes.ROUGHNESS))
                ),
            )
            original_values = ((albedo_shader, "old-albedo.dds"), (roughness_shader, "old-roughness.dds"))
            applied_values = tuple((path, str(outputs[key][0])) for key, path in target.texture_targets)
            restore_error = RuntimeError("Sidecar is read-only")
            real_revert_metadata = apply_handler_module.revert_metadata

            restore_calls = []

            def fail_durable_restore(received):
                """Half-restore the durable receipt, then fail; a rollback receipt restores normally."""
                restore_calls.append(received)
                if received is receipt.prior_metadata:
                    real_revert_metadata(type(received)(prior_meta=received.prior_meta[:1]))
                    raise restore_error
                real_revert_metadata(received)

            with (
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._get_apply_stage",
                    return_value=(MagicMock(), MagicMock()),
                ),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                    side_effect=[original_values, applied_values],
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler._read_compare_values", return_value=original_values),
                patch(
                    "lightspeed.trex.comfyui.core.apply_handler._canonicalize_asset_url",
                    side_effect=lambda _layer, url: url,
                ),
                patch("lightspeed.trex.comfyui.core.apply_handler.get_current_validation_extensions", return_value=[]),
                patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore"),
            ):
                receipt = await handler.capture_receipt(value, target)
                await handler.apply(value, target, receipt)
                applied = {key: json.loads(outputs[key][1].read_text()) for key in outputs}
                with patch.object(apply_handler_module, "revert_metadata", side_effect=fail_durable_restore):
                    # Act
                    with self.assertRaises(RuntimeError) as error_context:
                        await handler.revert(value, target, receipt)

            # Assert
            self.assertIs(error_context.exception, restore_error)
            for key, (_output, sidecar) in outputs.items():
                self.assertEqual(json.loads(sidecar.read_text()), applied[key])

    async def test_apply_receipt_target_mismatch_exposes_safe_reason_and_diagnostic(self):
        """Invalid saved Apply data provides recovery guidance without leaking internal terms."""
        # Arrange
        receipt = ComfyUIApplyReceipt(
            original_authored_values=(("/Shader.inputs:other_texture", "old.dds"),),
            original_compare_values=(("/Shader.inputs:other_texture", "old.dds"),),
            applied_compare_values=(("/Shader.inputs:other_texture", "applied.dds"),),
        )

        # Act
        with self.assertRaises(ApplyExecutionError) as error_context:
            ComfyUIJobApplyHandler._verify_receipt_target(
                ("/Shader.inputs:diffuse_texture",),
                receipt,
            )

        # Assert
        self.assertNotIn("receipt", error_context.exception.reason.lower())
        self.assertIn("saved Apply data", error_context.exception.reason)
        self.assertIn("receipt", str(error_context.exception.diagnostic))

    async def test_authored_asset_url_rejects_unsupported_usd_values(self):
        """Receipt capture never stringifies a blocked or malformed USD opinion."""
        # Arrange
        blocked_value = Sdf.ValueBlock()

        # Act
        with self.assertRaises(TypeError) as error_context:
            _to_asset_url(blocked_value)

        # Assert
        self.assertIsInstance(error_context.exception, TypeError)

    async def test_serialization_preserves_apply_target_and_receipt(self):
        """Queue persistence retains exact typed Apply identity and original values."""
        # Arrange
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        receipt = ComfyUIApplyReceipt(
            original_authored_values=(("/Shader.inputs:diffuse_texture", None),),
            original_compare_values=(("/Shader.inputs:diffuse_texture", None),),
            applied_compare_values=(("/Shader.inputs:diffuse_texture", "C:/project/albedo.dds"),),
            prior_metadata=MetadataApplyReceipt(
                prior_meta=((pathlib.Path("C:/project/albedo.dds.meta"), '{"prior": "meta"}'),)
            ),
        )

        # Act
        restored_target = deserialize(serialize(target))
        restored_receipt = deserialize(serialize(receipt))

        # Assert
        self.assertEqual(restored_target, target)
        self.assertEqual(restored_receipt, receipt)
        self.assertEqual(restored_receipt.prior_metadata, receipt.prior_metadata)

    async def test_legacy_apply_receipt_payload_decodes_with_empty_metadata_and_reverts_as_noop(self):
        """A released 3-tuple ComfyUIApplyReceipt payload decodes with empty prior_metadata and reverts inertly."""
        # Arrange
        path = "/Shader.inputs:diffuse_texture"
        receipt = ComfyUIApplyReceipt(
            original_authored_values=((path, "old.dds"),),
            original_compare_values=((path, "old.dds"),),
            applied_compare_values=((path, "applied.dds"),),
        )
        envelope = json.loads(serialize(receipt))
        envelope["value"]["value"] = envelope["value"]["value"][:3]  # drop prior_metadata: released shape

        # Act
        legacy_receipt = deserialize(json.dumps(envelope))

        # Assert: the legacy payload decodes with an empty metadata receipt.
        self.assertEqual(legacy_receipt, receipt)
        self.assertEqual(legacy_receipt.prior_metadata, MetadataApplyReceipt(prior_meta=()))

        # Revert with the decoded legacy receipt is a metadata no-op: nothing to restore or delete.
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", path),),
        )
        layer = MagicMock()
        replacements = MagicMock()
        value = MagicMock(spec=TextureProcessingResult)
        with (
            patch("lightspeed.trex.comfyui.core.apply_handler._get_apply_stage", return_value=(MagicMock(), layer)),
            patch(
                "lightspeed.trex.comfyui.core.apply_handler._read_exact_authored_values",
                return_value=legacy_receipt.applied_compare_values,
            ),
            patch("lightspeed.trex.comfyui.core.apply_handler.TextureReplacementsCore", return_value=replacements),
            patch("lightspeed.trex.comfyui.core.apply_handler.revert_metadata") as revert_metadata_mock,
        ):
            await ComfyUIJobApplyHandler().revert(value, target, legacy_receipt)

        revert_metadata_mock.assert_called_once_with(MetadataApplyReceipt(prior_meta=()))

    async def test_apply_receipt_payload_arity_outside_legacy_and_current_shapes_raises(self):
        """A ComfyUIApplyReceipt payload of any length other than 3 or 4 raises ValueError."""
        # Arrange
        path = "/Shader.inputs:diffuse_texture"
        receipt = ComfyUIApplyReceipt(
            original_authored_values=((path, "old.dds"),),
            original_compare_values=((path, "old.dds"),),
            applied_compare_values=((path, "applied.dds"),),
        )
        envelope = json.loads(serialize(receipt))
        envelope["value"]["value"] = envelope["value"]["value"][:2]  # neither 3 nor 4 values

        # Act / Assert
        with self.assertRaises(ValueError):
            deserialize(json.dumps(envelope))

    async def test_queue_restart_reconstructs_typed_children_and_binding(self):
        """Queue tables reconstruct both children, the workflow input, and the processing Apply binding."""
        # Arrange
        target = ComfyUIApplyTarget(
            context_name="texturecraft",
            project_path="C:/project/project.usda",
            edit_target_layer="C:/project/mod.usda",
            material_path="/World/Looks/Material",
            texture_targets=(("albedo", "/Shader.inputs:diffuse_texture"),),
        )
        generation_job = ComfyUIJob(name="Generate Material", context_name="texturecraft")
        workflow_request = _make_workflow_request()
        processing_job = TextureProcessingJob(
            name="Process Material",
            apply_binding=ApplyBinding(
                output_port=TextureProcessingJob.PROCESSED_TEXTURES,
                handler_type=ComfyUIJobApplyHandler,
                target=target,
            ),
        )
        graph = JobGraph(name="Material - Custom Settings")
        graph.add_job(generation_job)
        graph.add_job(processing_job)
        graph.bind(generation_job, ComfyUIJob.WORKFLOW_REQUEST, workflow_request)
        graph.connect(
            generation_job.output(ComfyUIJob.GENERATED_TEXTURES),
            processing_job.input(TextureProcessingJob.SOURCE_TEXTURES),
        )
        with tempfile.TemporaryDirectory(prefix="comfyui-queue-") as temp_dir:
            db_path = str(pathlib.Path(temp_dir) / "queue.sqlite")
            interface = QueueInterface(db_path)
            interface.submit(graph)

            # Act
            restarted = QueueInterface(db_path)
            graph_snapshot = restarted.get_graph_snapshots()[0]
            restored_generation = restarted.get_job(generation_job.job_id)
            restored_processing = restarted.get_job(processing_job.job_id)
            restored_request = restarted.resolve_job_inputs(generation_job.job_id)[ComfyUIJob.WORKFLOW_REQUEST]

        # Assert
        self.assertEqual(graph_snapshot.name, graph.name)
        self.assertEqual(
            [snapshot.job_id for snapshot in graph_snapshot.jobs],
            [generation_job.job_id, processing_job.job_id],
        )
        self.assertIs(type(restored_generation), ComfyUIJob)
        self.assertIs(type(restored_processing), TextureProcessingJob)
        self.assertIsNone(restored_generation.apply_binding)
        self.assertEqual(restored_request, workflow_request)
        self.assertIs(restored_processing.apply_binding.handler_type, ComfyUIJobApplyHandler)
        self.assertEqual(restored_processing.apply_binding.target, target)

    async def test_queue_restart_resolves_persisted_generation_output(self):
        """Queue tables resolve a persisted generation output into the processing input after restart."""
        # Arrange
        generation_job = ComfyUIJob(name="Generate Material", context_name="texturecraft")
        workflow_request = _make_workflow_request()
        processing_job = TextureProcessingJob(name="Process Material")
        graph = JobGraph(name="Material processing")
        graph.add_job(generation_job)
        graph.add_job(processing_job)
        graph.bind(generation_job, ComfyUIJob.WORKFLOW_REQUEST, workflow_request)
        graph.connect(
            generation_job.output(ComfyUIJob.GENERATED_TEXTURES),
            processing_job.input(TextureProcessingJob.SOURCE_TEXTURES),
        )
        request = TextureProcessingRequest(
            items=(
                TextureProcessingItem(
                    key="albedo",
                    path=pathlib.Path("C:/queue/albedo.png"),
                    texture_type=TextureTypes.DIFFUSE,
                ),
            ),
            source_root=pathlib.Path("C:/queue"),
            output_url=workflow_request.output_url,
        )
        with tempfile.TemporaryDirectory(prefix="comfyui-queue-") as temp_dir:
            db_path = str(pathlib.Path(temp_dir) / "queue.sqlite")
            interface = QueueInterface(db_path)
            interface.submit(graph)
            set_connected_endpoint("texturecraft", ("http", "127.0.0.1", 8188))
            self.assertEqual(interface.claim_runnable_jobs(), [generation_job.job_id])
            self.assertTrue(interface.start_job(generation_job.job_id))
            self.assertTrue(
                interface.complete_job(
                    generation_job.job_id,
                    JobOutputs({ComfyUIJob.GENERATED_TEXTURES: request}),
                )
            )
            restarted = QueueInterface(db_path)

            # Act
            restored_inputs = restarted.resolve_job_inputs(processing_job.job_id)

        # Assert
        self.assertEqual(restored_inputs[TextureProcessingJob.SOURCE_TEXTURES], request)

    async def test_execute_groups_declared_pbr_outputs_from_one_texture_input(self):
        """One source texture produces one processing request containing the complete declared PBR set."""
        # Arrange
        api = MagicMock()
        api.upload_image = AsyncMock(return_value={"name": "color.png", "subfolder": "inputs"})
        api.submit_prompt = AsyncMock(return_value="prompt-123")
        api.wait_for_prompt_completion = AsyncMock(
            return_value={
                "prompt-123": {
                    "outputs": {
                        "99": {"images": [{"filename": "albedo.png", "type": "output"}]},
                        "100": {"images": [{"filename": "normal.png", "type": "output"}]},
                        "101": {"images": [{"filename": "roughness.png", "type": "output"}]},
                        "102": {"images": [{"filename": "metallic.png", "type": "output"}]},
                    },
                    "status": {"completed": True},
                }
            }
        )
        api.download_image = AsyncMock(side_effect=lambda _image, destination: destination)
        job = ComfyUIJob()
        request = ComfyUIWorkflowRequest(
            prompt={
                "68": {"inputs": {"image": "/textures/color.png"}},
                "99": {},
                "100": {},
                "101": {},
                "102": {},
            },
            workflow=Workflow(
                output_specs=[
                    WorkflowOutput("99", "albedo", order=1),
                    WorkflowOutput("100", "normal_ogl", order=2),
                    WorkflowOutput("101", "roughness", order=3),
                    WorkflowOutput("102", "metallic", order=4),
                ]
            ),
            input_bindings=(("68.inputs.image", "/textures/color.png"),),
            client_id="",
            timeout=300.0,
            output_url="C:/project/assets/ingested/comfyui/job",
        )
        progress = AsyncMock()

        with patch("lightspeed.trex.comfyui.core.job.ComfyUIAPI", return_value=api):
            # Act
            outputs = await job.execute(
                pathlib.Path("C:/jobs"),
                JobInputs({ComfyUIJob.WORKFLOW_REQUEST: request}),
                progress,
            )

        # Assert
        result = outputs[ComfyUIJob.GENERATED_TEXTURES]
        self.assertIsInstance(result, TextureProcessingRequest)
        self.assertEqual([item.key for item in result.items], ["albedo", "normal_ogl", "roughness", "metallic"])
        self.assertEqual(
            [item.texture_type for item in result.items],
            [TextureTypes.DIFFUSE, TextureTypes.NORMAL_OGL, TextureTypes.ROUGHNESS, TextureTypes.METALLIC],
        )
        self.assertEqual(result.source_root, pathlib.Path("C:/jobs/outputs/prompt-123"))
        self.assertEqual(result.output_url, request.output_url)
        progress.assert_any_await(JobProgress(completed=1, total=4, detail="Submitting workflow to ComfyUI."))
        progress.assert_any_await(JobProgress(completed=4, total=4, detail="Downloaded 4 generated textures."))
        api.upload_image.assert_awaited_once()
        self.assertEqual(api.download_image.await_count, 4)
        api.submit_prompt.assert_awaited_once_with(
            {
                "68": {"inputs": {"image": "inputs/color.png"}},
                "99": {},
                "100": {},
                "101": {},
                "102": {},
            },
            "",
            extra_data={
                "extra_pnginfo": {
                    "rtx-remix": {"subfolder": f"rtx-remix/{job.job_id}"},
                    "workflow": {"nodes": []},
                }
            },
        )

    async def test_execute_rejects_unsupported_generated_texture_type(self):
        """An unsupported declared output fails with an actionable queue reason instead of a mapping error."""
        # Arrange
        api = MagicMock()
        api.submit_prompt = AsyncMock(return_value="prompt-123")
        api.wait_for_prompt_completion = AsyncMock(
            return_value={
                "prompt-123": {
                    "outputs": {"99": {"images": [{"filename": "unsupported.png", "type": "output"}]}},
                    "status": {"completed": True},
                }
            }
        )
        api.download_image = AsyncMock(side_effect=lambda _image, destination: destination)
        job = ComfyUIJob()
        request = _make_workflow_request(
            prompt={"99": {}},
            workflow=Workflow(output_specs=[WorkflowOutput("99", "unsupported", order=1)]),
        )

        # Act
        with patch("lightspeed.trex.comfyui.core.job.ComfyUIAPI", return_value=api):
            with self.assertRaises(JobExecutionError) as error_context:
                await job.execute(
                    pathlib.Path("C:/jobs"),
                    JobInputs({ComfyUIJob.WORKFLOW_REQUEST: request}),
                    AsyncMock(),
                )

        # Assert
        self.assertEqual(
            error_context.exception.reason,
            "ComfyUI returned a texture type this version of RTX Remix does not support. "
            "Update the workflow or RTX Remix, then try again.",
        )
        self.assertIsInstance(error_context.exception.diagnostic, ValueError)

    async def test_execute_retains_submit_diagnostic_beside_safe_reason(self):
        """Queue UI receives actionable text while logs retain the underlying server failure."""
        # Arrange
        diagnostic = RuntimeError("HTTP 500 from internal-host/path")
        api = MagicMock()
        api.submit_prompt = AsyncMock(side_effect=diagnostic)
        progress = AsyncMock()
        job = ComfyUIJob()
        request = _make_workflow_request()

        # Act
        with patch("lightspeed.trex.comfyui.core.job.ComfyUIAPI", return_value=api):
            with self.assertRaises(JobExecutionError) as error_context:
                await job.execute(
                    pathlib.Path("C:/jobs"),
                    JobInputs({ComfyUIJob.WORKFLOW_REQUEST: request}),
                    progress,
                )

        # Assert
        self.assertEqual(
            error_context.exception.reason,
            "ComfyUI could not start this workflow. Check the server connection and workflow, then try again.",
        )
        self.assertIs(error_context.exception.diagnostic, diagnostic)

    async def test_build_prompt_rejects_missing_upload(self):
        """A missing upload cannot leave a client-local path in the server prompt."""
        # Arrange
        job = ComfyUIJob()
        request = _make_workflow_request(
            prompt={"68": {"inputs": {"image": "C:/textures/source.dds"}}},
            input_bindings=(("68.inputs.image", "C:/textures/source.dds"),),
        )

        # Act
        with self.assertRaises(RuntimeError) as error_context:
            job._build_prompt(request, {})

        # Assert
        self.assertIn("was not uploaded", str(error_context.exception))

    async def test_build_prompt_rejects_missing_prompt_field(self):
        """A persisted mapping must still identify an executable prompt field."""
        # Arrange
        local_path = "C:/textures/source.dds"
        job = ComfyUIJob()
        request = _make_workflow_request(
            prompt={"68": {"inputs": {"image": local_path}}},
            input_bindings=(("68.inputs.missing", local_path),),
        )
        uploaded = {local_path: {"name": "source.dds", "subfolder": ""}}

        # Act
        with self.assertRaises(ValueError) as error_context:
            job._build_prompt(request, uploaded)

        # Assert
        self.assertIn("68.inputs.missing", str(error_context.exception))

    async def test_upload_images_isolates_equal_basenames(self):
        """Distinct local inputs with one basename use separate server namespaces."""
        # Arrange
        api = MagicMock()
        api.upload_image = AsyncMock(
            side_effect=lambda file_path, *, subfolder: {
                "name": pathlib.Path(file_path).name,
                "subfolder": subfolder,
                "type": "input",
            }
        )
        job = ComfyUIJob(job_id=uuid.UUID("12345678-1234-5678-1234-567812345678"))
        request = _make_workflow_request(
            input_bindings=(
                ("1.inputs.image", "C:/textures/first/albedo.png"),
                ("2.inputs.image", "C:/textures/second/albedo.png"),
            )
        )

        # Act
        uploaded = await job._upload_images(api, request)

        # Assert
        first = uploaded["C:/textures/first/albedo.png"]["subfolder"]
        second = uploaded["C:/textures/second/albedo.png"]["subfolder"]
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith(f"rtx-remix/{job.job_id}/"))
        self.assertTrue(second.startswith(f"rtx-remix/{job.job_id}/"))

    async def test_parse_results_rejects_malformed_history(self):
        """Malformed output containers cannot become an empty successful result."""
        # Arrange
        job = ComfyUIJob()
        workflow = Workflow(output_specs=[WorkflowOutput("99", "albedo")])

        # Act
        with self.assertRaises(RuntimeError) as error_context:
            job._parse_results({"prompt-123": {"outputs": []}}, "prompt-123", workflow)

        # Assert
        self.assertIn("Invalid ComfyUI history response", str(error_context.exception))

    async def test_parse_results_rejects_unsafe_output_paths(self):
        """Server-controlled output components must remain portable relative paths."""
        # Arrange
        job = ComfyUIJob()
        workflow = Workflow(output_specs=[WorkflowOutput("99", "albedo")])
        unsafe_outputs = (
            {"filename": "output.png", "subfolder": r"..\escape", "type": "output"},
            {"filename": "output.png.", "subfolder": "", "type": "output"},
            {"filename": "output.png", "subfolder": "CON", "type": "output"},
            {"filename": "output.png", "subfolder": "safe/folder.", "type": "output"},
        )

        for image_info in unsafe_outputs:
            with self.subTest(image_info=image_info):
                history = {"prompt-123": {"outputs": {"99": {"images": [image_info]}}}}

                # Act
                with self.assertRaises(RuntimeError) as error_context:
                    job._parse_results(history, "prompt-123", workflow)

                # Assert
                self.assertIn("Invalid ComfyUI history response", str(error_context.exception))

    async def test_download_images_rejects_duplicate_destinations(self):
        """Server outputs cannot overwrite one queue artifact path."""
        # Arrange
        api = MagicMock()
        api.download_image = AsyncMock()
        job = ComfyUIJob()
        images = [
            ComfyUIImageResult(filename="output.png", texture_type="albedo", subfolder="same"),
            ComfyUIImageResult(filename="output.png", texture_type="normal", subfolder="same"),
        ]

        # Act
        with self.assertRaisesRegex(RuntimeError, "same local artifact path"):
            await job._download_images(api, images, "prompt-123", pathlib.Path("C:/jobs"))

        # Assert
        api.download_image.assert_not_awaited()

    async def test_download_images_preserves_portable_server_filename(self):
        """A valid server filename keeps its full portable component length locally."""
        # Arrange
        api = MagicMock()
        api.download_image = AsyncMock(side_effect=lambda _image, destination: destination)
        job = ComfyUIJob()
        filename = f"{'a' * 246}.png"
        image = ComfyUIImageResult(filename=filename, texture_type="albedo")

        # Act
        await job._download_images(api, [image], "prompt-123", pathlib.Path("C:/jobs"))

        # Assert
        expected_destination = pathlib.Path("C:/jobs/outputs/prompt-123") / filename
        api.download_image.assert_awaited_once_with(image, expected_destination)
        self.assertEqual(image.path, expected_destination)

    async def test_parse_results_keeps_only_declared_final_outputs(self):
        """Preview, untyped, and undeclared node images stay outside the result contract."""
        # Arrange
        job = ComfyUIJob()
        workflow = Workflow(output_specs=[WorkflowOutput("99", "albedo")])
        history = {
            "prompt-123": {
                "outputs": {
                    "99": {
                        "images": [
                            {"filename": "preview.png", "subfolder": "", "type": "temp"},
                            {"filename": "untyped.png", "subfolder": ""},
                            {"filename": "result.png", "subfolder": "", "type": "output"},
                        ]
                    },
                    "unrelated": {"images": [{"filename": "other.png", "type": "output"}]},
                }
            }
        }

        # Act
        result = job._parse_results(history, "prompt-123", workflow)

        # Assert
        self.assertEqual([image.filename for image in result], ["result.png"])

    async def test_parse_results_rejects_missing_declared_output(self):
        """Every declared workflow texture must produce exactly one final image."""
        # Arrange
        job = ComfyUIJob()
        workflow = Workflow(
            output_specs=[WorkflowOutput("99", "albedo", order=1), WorkflowOutput("100", "normal", order=2)]
        )
        history = {"prompt-123": {"outputs": {"99": {"images": [{"filename": "albedo.png", "type": "output"}]}}}}

        # Act
        with self.assertRaisesRegex(RuntimeError, "did not produce a final image.*normal") as error_context:
            job._parse_results(history, "prompt-123", workflow)

        # Assert
        self.assertIsInstance(error_context.exception, RuntimeError)

    async def test_parse_results_rejects_multiple_final_images_for_declared_output(self):
        """A batch-producing node cannot ambiguously satisfy one declared texture output."""
        # Arrange
        job = ComfyUIJob()
        workflow = Workflow(output_specs=[WorkflowOutput("99", "albedo")])
        history = {
            "prompt-123": {
                "outputs": {
                    "99": {
                        "images": [
                            {"filename": "first.png", "type": "output"},
                            {"filename": "second.png", "type": "output"},
                        ]
                    }
                }
            }
        }

        # Act
        with self.assertRaisesRegex(RuntimeError, "multiple final images.*albedo") as error_context:
            job._parse_results(history, "prompt-123", workflow)

        # Assert
        self.assertIsInstance(error_context.exception, RuntimeError)

    async def test_serialization_preserves_workflow_identity(self):
        """Queued workflow requests retain the exact server source used for edit/reopen."""
        # Arrange
        request = _make_workflow_request(
            workflow=Workflow(
                name="Duplicate Name",
                source_type=WorkflowSourceType.USER,
                category=WorkflowCategory.API,
            )
        )

        # Act
        result = deserialize(serialize(request))

        # Assert
        self.assertEqual(result.workflow.source_type, WorkflowSourceType.USER)
        self.assertEqual(result.workflow.category, WorkflowCategory.API)

    async def test_serialization_preserves_complete_workflow_schema(self):
        """Queue persistence restores every typed model and resolver owned by a submitted workflow."""
        # Arrange
        api_workflow, full_workflow = get_test_workflow_pair()
        workflow = Workflow.from_litegraph_dict(
            api_workflow,
            full_workflow,
            name="PBRify",
            context_name="texturecraft",
        )
        workflow.source_type = WorkflowSourceType.RTX_REMIX
        workflow.category = WorkflowCategory.API
        request = _make_workflow_request(workflow=workflow)

        # Act
        restored = deserialize(serialize(request))

        # Assert
        self.assertIsInstance(restored.workflow.inputs[0].value, ConstantResolver)
        self.assertIs(restored.workflow.inputs[0].value.value_type, float)
        self.assertIsInstance(restored.workflow.inputs[1].value, ConstantResolver)
        self.assertIs(restored.workflow.inputs[1].value.value_type, str)
        self.assertIsInstance(restored.workflow.inputs[-1].value, SelectedTextureResolver)
        self.assertEqual(restored.workflow.presets, workflow.presets)
        self.assertEqual(restored.workflow.workflow_defaults, workflow.workflow_defaults)

    async def test_serialization_round_trips_typed_constant_and_context_getters(self):
        """Queue persistence preserves the exact Constant type and every registered context getter."""
        # Arrange
        resolvers = (
            ConstantResolver(True),
            ConstantResolver(3),
            ConstantResolver(0.5),
            ConstantResolver("prompt"),
            ConstantResolver(pathlib.Path("textures/source.png")),
            SelectedPrimPathResolver(),
            LayerIdentifierResolver(),
        )
        for resolver in resolvers:
            with self.subTest(resolver=type(resolver).__name__):
                # Act
                restored = deserialize(serialize(resolver))

                # Assert
                self.assertEqual(restored, resolver)
                if isinstance(resolver, ConstantResolver):
                    self.assertIs(restored.value_type, resolver.value_type)

    @patch("lightspeed.trex.comfyui.core.job.ComfyUIAPI")
    async def test_execute_orders_upload_submit_poll_download(self, api_type):
        """Execution uploads inputs before prompt submission and downloads only after completion.

        Args:
            api_type: Patched ComfyUI API constructor.
        """
        # Arrange
        call_order = []
        api = MagicMock()

        async def upload(_path, *, subfolder):
            """Record and return the mocked uploaded input image.

            Args:
                _path: Source path required by the upload callback contract.
                subfolder: Server subfolder assigned to the uploaded image.

            Returns:
                The server-side image descriptor.
            """
            call_order.append("upload")
            return {"name": "server_image.png", "subfolder": subfolder, "type": "input"}

        async def submit(_prompt, _client_id, *, extra_data):
            """Validate metadata and return the mocked prompt identifier.

            Args:
                _prompt: Prompt payload required by the submission callback contract.
                _client_id: Client identifier required by the submission callback contract.
                extra_data: Metadata attached to the submitted prompt.

            Returns:
                The mocked prompt identifier.
            """
            self.assertEqual(extra_data["extra_pnginfo"]["rtx-remix"]["subfolder"], f"rtx-remix/{job.job_id}")
            call_order.append("submit")
            return "prompt-456"

        async def poll(_prompt_id, _timeout):
            """Return a completed mocked ComfyUI history payload.

            Args:
                _prompt_id: Prompt identifier required by the polling callback contract.
                _timeout: Timeout required by the polling callback contract.

            Returns:
                A completed ComfyUI history payload.
            """
            call_order.append("poll")
            return {"prompt-456": {"outputs": {"99": {"images": [{"filename": "result.png", "type": "output"}]}}}}

        async def download(_image, destination):
            """Record and return the mocked download destination.

            Args:
                _image: Image descriptor required by the download callback contract.
                destination: Local path assigned to the downloaded image.

            Returns:
                The local download destination.
            """
            call_order.append("download")
            return destination

        api.upload_image = upload
        api.submit_prompt = submit
        api.wait_for_prompt_completion = poll
        api.download_image = download
        api_type.return_value = api
        job = ComfyUIJob()
        request = _make_workflow_request(
            input_bindings=(("68.inputs.image", "/textures/diffuse.png"),),
            prompt={"68": {"inputs": {"image": "/textures/diffuse.png"}}},
            client_id="test-client",
            output_url="C:/project/assets/ingested/comfyui/test",
            workflow=Workflow(output_specs=[WorkflowOutput("99", "albedo")]),
        )
        progress = AsyncMock()

        # Act
        await job.execute(
            pathlib.Path("C:/jobs"),
            JobInputs({ComfyUIJob.WORKFLOW_REQUEST: request}),
            progress,
        )

        # Assert
        self.assertEqual(call_order, ["upload", "submit", "poll", "download"])
