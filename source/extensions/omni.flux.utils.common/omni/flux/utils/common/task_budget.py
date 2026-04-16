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

import math
from dataclasses import dataclass

__all__ = ["AdaptiveTaskBudget", "TaskPartition"]


@dataclass(frozen=True)
class TaskPartition:
    """Computed task split for one filtering pass."""

    task_count: int
    chunk_size: int


class AdaptiveTaskBudget:
    """
    Adaptive partitioning helper for chunked background filtering workloads.

    The helper estimates how many tasks to run for the current input size and
    predicate count by balancing two goals:
    - Keep per-task compute windows short enough for responsive UI updates.
    - Cap scheduling overhead so task fanout does not dominate total time.

    Runtime feedback from `update_metrics()` is folded into exponential moving
    averages (EMAs), which are then used by `compute_partition()` on subsequent
    runs.
    """

    def __init__(
        self,
        default_task_count: int = 24,
        min_task_count: int = 8,
        max_task_count: int = 48,
        target_chunk_ms: float = 50.0,
        max_overhead_ms: float = 250.0,
        max_overhead_ratio: float = 0.2,
        ema_alpha: float = 0.25,
        overhead_warmup_samples: int = 4,
    ):
        """
        Initialize adaptive partitioning parameters.

        Args:
            default_task_count: Initial number of logical chunks used before EMAs
                are warmed up. This controls partitioning only; it is not a thread
                or worker count.
            min_task_count: Lower bound for selected chunk count during adaptive
                partitioning (clamped against item_count).
            max_task_count: Upper bound for selected chunk count during adaptive
                partitioning (clamped against item_count).
            target_chunk_ms: Target compute duration (ms) per chunk. Lower values
                bias toward more chunks for responsiveness.
            max_overhead_ms: Minimum absolute scheduling-overhead budget (ms)
                allowed when deriving an overhead cap.
            max_overhead_ratio: Relative scheduling-overhead budget as a fraction
                of predicted compute time, clamped to [0.0, 1.0].
            ema_alpha: Exponential moving average smoothing factor in [0.0, 1.0].
                Higher values react faster to recent samples.
            overhead_warmup_samples: Number of metric samples required before
                enforcing overhead-based task-count capping.
        """
        self._default_task_count = max(1, default_task_count)
        self._min_task_count = max(1, min_task_count)
        self._max_task_count = max(self._min_task_count, max_task_count)
        self._target_chunk_ms = max(1.0, target_chunk_ms)
        self._max_overhead_ms = max(1.0, max_overhead_ms)
        self._max_overhead_ratio = min(max(max_overhead_ratio, 0.0), 1.0)
        self._ema_alpha = min(max(ema_alpha, 0.0), 1.0)
        self._overhead_warmup_samples = max(0, overhead_warmup_samples)

        self._ema_item_predicate_ms: float | None = None
        self._ema_task_overhead_ms: float | None = None
        self._metrics_samples = 0

    def compute_partition(self, item_count: int, predicate_count: int) -> TaskPartition:
        """
        Compute task count and chunk size for the next filtering pass.

        Args:
            item_count: Number of items to process.
            predicate_count: Number of predicates applied per item.

        Returns:
            A `TaskPartition` with the selected task count and chunk size.
        """
        if item_count <= 0:
            return TaskPartition(task_count=0, chunk_size=1)

        if predicate_count <= 0:
            task_count = min(item_count, self._default_task_count)
            return TaskPartition(task_count=task_count, chunk_size=math.ceil(item_count / task_count))

        if self._ema_item_predicate_ms is None or self._ema_task_overhead_ms is None:
            task_count = min(item_count, self._default_task_count)
            return TaskPartition(task_count=task_count, chunk_size=math.ceil(item_count / task_count))

        predicted_compute_ms = item_count * predicate_count * self._ema_item_predicate_ms
        k_min = max(1, math.ceil(predicted_compute_ms / self._target_chunk_ms))
        overhead_budget_ms = max(self._max_overhead_ms, predicted_compute_ms * self._max_overhead_ratio)

        apply_overhead_cap = (
            self._ema_task_overhead_ms is not None and self._metrics_samples >= self._overhead_warmup_samples
        )
        if apply_overhead_cap and self._ema_task_overhead_ms > 0:
            k_max = max(1, math.floor(overhead_budget_ms / self._ema_task_overhead_ms))
        else:
            k_max = self._max_task_count

        lower_bound = min(item_count, self._min_task_count)
        upper_bound = min(item_count, self._max_task_count, k_max)
        if upper_bound < lower_bound:
            task_count = upper_bound
        else:
            task_count = min(max(k_min, lower_bound), upper_bound)

        task_count = max(1, min(task_count, item_count))
        return TaskPartition(task_count=task_count, chunk_size=math.ceil(item_count / task_count))

    def update_metrics(
        self,
        compute_ms: float,
        executor_wait_ms: float,
        task_count: int,
        item_count: int,
        predicate_count: int,
    ):
        """
        Update EMA estimates from observed execution timings.

        Args:
            compute_ms: Measured compute time spent executing chunk work.
            executor_wait_ms: Wall time spent awaiting executor completion.
            task_count: Number of tasks used for the measured run.
            item_count: Number of processed items.
            predicate_count: Number of predicates applied per item.
        """
        if item_count <= 0 or predicate_count <= 0:
            return

        item_predicate_work = item_count * predicate_count
        if item_predicate_work <= 0:
            return

        measured_item_predicate_ms = max(0.0, compute_ms) / item_predicate_work
        self._ema_item_predicate_ms = self._ema(measured_item_predicate_ms, self._ema_item_predicate_ms)

        if task_count > 0:
            overhead_total_ms = max(0.0, executor_wait_ms - compute_ms)
            measured_task_overhead_ms = overhead_total_ms / task_count
            self._ema_task_overhead_ms = self._ema(measured_task_overhead_ms, self._ema_task_overhead_ms)
            self._metrics_samples += 1

    def _ema(self, sample: float, previous: float | None) -> float:
        """Return EMA(sample) using configured alpha and prior value."""
        if previous is None:
            return sample
        return (self._ema_alpha * sample) + ((1.0 - self._ema_alpha) * previous)
