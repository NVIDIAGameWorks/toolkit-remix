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

from lightspeed.trex.asset_pipeline.core.jobs import TextureOptimizationJob
from omni.flux.job_queue.core.job import ApplyBinding
from omni.flux.job_queue.core.serializer import deserialize, serialize
from omni.kit.test import AsyncTestCase
from pxr import Sdf

from ...apply_handler import ComfyUITextureApplyHandler
from ...enums import MeshReferenceSelection, OutputApplyBehavior, RemixType, WorkflowType
from ...models import ComfyUIApplyTarget, ComfyUIInputBinding, ComfyUIWorkflowRequest, Workflow, WorkflowOutput
from ...resolvers import AllStageMeshesResolver, AllStageTexturesResolver, SelectedMeshResolver, SelectedTextureResolver


class TestPersistenceCodecs(AsyncTestCase):
    """Test released records and current persistence contracts."""

    async def test_workflow_request_decode_released_bindings_preserves_texture_sources(self):
        """A released request that stored (port_id, source) binding pairs decodes to the current request."""
        # Arrange
        workflow = Workflow(name="Released workflow", api={})
        binding = ComfyUIInputBinding("1.inputs.image", RemixType.TEXTURE_FILE_PATH, "C:/source/albedo.png")
        current = ComfyUIWorkflowRequest({}, (binding,), "client", 300.0, None, workflow)
        envelope = json.loads(serialize(current))
        envelope["value"] = json.loads(
            serialize(
                (
                    current.prompt,
                    ((binding.port_id, binding.source),),
                    current.client_id,
                    current.timeout,
                    current.output_url,
                    current.workflow,
                )
            )
        )

        # Act
        restored = deserialize(json.dumps(envelope))

        # Assert
        self.assertEqual(restored, current)

    async def test_released_workflow_payload_decodes_without_output_group_order(self):
        """A released ten-field Workflow record decodes with an empty output group order."""
        # Arrange
        current = Workflow(name="Released workflow", api={}, group_order=["Material"])
        envelope = json.loads(serialize(current))
        envelope["value"]["value"] = envelope["value"]["value"][:10]

        # Act
        restored = deserialize(json.dumps(envelope))

        # Assert
        self.assertEqual(restored, current)
        self.assertEqual(restored.output_group_order, [])

    async def test_workflow_round_trip_preserves_display_metadata(self):
        """A workflow reopened from a queue job keeps the display name that names its job graphs."""
        # Arrange
        current = Workflow(
            name="integration_pbrify",
            api={},
            display_name="PBRify",
            description="Generates PBR maps.",
            workflow_type=WorkflowType.MATERIAL_GENERATION,
        )

        # Act
        restored = deserialize(serialize(current))

        # Assert
        self.assertEqual(restored, current)
        self.assertEqual(restored.display_name, "PBRify")

    async def test_resolver_round_trip_preserves_context(self):
        """Resolver persistence preserves the context and mesh reference choice."""
        cases = (
            (
                "selected mesh keeps the selected reference choice",
                lambda: SelectedMeshResolver(
                    context_name="texturecraft", reference_selection=MeshReferenceSelection.SELECTED
                ),
            ),
            (
                "all stage meshes keeps the all reference choice",
                lambda: AllStageMeshesResolver(
                    context_name="texturecraft", reference_selection=MeshReferenceSelection.ALL
                ),
            ),
            ("selected texture keeps context", lambda: SelectedTextureResolver(context_name="texturecraft")),
            ("all stage textures keeps context", lambda: AllStageTexturesResolver(context_name="texturecraft")),
        )
        for title, make_resolver in cases:
            with self.subTest(title=title):
                # Arrange
                resolver = make_resolver()

                # Act
                restored = deserialize(serialize(resolver))

                # Assert
                self.assertEqual(restored, resolver)

    async def test_reference_decode_rejects_malformed_payload(self):
        """Malformed reference data cannot become a restored queue value."""
        cases = (
            ("wrong container", {"asset_path": "asset.usda"}),
            ("missing field", ("asset.usda", "/Model", 0.0, 1.0)),
            ("invalid prim path type", ("asset.usda", 123, 0.0, 1.0, {})),
        )
        for title, payload in cases:
            with self.subTest(title=title):
                # Arrange
                envelope = json.loads(serialize(Sdf.Reference("asset.usda")))
                envelope["value"] = json.loads(serialize(payload))

                # Act
                with self.assertRaises(ValueError) as error_context:
                    deserialize(json.dumps(envelope))

                # Assert
                self.assertIsInstance(error_context.exception, ValueError)

    async def test_released_workflow_output_payload_decodes_as_replaced_texture(self):
        """Old output records restore without an output reference choice, a name, or a group."""
        cases = (
            ("three-field record", ("12", "albedo", 2)),
            (
                "five-field record",
                ("12", RemixType.TEXTURE_FILE_PATH, 2, "albedo", OutputApplyBehavior.REPLACE),
            ),
            (
                "six-field record",
                ("12", RemixType.TEXTURE_FILE_PATH, 2, "albedo", OutputApplyBehavior.REPLACE, ""),
            ),
        )
        for title, payload in cases:
            with self.subTest(title=title):
                # Arrange
                current = WorkflowOutput(
                    node_id="12",
                    remix_type=RemixType.TEXTURE_FILE_PATH,
                    order=2,
                    texture_type="albedo",
                    apply_behavior=OutputApplyBehavior.REPLACE,
                )
                envelope = json.loads(serialize(current))
                envelope["value"] = json.loads(serialize(payload))

                # Act
                restored = deserialize(json.dumps(envelope))

                # Assert
                self.assertEqual(restored, current)

    async def test_apply_binding_decode_released_handler_resolves_to_texture_handler(self):
        """A released record bound to ComfyUIJobApplyHandler decodes to a texture Apply handler binding."""
        # Arrange
        target = ComfyUIApplyTarget(
            "released_comfyui_handler",
            "C:/project/mod.usda",
            "C:/project/mod.usda",
            "/Material",
            (("12", "/Material/Shader.inputs:diffuse_texture"),),
        )
        binding = ApplyBinding(TextureOptimizationJob.PROCESSED_TEXTURES, ComfyUITextureApplyHandler, target)
        released = serialize(binding).replace("ComfyUITextureApplyHandler", "ComfyUIJobApplyHandler")

        # Act
        restored = deserialize(released)

        # Assert
        self.assertTrue(issubclass(restored.handler_type, ComfyUITextureApplyHandler))
        self.assertEqual(restored.output_port, binding.output_port)
        self.assertEqual(restored.target, target)
