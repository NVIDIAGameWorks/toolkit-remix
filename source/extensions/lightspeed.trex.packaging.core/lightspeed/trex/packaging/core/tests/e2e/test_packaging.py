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

import filecmp
import tempfile
from os import walk
from pathlib import Path
from unittest.mock import Mock, call

import carb
import omni.client
import omni.kit.test
from lightspeed.trex.packaging.core import PackagingCore
from omni.kit.test_suite.helpers import get_test_data_path


def compare_files(fn1, fn2):
    try:  # try to compare the content to ignore CRLF/LF stuffs
        with (
            open(fn1, newline=None, encoding="utf8") as file1,
            open(fn2, newline=None, encoding="utf8") as file2,
        ):
            return file1.read() == file2.read()
    except UnicodeDecodeError:  # not a text file
        return filecmp.cmp(fn1, fn2)


class TestPackagingCoreE2E(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def test_package_valid_arguments_should_create_expected_file_structure(self):
        packaging_core = PackagingCore()

        progress_mock = Mock()
        completed_mock = Mock()

        progress_mock.side_effect = lambda *args: print(f"Progress: {args}")
        completed_mock.side_effect = lambda *args: print(f"Completed: {args}")

        _progress_sub = packaging_core.subscribe_packaging_progress(progress_mock)  # noqa F841
        _completed_sub = packaging_core.subscribe_packaging_completed(completed_mock)  # noqa F841

        # TEST LOGGING
        mdl_search_paths = carb.tokens.get_tokens_interface().resolve(
            carb.settings.get_settings().get("/renderer/mdl/searchPaths/templates")
        )
        print("MDL Search Paths:\n -", "\n - ".join(mdl_search_paths.split(";")))
        mdl_files = []
        for mdl_path in mdl_search_paths.split(";"):
            for root, _, files in walk(mdl_path):
                for file in files:
                    if file.lower().endswith(".mdl"):
                        mdl_files.append(str(Path(root) / file))
        print("MDL Files:\n -", "\n - ".join(mdl_files))
        print("Resolved MDL Files:\n -", "\n - ".join([str(Path(f).resolve()) for f in mdl_files]))
        # END TEST LOGGING

        output_dir = Path(self.temp_dir.name) / "package"

        with tempfile.TemporaryDirectory() as temp_input:
            input_project_path = get_test_data_path(__name__, "projects")
            temp_project_path = Path(temp_input) / "projects"

            result = await omni.client.copy_async(input_project_path, str(temp_project_path))
            self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

            temp_project_root = temp_project_path / "MainProject"
            temp_mod_usda = temp_project_root / "mod.usda"
            temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
            temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
            temp_sublayer = temp_project_root / "sublayer.usda"

            await packaging_core.package_async_with_exceptions(
                {
                    "context_name": "PackagingE2E",
                    "mod_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_subproject_mod),
                    ],
                    "selected_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_mod_capture_baker),
                        str(temp_sublayer),
                    ],
                    "output_directory": output_dir,
                    "mod_name": "Main Project",
                    "mod_version": "1.0.0",
                    "mod_details": "Main Test Notes",
                }
            )

        self.assertEqual(79, progress_mock.call_count)
        self.assertEqual(call(0, 1, "Filtering the selected layers..."), progress_mock.call_args_list[0])
        self.assertEqual(call(1, 1, "Filtering the selected layers..."), progress_mock.call_args_list[1])
        self.assertEqual(call(1, 3, "Filtering the selected layers..."), progress_mock.call_args_list[2])
        self.assertEqual(call(2, 3, "Filtering the selected layers..."), progress_mock.call_args_list[3])
        self.assertEqual(call(2, 3, "Filtering the selected layers..."), progress_mock.call_args_list[4])
        self.assertEqual(call(3, 3, "Filtering the selected layers..."), progress_mock.call_args_list[5])
        self.assertEqual(call(3, 3, "Filtering the selected layers..."), progress_mock.call_args_list[6])
        self.assertEqual(call(3, 3, "Filtering the selected layers..."), progress_mock.call_args_list[7])
        self.assertEqual(call(0, 13, "Redirecting dependencies..."), progress_mock.call_args_list[8])
        self.assertEqual(call(1, 13, "Redirecting dependencies..."), progress_mock.call_args_list[9])
        self.assertEqual(call(2, 13, "Redirecting dependencies..."), progress_mock.call_args_list[10])
        self.assertEqual(call(3, 13, "Redirecting dependencies..."), progress_mock.call_args_list[11])
        self.assertEqual(call(4, 13, "Redirecting dependencies..."), progress_mock.call_args_list[12])
        self.assertEqual(call(5, 13, "Redirecting dependencies..."), progress_mock.call_args_list[13])
        self.assertEqual(call(6, 13, "Redirecting dependencies..."), progress_mock.call_args_list[14])
        self.assertEqual(call(7, 13, "Redirecting dependencies..."), progress_mock.call_args_list[15])
        self.assertEqual(call(8, 13, "Redirecting dependencies..."), progress_mock.call_args_list[16])
        self.assertEqual(call(9, 13, "Redirecting dependencies..."), progress_mock.call_args_list[17])
        self.assertEqual(call(10, 13, "Redirecting dependencies..."), progress_mock.call_args_list[18])
        self.assertEqual(call(11, 13, "Redirecting dependencies..."), progress_mock.call_args_list[19])
        self.assertEqual(call(12, 13, "Redirecting dependencies..."), progress_mock.call_args_list[20])
        self.assertEqual(call(13, 13, "Redirecting dependencies..."), progress_mock.call_args_list[21])
        self.assertEqual(call(0, 10, "Creating temporary layers..."), progress_mock.call_args_list[22])
        self.assertEqual(call(1, 10, "Creating temporary layers..."), progress_mock.call_args_list[23])
        self.assertEqual(call(2, 10, "Creating temporary layers..."), progress_mock.call_args_list[24])
        self.assertEqual(call(3, 10, "Creating temporary layers..."), progress_mock.call_args_list[25])
        self.assertEqual(call(4, 10, "Creating temporary layers..."), progress_mock.call_args_list[26])
        self.assertEqual(call(5, 10, "Creating temporary layers..."), progress_mock.call_args_list[27])
        self.assertEqual(call(6, 10, "Creating temporary layers..."), progress_mock.call_args_list[28])
        self.assertEqual(call(7, 10, "Creating temporary layers..."), progress_mock.call_args_list[29])
        self.assertEqual(call(8, 10, "Creating temporary layers..."), progress_mock.call_args_list[30])
        self.assertEqual(call(9, 10, "Creating temporary layers..."), progress_mock.call_args_list[31])
        self.assertEqual(call(10, 10, "Creating temporary layers..."), progress_mock.call_args_list[32])
        self.assertEqual(call(0, 13, "Listing assets to collect..."), progress_mock.call_args_list[33])
        self.assertEqual(call(1, 13, "Listing assets to collect..."), progress_mock.call_args_list[34])
        self.assertEqual(call(2, 13, "Listing assets to collect..."), progress_mock.call_args_list[35])
        self.assertEqual(call(3, 13, "Listing assets to collect..."), progress_mock.call_args_list[36])
        self.assertEqual(call(4, 13, "Listing assets to collect..."), progress_mock.call_args_list[37])
        self.assertEqual(call(5, 13, "Listing assets to collect..."), progress_mock.call_args_list[38])
        self.assertEqual(call(6, 13, "Listing assets to collect..."), progress_mock.call_args_list[39])
        self.assertEqual(call(7, 13, "Listing assets to collect..."), progress_mock.call_args_list[40])
        self.assertEqual(call(8, 13, "Listing assets to collect..."), progress_mock.call_args_list[41])
        self.assertEqual(call(9, 13, "Listing assets to collect..."), progress_mock.call_args_list[42])
        self.assertEqual(call(10, 13, "Listing assets to collect..."), progress_mock.call_args_list[43])
        self.assertEqual(call(11, 13, "Listing assets to collect..."), progress_mock.call_args_list[44])
        self.assertEqual(call(12, 13, "Listing assets to collect..."), progress_mock.call_args_list[45])
        self.assertEqual(call(13, 13, "Listing assets to collect..."), progress_mock.call_args_list[46])
        self.assertEqual(call(0, 10, "Updating asset paths..."), progress_mock.call_args_list[47])
        self.assertEqual(call(1, 10, "Updating asset paths..."), progress_mock.call_args_list[48])
        self.assertEqual(call(2, 10, "Updating asset paths..."), progress_mock.call_args_list[49])
        self.assertEqual(call(3, 10, "Updating asset paths..."), progress_mock.call_args_list[50])
        self.assertEqual(call(4, 10, "Updating asset paths..."), progress_mock.call_args_list[51])
        self.assertEqual(call(5, 10, "Updating asset paths..."), progress_mock.call_args_list[52])
        self.assertEqual(call(6, 10, "Updating asset paths..."), progress_mock.call_args_list[53])
        self.assertEqual(call(7, 10, "Updating asset paths..."), progress_mock.call_args_list[54])
        self.assertEqual(call(8, 10, "Updating asset paths..."), progress_mock.call_args_list[55])
        self.assertEqual(call(9, 10, "Updating asset paths..."), progress_mock.call_args_list[56])
        self.assertEqual(call(10, 10, "Updating asset paths..."), progress_mock.call_args_list[57])
        self.assertEqual(call(0, 9, "Collecting assets..."), progress_mock.call_args_list[58])
        self.assertEqual(call(1, 9, "Collecting assets..."), progress_mock.call_args_list[59])
        self.assertEqual(call(2, 9, "Collecting assets..."), progress_mock.call_args_list[60])
        self.assertEqual(call(3, 9, "Collecting assets..."), progress_mock.call_args_list[61])
        self.assertEqual(call(4, 9, "Collecting assets..."), progress_mock.call_args_list[62])
        self.assertEqual(call(5, 9, "Collecting assets..."), progress_mock.call_args_list[63])
        self.assertEqual(call(6, 9, "Collecting assets..."), progress_mock.call_args_list[64])
        self.assertEqual(call(7, 9, "Collecting assets..."), progress_mock.call_args_list[65])
        self.assertEqual(call(8, 9, "Collecting assets..."), progress_mock.call_args_list[66])
        self.assertEqual(call(9, 9, "Collecting assets..."), progress_mock.call_args_list[67])
        self.assertEqual(call(0, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[68])
        self.assertEqual(call(1, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[69])
        self.assertEqual(call(2, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[70])
        self.assertEqual(call(3, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[71])
        self.assertEqual(call(4, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[72])
        self.assertEqual(call(5, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[73])
        self.assertEqual(call(6, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[74])
        self.assertEqual(call(7, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[75])
        self.assertEqual(call(8, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[76])
        self.assertEqual(call(9, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[77])
        self.assertEqual(call(10, 10, "Cleaning up temporary layers..."), progress_mock.call_args_list[78])

        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(call([], [], False), completed_mock.call_args)

        # Make sure the actual package matches the expected package
        await self.__asset_directories_equal(get_test_data_path(__name__, "package"), output_dir)

    async def __asset_directories_equal(self, expected: Path, actual: Path):
        # Make sure all the files in the expected directory are identical in the actual directory
        for dirpath, _, filenames in walk(expected):
            for filename in filenames:
                expected_path = Path(dirpath) / filename
                actual_path = actual / expected_path.relative_to(expected)
                self.assertTrue(
                    actual_path.exists(), msg=f"The file was not found in the actual package: {expected_path}"
                )
                self.assertTrue(
                    compare_files(expected_path, actual_path),
                    msg=f"The contents of the expected and actual files don't match: {expected_path}",
                )

        # Make sure no extra files exist in the actual directory
        for dirpath, _, filenames in walk(actual):
            for filename in filenames:
                actual_path = Path(dirpath) / filename
                expected_path = expected / actual_path.relative_to(actual)
                self.assertTrue(
                    expected_path.exists(), msg=f"An extra file was found in the actual package: {actual_path}"
                )
