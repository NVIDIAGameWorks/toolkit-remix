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

__all__ = ["TestTaskTracker"]

import asyncio

import omni.kit.test
from omni.flux.utils.common.task_tracker import TaskTracker


class TestTaskTracker(omni.kit.test.AsyncTestCase):
    async def test_a_key_runs_one_task_until_it_settles_even_after_cancel(self):
        """A second start for a running or cancelling key does nothing, and the key frees once the task settles."""
        tracker = TaskTracker()
        started = asyncio.Event()

        async def wait_forever():
            started.set()
            await asyncio.Event().wait()

        first = tracker.start("context", wait_forever, name="Submit:context")
        await started.wait()
        self.assertEqual(first.get_name(), "Submit:context")
        self.assertIsNone(tracker.start("context", wait_forever))
        self.assertIsNotNone(other := tracker.start("other", wait_forever))

        tracker.cancel_all()
        self.assertIsNone(tracker.start("context", wait_forever))
        self.assertTrue(tracker.is_running("context"))

        await asyncio.gather(first, other, return_exceptions=True)
        self.assertFalse(tracker.is_running("context"))
        self.assertEqual(tracker._tasks, {})

    async def test_a_task_cancelled_before_it_starts_frees_its_key(self):
        """The key frees even when the coroutine never ran, so its own cleanup never ran either."""
        tracker = TaskTracker()
        calls = []

        async def record():
            calls.append("ran")

        task = tracker.start(None, record)
        tracker.cancel_all()
        await asyncio.gather(task, return_exceptions=True)

        self.assertEqual(calls, [])
        self.assertTrue(task.cancelled())
        self.assertEqual(tracker._tasks, {})

    async def test_a_callers_done_callback_sees_the_key_free(self):
        """A done callback the caller adds runs after the tracker freed the key."""
        tracker = TaskTracker()
        seen = []

        async def finish():
            pass

        task = tracker.start(None, finish)
        task.add_done_callback(lambda _task: seen.append(tracker.is_running(None)))
        await task
        await asyncio.sleep(0)

        self.assertEqual(seen, [False])
        self.assertIsNotNone(tracker.start(None, finish))
