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

from unittest.mock import Mock, patch

import omni.kit.test

from ... import task_budget


class TestWorkerYieldBudget(omni.kit.test.AsyncTestCase):
    """Test cooperative worker pacing."""

    def test_checkpoint_with_expired_deadline_sleeps_and_refreshes_deadline(self):
        """Sleep once and use a fresh post-sleep clock after an expired deadline."""
        # Arrange
        worker_time = Mock()
        worker_time.perf_counter.side_effect = (0.0, 1.0, 2.0)

        # Act
        with patch.object(task_budget, "time", worker_time, create=True):
            budget = task_budget.WorkerYieldBudget(yield_seconds=0.004)
            budget.checkpoint()

        # Assert
        worker_time.sleep.assert_called_once_with(0.004)
        self.assertGreater(budget._next_yield_at, 2.0)
        self.assertEqual(3, worker_time.perf_counter.call_count)

    def test_checkpoint_before_deadline_does_not_sleep(self):
        """Continue working without sleeping before the deadline expires."""
        # Arrange
        worker_time = Mock()
        worker_time.perf_counter.return_value = 0.0

        # Act
        with patch.object(task_budget, "time", worker_time, create=True):
            budget = task_budget.WorkerYieldBudget()
            budget.checkpoint()

        # Assert
        worker_time.sleep.assert_not_called()
        self.assertEqual(2, worker_time.perf_counter.call_count)
