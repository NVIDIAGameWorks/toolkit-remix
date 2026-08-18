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

import pathlib
from unittest.mock import MagicMock, patch

from lightspeed.trex.asset_pipeline.core.job import TextureProcessingJob
from lightspeed.trex.asset_pipeline.core.models import (
    ProcessedTexture,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
)
from lightspeed.trex.job_queue.widget.display_adapter import TextureProcessingDisplayAdapter
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.job_queue.core.job import JobProgress
from omni.flux.job_queue.widget.display_adapter_base import (
    JobAction,
    JobDetailDirectories,
    JobDetailField,
    JobDetailSection,
)
from omni.flux.job_queue.widget.display_adapter_registry import DisplayAdapterRegistry
from omni.flux.job_queue.widget.enums import DisplayState, JobDetailSectionPlacement
from omni.kit.test import AsyncTestCase


class TestTextureProcessingDisplayAdapter(AsyncTestCase):
    """Test product-neutral shared texture-processing presentation."""

    async def test_targets_exact_shared_job_type(self):
        """Registry dispatch uses the exact reusable texture-processing class."""
        # Arrange
        adapter_type = TextureProcessingDisplayAdapter

        # Act
        contract = (adapter_type.name, adapter_type.job_type)

        # Assert
        self.assertEqual(contract[0], "texture_processing")
        self.assertIs(contract[1], TextureProcessingJob)

    async def test_registers_with_real_exact_type_registry(self):
        """The production registry accepts and resolves the explicit adapter contract."""
        # Arrange
        registry = DisplayAdapterRegistry()
        job = TextureProcessingJob()

        # Act
        registry.register(TextureProcessingDisplayAdapter)
        adapter = registry.get_adapter(job)

        # Assert
        self.assertIs(type(adapter), TextureProcessingDisplayAdapter)

    async def test_describes_texture_optimization(self):
        """The reusable adapter provides one consistent texture-optimization name."""
        # Arrange
        adapter = TextureProcessingDisplayAdapter()
        job = TextureProcessingJob(name="Texture optimization")

        # Act
        result = (
            adapter.get_source_name(job),
            adapter.get_name_display(job),
            adapter.get_name_tooltip(job),
        )

        # Assert
        self.assertEqual(
            result,
            (
                "Texture Processing",
                "Texture optimization",
                "Prepare, optimize, and publish textures for efficient use in RTX Remix.",
            ),
        )

    async def test_active_labels_use_structured_texture_progress(self):
        """Active graph aggregation receives product-facing processing labels."""
        # Arrange
        adapter = TextureProcessingDisplayAdapter()
        job = TextureProcessingJob()
        progress = JobProgress(completed=1, total=3, detail="Converting textures")

        # Act
        result = (
            adapter.get_active_status_label(job, progress),
            adapter.get_active_progress_label(job, progress),
        )

        # Assert
        self.assertEqual(result, ("Converting textures", "1 of 3 textures"))
        self.assertIsNone(adapter.get_active_progress_label(job, JobProgress(detail="Converting textures")))

    async def test_job_action_opens_local_processed_texture_directory(self):
        """The child-owned processed-texture action opens its shared local directory."""
        # Arrange
        job = TextureProcessingJob()
        queue = MagicMock()
        queue.get_job_details.return_value.outputs = {
            job.PROCESSED_TEXTURES: TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/generated/albedo.png"),
                        asset_url="C:/processed/albedo.dds",
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                )
            )
        }

        # Act
        with (
            patch("lightspeed.trex.job_queue.widget.display_adapter.get_job_queue", return_value=queue),
            patch("lightspeed.trex.job_queue.widget.display_adapter.open_file_using_os_default") as reveal,
        ):
            adapter = TextureProcessingDisplayAdapter()
            actions = adapter.get_job_actions(job, "")
            adapter.execute_action("open_processed_texture_directory", job, "")

        # Assert
        self.assertEqual(
            actions,
            (
                JobAction(
                    "open_processed_texture_directory",
                    "Reveal in File Explorer",
                    "OpenFolder",
                    "Open the processed texture directory in File Explorer.",
                    True,
                ),
            ),
        )
        reveal.assert_called_once_with(str(pathlib.Path("C:/processed")), highlight=False)
        self.assertEqual(queue.get_job_details.call_count, 2)
        queue.get_job_details.assert_called_with(job.job_id, include_values=True)

    async def test_processed_texture_action_is_owned_only_by_child_job(self):
        """Texture processing never promotes its file reveal action to the graph row."""
        # Arrange
        adapter = TextureProcessingDisplayAdapter()
        job = TextureProcessingJob()

        # Act
        actions = adapter.get_graph_actions(job, "stagecraft")

        # Assert
        self.assertEqual(actions, ())

    async def test_open_action_reopens_shared_directory_without_cycling_textures(self):
        """Repeated activation always opens the one directory containing every output."""
        # Arrange
        job = TextureProcessingJob()
        queue = MagicMock()
        queue.get_job_details.return_value.outputs = {
            job.PROCESSED_TEXTURES: TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/generated/albedo.png"),
                        asset_url="C:/processed/albedo.dds",
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="normal_ogl",
                        source_path=pathlib.Path("C:/generated/normal.png"),
                        asset_url="C:/processed/normal.dds",
                        texture_type=TextureTypes.NORMAL_OGL,
                    ),
                )
            )
        }
        adapter = TextureProcessingDisplayAdapter()

        # Act
        with (
            patch("lightspeed.trex.job_queue.widget.display_adapter.get_job_queue", return_value=queue),
            patch("lightspeed.trex.job_queue.widget.display_adapter.open_file_using_os_default") as reveal,
        ):
            action = adapter.get_job_actions(job, "")[0]
            adapter.execute_action(action.action_id, job, "")
            adapter.execute_action(action.action_id, job, "")

        # Assert
        self.assertEqual(
            action.tooltip,
            "Open the processed texture directory in File Explorer.",
        )
        self.assertEqual(
            reveal.call_args_list,
            [
                ((str(pathlib.Path("C:/processed")),), {"highlight": False}),
                ((str(pathlib.Path("C:/processed")),), {"highlight": False}),
            ],
        )

    async def test_detail_sections_expose_local_and_remote_processed_textures(self):
        """Processed textures retain every published value and own their local folder action."""
        # Arrange
        job = TextureProcessingJob()
        details = MagicMock()
        details.outputs = {
            job.PROCESSED_TEXTURES: TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/generated/albedo.png"),
                        asset_url="C:/processed/albedo.dds",
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="normal_ogl",
                        source_path=pathlib.Path("C:/generated/normal.png"),
                        asset_url="omniverse://server/project/normal.dds",
                        texture_type=TextureTypes.NORMAL_OGL,
                    ),
                )
            )
        }

        # Act
        result = TextureProcessingDisplayAdapter().get_detail_sections(job, details, "")

        # Assert
        self.assertEqual(
            result,
            (
                JobDetailSection(
                    "processed_textures",
                    "Processed textures",
                    (
                        JobDetailField(
                            "texture_processing.output.0",
                            "Albedo",
                            "C:/processed/albedo.dds",
                            "Processed texture published by the reusable asset pipeline.",
                        ),
                        JobDetailField(
                            "texture_processing.output.1",
                            "Normal Ogl",
                            "omniverse://server/project/normal.dds",
                            "Processed texture published by the reusable asset pipeline.",
                        ),
                    ),
                    JobDetailSectionPlacement.AFTER_OUTPUTS,
                    pathlib.Path("C:/processed"),
                ),
            ),
        )

    async def test_detail_directories_expose_only_generic_input_values(self):
        """Generic Inputs own their folder while processed textures use their product section."""
        # Arrange
        job = TextureProcessingJob()
        details = MagicMock()
        details.inputs = {
            job.SOURCE_TEXTURES: TextureProcessingRequest(
                items=(
                    TextureProcessingItem(
                        key="albedo",
                        path=pathlib.Path("C:/generated/albedo.png"),
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    TextureProcessingItem(
                        key="normal_ogl",
                        path=pathlib.Path("C:/generated/normal.png"),
                        texture_type=TextureTypes.NORMAL_OGL,
                    ),
                ),
                source_root=pathlib.Path("C:/generated"),
                output_url="C:/processed",
            )
        }
        details.outputs = {
            job.PROCESSED_TEXTURES: TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/generated/albedo.png"),
                        asset_url="C:/processed/albedo.dds",
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="normal_ogl",
                        source_path=pathlib.Path("C:/generated/normal.png"),
                        asset_url="C:/processed/normal.dds",
                        texture_type=TextureTypes.NORMAL_OGL,
                    ),
                )
            )
        }

        # Act
        result = TextureProcessingDisplayAdapter().get_detail_directories(job, details, "")

        # Assert
        self.assertEqual(
            result,
            JobDetailDirectories(pathlib.Path("C:/generated")),
        )

    async def test_remote_processed_texture_remains_details_only(self):
        """A remote output keeps its stable disabled action and remains visible in details."""
        # Arrange
        job = TextureProcessingJob()
        queue = MagicMock()
        queue.get_job_details.return_value.outputs = {
            job.PROCESSED_TEXTURES: TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/generated/albedo.png"),
                        asset_url="omniverse://server/project/albedo.dds",
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                )
            )
        }

        # Act
        with (
            patch("lightspeed.trex.job_queue.widget.display_adapter.get_job_queue", return_value=queue),
            patch("lightspeed.trex.job_queue.widget.display_adapter.open_file_using_os_default") as reveal,
        ):
            actions = TextureProcessingDisplayAdapter().get_job_actions(job, "")

        # Assert
        self.assertEqual(
            actions,
            (
                JobAction(
                    "open_processed_texture_directory",
                    "Reveal in File Explorer",
                    "OpenFolder",
                    "Processed textures are stored remotely and cannot be opened in File Explorer.",
                    False,
                ),
            ),
        )
        reveal.assert_not_called()

    async def test_missing_processed_texture_disables_reveal(self):
        """A queued or unsuccessful processing job has no reveal target before values exist."""
        # Arrange
        job = TextureProcessingJob()
        queue = MagicMock()
        queue.get_job_details.return_value.outputs = None

        # Act
        with patch("lightspeed.trex.job_queue.widget.display_adapter.get_job_queue", return_value=queue):
            actions = TextureProcessingDisplayAdapter().get_job_actions(job, "")

        # Assert
        self.assertEqual(
            actions,
            (
                JobAction(
                    "open_processed_texture_directory",
                    "Reveal in File Explorer",
                    "OpenFolder",
                    "Processed textures are not available yet.",
                    False,
                ),
            ),
        )

    async def test_unavailable_processed_texture_state_keeps_disabled_reveal(self):
        """A details read failure cannot remove the child action's stable slot."""
        # Arrange
        job = TextureProcessingJob()
        queue = MagicMock()
        queue.get_job_details.side_effect = RuntimeError("queue unavailable")

        # Act
        with patch("lightspeed.trex.job_queue.widget.display_adapter.get_job_queue", return_value=queue):
            actions = TextureProcessingDisplayAdapter().get_job_actions(job, "")

        # Assert
        self.assertEqual(
            actions,
            (
                JobAction(
                    "open_processed_texture_directory",
                    "Reveal in File Explorer",
                    "OpenFolder",
                    "Processed texture information is unavailable.",
                    False,
                ),
            ),
        )

    async def test_mixed_processed_texture_locations_explain_disabled_reveal(self):
        """A mixed local and remote result explains why one folder cannot represent the job."""
        # Arrange
        job = TextureProcessingJob()
        queue = MagicMock()
        queue.get_job_details.return_value.outputs = {
            job.PROCESSED_TEXTURES: TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/generated/albedo.png"),
                        asset_url="C:/processed/albedo.dds",
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="normal_ogl",
                        source_path=pathlib.Path("C:/generated/normal.png"),
                        asset_url="omniverse://server/project/normal.dds",
                        texture_type=TextureTypes.NORMAL_OGL,
                    ),
                )
            )
        }

        # Act
        with patch("lightspeed.trex.job_queue.widget.display_adapter.get_job_queue", return_value=queue):
            action = TextureProcessingDisplayAdapter().get_job_actions(job, "")[0]

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(action.tooltip, "Processed textures are split between local and remote locations.")

    async def test_multiple_processed_texture_directories_explain_disabled_reveal(self):
        """A result spanning local folders explains why one folder cannot represent the job."""
        # Arrange
        job = TextureProcessingJob()
        queue = MagicMock()
        queue.get_job_details.return_value.outputs = {
            job.PROCESSED_TEXTURES: TextureProcessingResult(
                items=(
                    ProcessedTexture(
                        key="albedo",
                        source_path=pathlib.Path("C:/generated/albedo.png"),
                        asset_url="C:/processed/albedo.dds",
                        texture_type=TextureTypes.DIFFUSE,
                    ),
                    ProcessedTexture(
                        key="normal_ogl",
                        source_path=pathlib.Path("C:/generated/normal.png"),
                        asset_url="C:/other/normal.dds",
                        texture_type=TextureTypes.NORMAL_OGL,
                    ),
                )
            )
        }

        # Act
        with patch("lightspeed.trex.job_queue.widget.display_adapter.get_job_queue", return_value=queue):
            action = TextureProcessingDisplayAdapter().get_job_actions(job, "")[0]

        # Assert
        self.assertFalse(action.enabled)
        self.assertEqual(action.tooltip, "Processed textures are stored in multiple local directories.")

    async def test_describes_processing_and_apply_states(self):
        """The shared child owns generic progress and Apply guidance."""
        # Arrange
        adapter = TextureProcessingDisplayAdapter()
        job = TextureProcessingJob()
        cases = (
            (DisplayState.WAITING_FOR_DEPENDENCIES, "Waiting for generated textures."),
            (DisplayState.IN_PROGRESS, "Optimizing and publishing textures for RTX Remix."),
            (DisplayState.READY_TO_APPLY, "The optimized textures are ready to add to the project."),
            (DisplayState.REVERTING, "Restoring the project values used before the first Apply."),
        )

        for state, expected in cases:
            with self.subTest(state=state):
                # Act
                result = adapter.get_state_tooltip(job, state, None)

                # Assert
                self.assertEqual(result, expected)

    async def test_uses_only_sanitized_queue_skip_and_apply_reasons(self):
        """Adapters display the queue's safe reason channel without reading diagnostic errors."""
        # Arrange
        adapter = TextureProcessingDisplayAdapter()
        job = TextureProcessingJob()
        cases = (
            (
                DisplayState.SKIPPED,
                "Generate Wall: This material has no albedo texture.",
                "Generate Wall: This material has no albedo texture.",
            ),
            (
                DisplayState.APPLY_FAILED,
                "Open the project used to submit this job, then try Apply again.",
                "Open the project used to submit this job, then try Apply again.",
            ),
            (
                DisplayState.REAPPLY_FAILED,
                "A texture target changed after Apply. Resolve that external edit before trying again.",
                "A texture target changed after Apply. Resolve that external edit before trying again.",
            ),
            (
                DisplayState.REVERT_FAILED,
                "The previous project values could not be restored safely.",
                "The previous project values could not be restored safely.",
            ),
        )

        for state, reason, expected in cases:
            with self.subTest(state=state):
                # Act
                result = adapter.get_state_tooltip(job, state, reason)

                # Assert
                self.assertEqual(result, expected)
