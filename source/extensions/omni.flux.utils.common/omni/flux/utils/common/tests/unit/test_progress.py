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
import threading

import omni.kit.app
import omni.kit.test
from omni.flux.utils.common.progress import run_worker_with_latest_progress


class TestProgressWorker(omni.kit.test.AsyncTestCase):
    async def test_run_worker_with_latest_progress_cancel_should_propagate_worker_exception(self):
        # Arrange
        worker_started = threading.Event()
        finish_worker = threading.Event()
        cancel_requested = False

        def worker(_queue_progress):
            worker_started.set()
            finish_worker.wait(timeout=5)
            raise RuntimeError("worker failed")

        task = asyncio.ensure_future(
            run_worker_with_latest_progress(
                worker,
                is_cancelled=lambda: cancel_requested,
                cancelled_result=None,
                finish_worker_on_cancel=True,
            )
        )
        for _ in range(120):
            if worker_started.is_set():
                break
            await omni.kit.app.get_app().next_update_async()
        self.assertTrue(worker_started.is_set())

        # Act
        cancel_requested = True
        finish_worker.set()

        # Assert
        with self.assertRaisesRegex(RuntimeError, "worker failed"):
            await task
