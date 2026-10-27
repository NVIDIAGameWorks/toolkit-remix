"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import concurrent.futures
import time
from unittest.mock import patch

import omni.kit.app
from omni.flux.validator.mass.core import ManagerMassCore as _ManagerMassCore
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path

from .fake_plugins import register_fake_plugins as _register_fake_plugins
from .fake_plugins import unregister_fake_plugins as _unregister_fake_plugins


class TestExecutors(AsyncTestCase):
    SCHEMAS = [
        get_test_data_path(__name__, "schemas/good_material_ingestion.json"),
        get_test_data_path(__name__, "schemas/good_model_ingestion.json"),
    ]

    async def setUp(self):
        _register_fake_plugins()

    # After running each test
    async def tearDown(self):
        _unregister_fake_plugins()

    async def test_create_task_current_process_executor(self):
        core = _ManagerMassCore(schema_paths=self.SCHEMAS)
        items = core.schema_model.get_item_children(None)

        # create task will create the task and run them using the executor
        with (
            patch("omni.flux.validator.mass.core.manager._ManagerCore.deferred_run_with_exception") as run_mock,
            patch.object(core, "_on_core_added") as core_added_mock,
        ):
            await core.create_tasks(0, [items[0]._data])
            await omni.kit.app.get_app().next_update_async()
            run_mock.assert_called_once()
            core_added_mock.assert_called_once()

    async def test_create_tasks_current_process_executor(self):
        core = _ManagerMassCore(schema_paths=self.SCHEMAS)
        items = core.schema_model.get_item_children(None)

        # create task will create the task and run them using the executor
        with (
            patch("omni.flux.validator.mass.core.manager._ManagerCore.deferred_run_with_exception") as run_mock,
            patch.object(core, "_on_core_added") as core_added_mock,
        ):
            result = await core.create_tasks(0, [item._data for item in items])
            await omni.kit.app.get_app().next_update_async()
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(core_added_mock.call_count, 2)
            self.assertIsNotNone(result)

            # add others
            await core.create_tasks(0, [item._data for item in items])
            await omni.kit.app.get_app().next_update_async()
            self.assertEqual(run_mock.call_count, 4)
            self.assertEqual(core_added_mock.call_count, 4)
            self.assertIsNotNone(result)

    async def _wait_for_tasks(self, results, timeout: float = 30.0):
        """Wait for the tasks of `create_tasks()` the same way the mass validation service and CLI do.

        The callers wait one app update at a time until each returned task is done. The external process executor
        runs its tasks on a worker thread, so a fixed number of updates is not enough on a slow machine.

        Args:
            results: The `(core, task)` pairs that `create_tasks()` returns.
            timeout: Maximum time to wait, in seconds.
        """
        tasks = [task for _core, task in results]
        deadline = time.monotonic() + timeout
        while not all(task.done() for task in tasks):
            if time.monotonic() > deadline:
                # Cancel the queued tasks and let the running worker finish while the caller still mocks
                # subprocess.run, so that a late worker cannot start a real Kit process after the test fails.
                # A worker that never finishes is caught by the extension test timeout.
                for task in tasks:
                    task.cancel()
                concurrent.futures.wait(tasks)
                self.fail(f"Tasks did not finish in {timeout} seconds")
            await omni.kit.app.get_app().next_update_async()

    async def test_create_task_external_process_executor(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            core = _ManagerMassCore(schema_paths=self.SCHEMAS)
            items = core.schema_model.get_item_children(None)

            # create task will create the task and run them using the executor
            with patch.object(core, "_on_core_added") as core_added_mock:
                result = await core.create_tasks(1, [items[0]._data])
                await self._wait_for_tasks(result)
                run_mock.assert_called_once()
                core_added_mock.assert_called_once()

    async def test_create_tasks_external_process_executor(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            core = _ManagerMassCore(schema_paths=self.SCHEMAS)
            items = core.schema_model.get_item_children(None)

            # create task will create the task and run them using the executor
            with patch.object(core, "_on_core_added") as core_added_mock:
                result = await core.create_tasks(1, [item._data for item in items])
                await self._wait_for_tasks(result)
                self.assertEqual(run_mock.call_count, 2)
                self.assertEqual(core_added_mock.call_count, 2)
                self.assertIsNotNone(result)

                # add others
                result = await core.create_tasks(1, [item._data for item in items])
                await self._wait_for_tasks(result)
                self.assertEqual(run_mock.call_count, 4)
                self.assertEqual(core_added_mock.call_count, 4)
                self.assertIsNotNone(result)
