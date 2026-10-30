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

__all__ = ["TestApplyStageWatcherE2E"]

from unittest import mock

import omni.kit.app
import omni.kit.test
import omni.usd
from omni.flux.job_queue.core.enums import ApplyDisposition

from ...jobs import apply_stage_watcher
from ...jobs.asset_replace_apply_target import AssetReplaceApplyTarget
from ...jobs.reference_apply import get_block_reason

_CONTEXT_NAME = "apply_stage_watcher_e2e"


class TestApplyStageWatcherE2E(omni.kit.test.AsyncTestCase):
    """Refresh stage-target Apply jobs when the project of their USD context opens or closes."""

    async def setUp(self) -> None:
        """Create an empty USD context and a queue with one pending and one applied job."""
        self._context = omni.usd.create_context(_CONTEXT_NAME)
        self._queue = mock.MagicMock()
        self._queue.iter_snapshot.return_value = [
            mock.MagicMock(job_id="pending", apply_disposition=ApplyDisposition.PENDING),
            mock.MagicMock(job_id="applied", apply_disposition=ApplyDisposition.APPLIED),
        ]
        self._executor = mock.MagicMock()

    async def tearDown(self) -> None:
        """Stop watching and remove the context."""
        apply_stage_watcher.get_apply_stage_watcher().destroy()
        if self._context.get_stage() is not None:
            await self._context.close_stage_async()
        omni.usd.destroy_context(_CONTEXT_NAME)

    async def test_opening_the_project_retries_pending_apply_and_closing_it_refreshes_availability(self) -> None:
        """A checked target's context reconciles pending jobs on open and refreshes Apply availability on close."""
        target = AssetReplaceApplyTarget(_CONTEXT_NAME, "C:/project/project.usda", "C:/project/project.usda", ())
        with (
            mock.patch.object(apply_stage_watcher, "get_job_queue", return_value=self._queue),
            mock.patch.object(apply_stage_watcher.handlers, "get_apply_executor", return_value=self._executor),
        ):
            # 1. Checking a target while its project is closed blocks Apply and watches the target's context.
            self.assertEqual(
                get_block_reason(target), "Open the project used to create this job before applying its outputs."
            )

            # 2. Opening a project refreshes Apply availability and retries only the pending job.
            await self._context.new_stage_async()
            await omni.kit.app.get_app().next_update_async()
            self._queue.notify_schedule_conditions_changed.assert_called_once_with()
            self._executor.request_reconcile.assert_called_once_with("pending")

            # 3. Closing it refreshes Apply availability again, so Revert shows as blocked, and retries nothing.
            await self._context.close_stage_async()
            await omni.kit.app.get_app().next_update_async()
            self.assertEqual(self._queue.notify_schedule_conditions_changed.call_count, 2)
            self._executor.request_reconcile.assert_called_once_with("pending")
