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
            await core.create_tasks(0, [items[0]._data])  # noqa
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
            result = await core.create_tasks(0, [item._data for item in items])  # noqa
            await omni.kit.app.get_app().next_update_async()
            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(core_added_mock.call_count, 2)
            self.assertIsNotNone(result)

            # add others
            await core.create_tasks(0, [item._data for item in items])  # noqa
            await omni.kit.app.get_app().next_update_async()
            self.assertEqual(run_mock.call_count, 4)
            self.assertEqual(core_added_mock.call_count, 4)
            self.assertIsNotNone(result)

    async def test_create_task_external_process_executor(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            core = _ManagerMassCore(schema_paths=self.SCHEMAS)
            items = core.schema_model.get_item_children(None)

            # create task will create the task and run them using the executor
            with patch.object(core, "_on_core_added") as core_added_mock:
                await core.create_tasks(1, [items[0]._data])  # noqa
                for _ in range(len(items) * 2):
                    await omni.kit.app.get_app().next_update_async()
                run_mock.assert_called_once()
                core_added_mock.assert_called_once()

    async def test_create_tasks_external_process_executor(self):
        with patch("subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            core = _ManagerMassCore(schema_paths=self.SCHEMAS)
            items = core.schema_model.get_item_children(None)

            # create task will create the task and run them using the executor
            with patch.object(core, "_on_core_added") as core_added_mock:
                result = await core.create_tasks(1, [item._data for item in items])  # noqa
                for _ in range(len(items) * 2):
                    await omni.kit.app.get_app().next_update_async()
                self.assertEqual(run_mock.call_count, 2)
                self.assertEqual(core_added_mock.call_count, 2)
                self.assertIsNotNone(result)

                # add others
                await core.create_tasks(1, [item._data for item in items])  # noqa
                for _ in range(len(items) * 2):
                    await omni.kit.app.get_app().next_update_async()
                self.assertEqual(run_mock.call_count, 4)
                self.assertEqual(core_added_mock.call_count, 4)
                self.assertIsNotNone(result)
