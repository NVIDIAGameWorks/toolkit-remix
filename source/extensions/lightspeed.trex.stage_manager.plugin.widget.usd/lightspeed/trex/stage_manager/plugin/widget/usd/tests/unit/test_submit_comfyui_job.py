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

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

from omni.kit.test import AsyncTestCase
from lightspeed.common.constants import LayoutFiles
from lightspeed.trex.comfyui.core.core import ComfyUISubmission, ComfyUISubmissionResult
from lightspeed.trex.stage_manager.plugin.widget.usd.extension import LightspeedStageManagerUSDWidgetPluginsExtension
from lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job import SubmitComfyUIJobActionWidgetPlugin
from omni.kit.notification_manager import NotificationStatus


class TestSubmitComfyUIJobActionWidgetPlugin(AsyncTestCase):
    """Test Stage Manager's ComfyUI job submission action."""

    async def setUp(self):
        """Reset class-owned asynchronous task state before each test."""
        SubmitComfyUIJobActionWidgetPlugin._submit_tasks.clear()
        SubmitComfyUIJobActionWidgetPlugin._pending_confirmations.clear()
        SubmitComfyUIJobActionWidgetPlugin._layout_task = None

    async def tearDown(self):
        """Cancel tasks retained by the plugin after each test."""
        SubmitComfyUIJobActionWidgetPlugin.cancel_pending_submissions()

    async def test_open_layout_uses_texturecraft_layout_resource(self):
        """Opening AI Tools retains one owner coroutine for the TextureCraft layout resource."""
        # Arrange
        layout = "texturecraft_default_layout.json"
        loaded = asyncio.get_running_loop().create_future()
        loaded.set_result(None)

        # Act
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_quicklayout_config",
                return_value=layout,
            ) as get_layout,
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.load_layout",
                return_value=loaded,
            ) as load_layout,
        ):
            SubmitComfyUIJobActionWidgetPlugin._open_ai_tools_layout()
            task = SubmitComfyUIJobActionWidgetPlugin._layout_task
            self.assertIsNotNone(task)
            await task
            await asyncio.sleep(0)

        # Assert
        get_layout.assert_called_once_with(LayoutFiles.TEXTURECRAFT)
        load_layout.assert_called_once_with(layout)
        self.assertIsNone(SubmitComfyUIJobActionWidgetPlugin._layout_task)

    async def test_open_layout_ignores_missing_layout(self):
        """Opening setup reports a missing AI Tools layout configuration."""
        # Arrange
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_quicklayout_config",
                return_value=None,
            ),
            patch("lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.load_layout") as load_layout,
            patch("lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.carb.log_warn") as log_warn,
        ):
            # Act
            SubmitComfyUIJobActionWidgetPlugin._open_ai_tools_layout()

        # Assert
        load_layout.assert_not_called()
        log_warn.assert_called_once_with("The AI Tools layout resource is unavailable.")

    async def test_open_layout_reports_shared_task_failure(self):
        """A failed shared layout task reports the failure and releases plugin ownership."""
        # Arrange
        layout_task = asyncio.get_running_loop().create_future()

        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_quicklayout_config",
                return_value="texturecraft_default_layout.json",
            ),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.load_layout",
                return_value=layout_task,
            ),
            patch("lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.carb.log_warn") as log_warn,
        ):
            # Act
            SubmitComfyUIJobActionWidgetPlugin._open_ai_tools_layout()
            layout_task.set_exception(RuntimeError("invalid layout"))
            await asyncio.sleep(0)

        # Assert
        log_warn.assert_called_once_with("Failed to open the AI Tools layout: invalid layout")
        self.assertIsNone(SubmitComfyUIJobActionWidgetPlugin._layout_task)

    async def test_submit_snapshots_explicit_paths_and_prepares_graph(self):
        """Submission copies selected paths and offloads queue persistence from its owner coroutine."""
        # Arrange
        core = MagicMock()
        graphs = [
            MagicMock(jobs=[MagicMock(skip_reason=None)]),
            MagicMock(jobs=[MagicMock(skip_reason=None)]),
        ]
        submission = ComfyUISubmission(tuple(graphs), 0)
        core.prepare_submission = AsyncMock(return_value=submission)
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(2, 0))
        item = MagicMock()
        selected_paths = ["/World/MaterialA"]

        # Act
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ) as get_core_mock,
            patch.object(SubmitComfyUIJobActionWidgetPlugin, "_is_comfy_ready", return_value=True),
        ):
            SubmitComfyUIJobActionWidgetPlugin._on_submit_comfyui_job(
                {
                    "context_name": "texturecraft",
                    "right_clicked_item": item,
                    "selected_paths": selected_paths,
                }
            )
            task = SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"]
            await task

        # Assert
        self.assertEqual(get_core_mock.call_args_list, [call("texturecraft"), call("texturecraft")])
        core.prepare_submission.assert_awaited_once_with(prim_paths=selected_paths, progress=ANY, is_cancelled=ANY)
        self.assertIsNot(core.prepare_submission.call_args.kwargs["prim_paths"], selected_paths)
        core.submit_prepared_submission.assert_awaited_once_with(submission)
        self.assertNotIn("texturecraft", SubmitComfyUIJobActionWidgetPlugin._submit_tasks)

    async def test_submit_ignores_duplicate_task_for_context(self):
        """A context cannot enqueue a second submission while one is pending."""
        # Arrange
        pending_task = MagicMock()
        pending_task.done.return_value = False
        SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"] = pending_task
        item = MagicMock()

        with (
            patch.object(SubmitComfyUIJobActionWidgetPlugin, "_is_comfy_ready", return_value=True),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.asyncio.ensure_future"
            ) as ensure_future,
        ):
            # Act
            SubmitComfyUIJobActionWidgetPlugin._on_submit_comfyui_job(
                {
                    "context_name": "texturecraft",
                    "right_clicked_item": item,
                    "selected_paths": ["/World/MaterialA"],
                }
            )

        # Assert
        ensure_future.assert_not_called()

    async def test_submit_ignores_context_with_open_skip_confirmation(self):
        """A context cannot prepare another graph while its skip dialog is open."""
        # Arrange
        SubmitComfyUIJobActionWidgetPlugin._pending_confirmations.add("texturecraft")

        with (
            patch.object(SubmitComfyUIJobActionWidgetPlugin, "_is_comfy_ready", return_value=True),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.asyncio.ensure_future"
            ) as ensure_future,
        ):
            # Act
            SubmitComfyUIJobActionWidgetPlugin._on_submit_comfyui_job(
                {
                    "context_name": "texturecraft",
                    "right_clicked_item": MagicMock(),
                    "selected_paths": ["/World/MaterialA"],
                }
            )

        # Assert
        ensure_future.assert_not_called()

    async def test_cancel_pending_submissions_retains_tasks_until_cancellation_settles(self):
        """Extension teardown retains cancelled tasks until each owner releases itself."""
        # Arrange
        started = asyncio.Event()

        async def wait_for_cancellation(*_args, **_kwargs):
            """Signal startup, then wait until the helper task is cancelled.

            Args:
                *_args: Positional arguments ignored by the cancellation helper.
                **_kwargs: Keyword arguments ignored by the cancellation helper.
            """
            started.set()
            await asyncio.Event().wait()

        core = MagicMock()
        core.prepare_submission = AsyncMock(side_effect=wait_for_cancellation)
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ),
            patch.object(SubmitComfyUIJobActionWidgetPlugin, "_is_comfy_ready", return_value=True),
        ):
            SubmitComfyUIJobActionWidgetPlugin._on_submit_comfyui_job(
                {
                    "context_name": "texturecraft",
                    "right_clicked_item": MagicMock(),
                    "selected_paths": ["/World/MaterialA"],
                }
            )
            submit_task = SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"]
            await started.wait()

        started.clear()
        layout_task = asyncio.create_task(wait_for_cancellation())
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_quicklayout_config",
                return_value="texturecraft_default_layout.json",
            ),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.load_layout",
                return_value=layout_task,
            ),
        ):
            SubmitComfyUIJobActionWidgetPlugin._open_ai_tools_layout()
            await started.wait()

        # Act
        SubmitComfyUIJobActionWidgetPlugin.cancel_pending_submissions()

        # Assert
        self.assertIs(SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"], submit_task)
        self.assertIs(SubmitComfyUIJobActionWidgetPlugin._layout_task, layout_task)
        await asyncio.gather(submit_task, layout_task, return_exceptions=True)
        await asyncio.sleep(0)
        self.assertEqual(SubmitComfyUIJobActionWidgetPlugin._submit_tasks, {})
        self.assertEqual(SubmitComfyUIJobActionWidgetPlugin._pending_confirmations, set())
        self.assertIsNone(SubmitComfyUIJobActionWidgetPlugin._layout_task)

    async def test_extension_shutdown_cancels_pending_submissions(self):
        """Plugin extension shutdown cancels Stage Manager ComfyUI submissions."""
        # Arrange
        extension = LightspeedStageManagerUSDWidgetPluginsExtension()
        factory = MagicMock()

        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.extension._get_factory_instance",
                return_value=factory,
            ),
            patch.object(SubmitComfyUIJobActionWidgetPlugin, "cancel_pending_submissions") as cancel_submissions,
        ):
            # Act
            extension.on_shutdown()

        # Assert
        cancel_submissions.assert_called_once_with()
        factory.unregister_plugins.assert_called_once_with(extension._PLUGINS)

    async def test_prepared_jobs_with_skips_require_exact_material_confirmation(self):
        """Skipped materials show the complete approved confirmation copy before queue submission."""
        # Arrange
        core = MagicMock()
        core.prepare_submission = AsyncMock(return_value=ComfyUISubmission((MagicMock(),), 1))

        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ),
            patch.object(SubmitComfyUIJobActionWidgetPlugin, "_is_comfy_ready", return_value=True),
            patch("lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job._TrexMessageDialog") as dialog,
        ):
            # Act
            SubmitComfyUIJobActionWidgetPlugin._on_submit_comfyui_job(
                {
                    "context_name": "texturecraft",
                    "right_clicked_item": MagicMock(),
                    "selected_paths": ["/World/MaterialA"],
                }
            )
            await SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"]

        # Assert
        self.assertEqual(
            dialog.call_args.args[0],
            "1 selected material does not provide the inputs required by the active workflow.\n\n"
            "These jobs will be skipped.\n\n"
            "Do you want to proceed anyway?",
        )
        self.assertIn("texturecraft", SubmitComfyUIJobActionWidgetPlugin._pending_confirmations)

    async def test_closing_skip_confirmation_allows_new_submission(self):
        """Cancelling the skipped-job dialog releases its context guard."""
        # Arrange
        SubmitComfyUIJobActionWidgetPlugin._pending_confirmations.add("texturecraft")

        # Act
        SubmitComfyUIJobActionWidgetPlugin._on_confirmation_closed("texturecraft")

        # Assert
        self.assertNotIn("texturecraft", SubmitComfyUIJobActionWidgetPlugin._pending_confirmations)

    async def test_cancelled_skip_confirmation_cannot_restart_submission(self):
        """Extension shutdown invalidates callbacks retained by an open dialog."""
        # Arrange
        submission = ComfyUISubmission((MagicMock(),), 0)
        SubmitComfyUIJobActionWidgetPlugin._pending_confirmations.add("texturecraft")
        SubmitComfyUIJobActionWidgetPlugin.cancel_pending_submissions()

        # Act
        with patch(
            "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.asyncio.ensure_future"
        ) as ensure_future:
            SubmitComfyUIJobActionWidgetPlugin._submit_prepared_submission("texturecraft", submission)

        # Assert
        ensure_future.assert_not_called()

    async def test_dialog_construction_failure_releases_confirmation_guard(self):
        """A failed confirmation dialog cannot permanently block later submissions."""
        # Arrange
        core = MagicMock()
        core.prepare_submission = AsyncMock(return_value=ComfyUISubmission((MagicMock(),), 1))

        # Act
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job._TrexMessageDialog",
                side_effect=RuntimeError("window unavailable"),
            ),
            patch("lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.post_notification"),
        ):
            await SubmitComfyUIJobActionWidgetPlugin._prepare_and_submit("texturecraft", ["/World/Material"])

        # Assert
        self.assertNotIn("texturecraft", SubmitComfyUIJobActionWidgetPlugin._pending_confirmations)

    async def test_confirmed_graph_is_submitted_by_retained_owner_task(self):
        """Confirmation schedules one retained task that emits the exact prepared submission."""
        # Arrange
        core = MagicMock()
        submission = ComfyUISubmission((MagicMock(),), 0)
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(1, 0))
        SubmitComfyUIJobActionWidgetPlugin._pending_confirmations.add("texturecraft")

        # Act
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.post_notification"
            ) as post_notification_mock,
        ):
            SubmitComfyUIJobActionWidgetPlugin._submit_prepared_submission("texturecraft", submission)
            task = SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"]
            await task

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)
        post_notification_mock.assert_called_once()
        self.assertIn("selection was added", post_notification_mock.call_args.args[0])
        self.assertNotIn("texturecraft", SubmitComfyUIJobActionWidgetPlugin._submit_tasks)

    async def test_submit_owner_reports_queue_recovery_without_technical_details(self):
        """An all-failed submission reports exact counts without exposing exception details."""
        # Arrange
        core = MagicMock()
        submission = ComfyUISubmission((MagicMock(),), 0)
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(0, 1))
        SubmitComfyUIJobActionWidgetPlugin._pending_confirmations.add("texturecraft")

        # Act
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.post_notification"
            ) as post_notification_mock,
        ):
            SubmitComfyUIJobActionWidgetPlugin._submit_prepared_submission("texturecraft", submission)
            await SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"]

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)
        post_notification_mock.assert_called_once()
        self.assertEqual(
            post_notification_mock.call_args.args[0],
            "0 selected materials were added to the AI Tools job queue. 1 selected material was not added. "
            "Check the workflow inputs and ComfyUI connection, then try again.",
        )

    async def test_submit_owner_continues_after_middle_failure_and_reports_exact_counts(self):
        """A failed material cannot block later graphs or invite duplicate successful submissions."""
        # Arrange
        core = MagicMock()
        submission = ComfyUISubmission(tuple(MagicMock(name=name) for name in ("first", "second", "third")), 0)
        core.submit_prepared_submission = AsyncMock(return_value=ComfyUISubmissionResult(2, 1))
        SubmitComfyUIJobActionWidgetPlugin._pending_confirmations.add("texturecraft")

        # Act
        with (
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.post_notification"
            ) as post_notification_mock,
        ):
            SubmitComfyUIJobActionWidgetPlugin._submit_prepared_submission("texturecraft", submission)
            await SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"]

        # Assert
        core.submit_prepared_submission.assert_awaited_once_with(submission)
        post_notification_mock.assert_called_once()
        self.assertEqual(
            post_notification_mock.call_args.args[0],
            "2 selected materials were added to the AI Tools job queue. 1 selected material was not added. "
            "To avoid duplicates, select only the failed material before trying again.",
        )
        self.assertIs(post_notification_mock.call_args.kwargs["status"], NotificationStatus.WARNING)
        self.assertEqual(len(post_notification_mock.call_args.kwargs["button_infos"]), 1)

    async def test_prepare_owner_reports_recovery_without_technical_details(self):
        """A failed preparation gives recovery guidance and releases task ownership."""
        # Arrange
        error = ValueError("No valid ComfyUI workflow selected")
        core = MagicMock()
        core.prepare_submission = AsyncMock(side_effect=error)

        # Act
        with (
            patch("lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.carb.log_warn"),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.get_comfyui_core_instance",
                return_value=core,
            ),
            patch.object(SubmitComfyUIJobActionWidgetPlugin, "_is_comfy_ready", return_value=True),
            patch(
                "lightspeed.trex.stage_manager.plugin.widget.usd.submit_comfyui_job.post_notification"
            ) as post_notification_mock,
        ):
            SubmitComfyUIJobActionWidgetPlugin._on_submit_comfyui_job(
                {
                    "context_name": "texturecraft",
                    "right_clicked_item": MagicMock(),
                    "selected_paths": ["/World/MaterialA"],
                }
            )
            await SubmitComfyUIJobActionWidgetPlugin._submit_tasks["texturecraft"]

        # Assert
        post_notification_mock.assert_called_once()
        self.assertEqual(
            post_notification_mock.call_args.args[0],
            "The selected materials could not be added to the AI Tools job queue. "
            "Check the workflow inputs and ComfyUI connection, then try again.",
        )
        self.assertNotIn("texturecraft", SubmitComfyUIJobActionWidgetPlugin._submit_tasks)
