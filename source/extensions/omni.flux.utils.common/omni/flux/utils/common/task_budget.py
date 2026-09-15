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

import time

__all__ = ["WorkerYieldBudget"]


# These defaults were measured against Stage Manager's 62k-item refresh: 8 ms limits uninterrupted Python work,
# checking every 256 items keeps clock overhead low, and 1 ms favors worker throughput while releasing the GIL.
_WORKER_YIELD_BUDGET_SECONDS = 0.008
_WORKER_YIELD_CHECK_INTERVAL = 256
_WORKER_YIELD_SECONDS = 0.001


class WorkerYieldBudget:
    """Pace a synchronous Python worker loop with cooperative GIL releases."""

    def __init__(self, *, yield_seconds: float = _WORKER_YIELD_SECONDS):
        """Initialize worker pacing with the requested GIL-release duration.

        Args:
            yield_seconds: Positive sleep duration after an expired work deadline.
        """
        self._checkpoint_count = 0
        self._next_yield_at = time.perf_counter() + _WORKER_YIELD_BUDGET_SECONDS
        self._yield_seconds = yield_seconds

    def checkpoint(self) -> None:
        """Yield the GIL after the current worker deadline expires."""
        checkpoint_count = self._checkpoint_count
        self._checkpoint_count += 1
        if checkpoint_count % _WORKER_YIELD_CHECK_INTERVAL:
            return

        if time.perf_counter() < self._next_yield_at:
            return

        time.sleep(self._yield_seconds)
        self._next_yield_at = time.perf_counter() + _WORKER_YIELD_BUDGET_SECONDS
