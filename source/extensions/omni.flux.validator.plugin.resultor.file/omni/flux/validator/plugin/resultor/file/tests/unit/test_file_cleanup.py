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

import os
import pathlib
import tempfile
from typing import List, Optional
from unittest.mock import PropertyMock, patch

from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.plugin.check.usd.example.print_prims import PrintPrims as _PrintPrims
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading
from pydantic import Extra


class TestFileCleanup(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))
        self.temp_dir = tempfile.TemporaryDirectory()  # noqa PLR1732

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()
        self.temp_dir.cleanup()

    async def test_run_ok(self):
        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {}},
                    }
                ],
                "resultor_plugins": [{"name": "FileCleanup", "data": {}}],
            }
        )
        with patch("omni.flux.validator.plugin.resultor.file.file_cleanup._cleanup_file") as mock_cleanup:
            # run, it should be ok
            await core.deferred_run()
            self.assertEqual(mock_cleanup.call_count, 0)

    async def test_run_ok_file_cleaned_up_no_channels(self):
        # fake some pushed data
        file_size_in_bytes = 1024
        randon_input_path = str(pathlib.Path(self.temp_dir.name) / "random_input")
        with open(randon_input_path, "wb") as fout:
            fout.write(os.urandom(file_size_in_bytes))
        randon_output_path = str(pathlib.Path(self.temp_dir.name) / "random_output")
        with open(randon_output_path, "wb") as fout:
            fout.write(os.urandom(file_size_in_bytes))

        class _Data(_PrintPrims.Data):
            data_flows: Optional[List[_InOutDataFlow]] = None

            @property
            def data_flow_compatible_name(self):
                return ["InOutData"]

            class _Config:
                extra = Extra.allow

        with (
            patch.object(_PrintPrims, "data_type", new_callable=PropertyMock) as mock_data_type,
            patch("omni.flux.validator.plugin.resultor.file.file_cleanup._cleanup_file") as mock_cleanup,
        ):
            mock_data_type.return_value = _Data

            core = _ManagerCore(
                {
                    "name": "Test",
                    "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    "check_plugins": [
                        {
                            "name": "PrintPrims",
                            "selector_plugins": [{"name": "AllPrims", "data": {}}],
                            "data": {
                                "data_flows": [
                                    {
                                        "name": "InOutData",
                                        "push_input_data": True,
                                        "input_data": [randon_input_path],
                                        "push_output_data": True,
                                        "output_data": [randon_output_path],
                                    }
                                ],
                            },
                            "context_plugin": {"name": "CurrentStage", "data": {}},
                        }
                    ],
                    "resultor_plugins": [{"name": "FileCleanup", "data": {}}],
                }
            )

            # run, it should be ok
            await core.deferred_run()

            self.assertEqual(mock_cleanup.call_count, 2)

    async def test_run_ok_file_cleaned_up_channels(self):
        # fake some pushed data
        file_size_in_bytes = 1024
        randon_input_path = str(pathlib.Path(self.temp_dir.name) / "random_input")
        with open(randon_input_path, "wb") as fout:
            fout.write(os.urandom(file_size_in_bytes))
        randon_input_path1 = str(pathlib.Path(self.temp_dir.name) / "random_input1")
        with open(randon_input_path1, "wb") as fout:
            fout.write(os.urandom(file_size_in_bytes))
        randon_output_path = str(pathlib.Path(self.temp_dir.name) / "random_output")
        with open(randon_output_path, "wb") as fout:
            fout.write(os.urandom(file_size_in_bytes))
        randon_output_path1 = str(pathlib.Path(self.temp_dir.name) / "random_output1")
        with open(randon_output_path1, "wb") as fout:
            fout.write(os.urandom(file_size_in_bytes))

        class _Data(_PrintPrims.Data):
            data_flows: Optional[List[_InOutDataFlow]] = None

            @property
            def data_flow_compatible_name(self):
                return ["InOutData"]

            class _Config:
                extra = Extra.allow

        with (
            patch.object(_PrintPrims, "data_type", new_callable=PropertyMock) as mock_data_type,
            patch("omni.flux.validator.plugin.resultor.file.file_cleanup._cleanup_file") as mock_cleanup,
        ):
            mock_data_type.return_value = _Data

            core = _ManagerCore(
                {
                    "name": "Test",
                    "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    "check_plugins": [
                        {
                            "name": "PrintPrims",
                            "selector_plugins": [{"name": "AllPrims", "data": {}}],
                            "data": {
                                "data_flows": [
                                    {
                                        "name": "InOutData",
                                        "push_input_data": True,
                                        "input_data": [randon_input_path],
                                        "push_output_data": True,
                                        "output_data": [randon_output_path],
                                        "channel": "TestChannel01",
                                    }
                                ],
                            },
                            "context_plugin": {"name": "CurrentStage", "data": {}},
                        },
                        {
                            "name": "PrintPrims",
                            "selector_plugins": [{"name": "AllPrims", "data": {}}],
                            "data": {
                                "data_flows": [
                                    {
                                        "name": "InOutData",
                                        "push_input_data": True,
                                        "input_data": [randon_input_path1],
                                        "push_output_data": True,
                                        "output_data": [randon_output_path1],
                                    }
                                ],
                            },
                            "context_plugin": {"name": "CurrentStage", "data": {}},
                        },
                    ],
                    "resultor_plugins": [{"name": "FileCleanup", "data": {"channel": "TestChannel01"}}],
                }
            )

            # run, it should be ok
            await core.deferred_run()

            self.assertEqual(mock_cleanup.call_count, 2)
