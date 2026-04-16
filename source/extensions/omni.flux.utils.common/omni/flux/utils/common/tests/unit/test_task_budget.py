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

import omni.kit.test
from omni.flux.utils.common.task_budget import AdaptiveTaskBudget


class TestAdaptiveTaskBudget(omni.kit.test.AsyncTestCase):
    def test_cold_start_uses_default_tasks(self):
        # Arrange
        budget = AdaptiveTaskBudget(default_task_count=24)

        # Act
        partition = budget.compute_partition(item_count=1000, predicate_count=2)

        # Assert
        self.assertEqual(partition.task_count, 24)
        self.assertEqual(partition.chunk_size, 42)

    def test_partition_caps_at_item_count(self):
        # Arrange
        budget = AdaptiveTaskBudget(default_task_count=24)

        # Act
        partition = budget.compute_partition(item_count=3, predicate_count=2)

        # Assert
        self.assertEqual(partition.task_count, 3)
        self.assertEqual(partition.chunk_size, 1)

    def test_overhead_budget_caps_task_count(self):
        # Arrange
        budget = AdaptiveTaskBudget(
            max_overhead_ms=100.0,
            max_overhead_ratio=0.0,
            target_chunk_ms=50.0,
            min_task_count=1,
            max_task_count=64,
            overhead_warmup_samples=0,
        )
        budget._ema_item_predicate_ms = 0.02
        budget._ema_task_overhead_ms = 20.0

        # Act
        partition = budget.compute_partition(item_count=10000, predicate_count=2)

        # Assert
        self.assertEqual(partition.task_count, 5)
        self.assertEqual(partition.chunk_size, 2000)

    def test_compute_scaled_overhead_budget_relaxes_cap(self):
        # Arrange
        budget = AdaptiveTaskBudget(
            max_overhead_ms=250.0,
            max_overhead_ratio=0.2,
            target_chunk_ms=50.0,
            min_task_count=1,
            max_task_count=64,
            overhead_warmup_samples=0,
        )
        budget._ema_item_predicate_ms = 0.02
        budget._ema_task_overhead_ms = 20.0

        # Act
        partition = budget.compute_partition(item_count=10000, predicate_count=2)

        # Assert
        self.assertEqual(partition.task_count, 8)
        self.assertEqual(partition.chunk_size, 1250)

    def test_higher_compute_cost_requests_more_tasks(self):
        # Arrange
        budget = AdaptiveTaskBudget(min_task_count=1, max_task_count=64, max_overhead_ms=10000.0, target_chunk_ms=50.0)
        budget._ema_task_overhead_ms = 0.1

        # Act
        budget._ema_item_predicate_ms = 0.001
        low_partition = budget.compute_partition(item_count=10000, predicate_count=2)

        budget._ema_item_predicate_ms = 0.01
        high_partition = budget.compute_partition(item_count=10000, predicate_count=2)

        # Assert
        self.assertGreaterEqual(high_partition.task_count, low_partition.task_count)
        self.assertLessEqual(high_partition.chunk_size, low_partition.chunk_size)

    def test_update_metrics_uses_ema(self):
        # Arrange
        budget = AdaptiveTaskBudget(ema_alpha=0.5)

        # Act
        budget.update_metrics(
            compute_ms=2000.0,
            executor_wait_ms=2300.0,
            task_count=20,
            item_count=10000,
            predicate_count=2,
        )
        first_compute = budget._ema_item_predicate_ms
        first_overhead = budget._ema_task_overhead_ms

        budget.update_metrics(
            compute_ms=1000.0,
            executor_wait_ms=1100.0,
            task_count=20,
            item_count=10000,
            predicate_count=2,
        )

        # Assert
        self.assertIsNotNone(first_compute)
        self.assertIsNotNone(first_overhead)
        self.assertLess(budget._ema_item_predicate_ms, first_compute)
        self.assertLess(budget._ema_task_overhead_ms, first_overhead)
