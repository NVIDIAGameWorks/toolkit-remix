"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import filecmp
import tempfile
from os import walk
from pathlib import Path
from unittest.mock import Mock, call

import omni.kit.test
from lightspeed.trex.packaging.core import PackagingCore
from omni.kit.test_suite.helpers import get_test_data_path


def compare_files(fn1, fn2):
    try:  # try to compare the content to ignore CRLF/LF stuffs
        with open(fn1, "rt", newline=None, encoding="utf8") as file1, open(
            fn2, "rt", newline=None, encoding="utf8"
        ) as file2:
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

        _progress_sub = packaging_core.subscribe_packaging_progress(progress_mock)  # noqa F841
        _completed_sub = packaging_core.subscribe_packaging_completed(completed_mock)  # noqa F841

        output_dir = Path(self.temp_dir.name) / "package"

        await packaging_core.package_async_with_exceptions(
            {
                "context_name": "PackagingE2E",
                "mod_layer_paths": [
                    Path(get_test_data_path(__name__, "projects/MainProject/mod.usda")),
                    Path(get_test_data_path(__name__, "projects/MainProject/deps/mods/SubProject/mod.usda")),
                ],
                "selected_layer_paths": [
                    Path(get_test_data_path(__name__, "projects/MainProject/mod.usda")),
                    Path(get_test_data_path(__name__, "projects/MainProject/mod_capture_baker.usda")),
                    Path(get_test_data_path(__name__, "projects/MainProject/sublayer.usda")),
                ],
                "output_directory": output_dir,
                "mod_name": "Main Project",
                "mod_version": "1.0.0",
                "mod_details": "Main Test Notes",
            }
        )

        # Make sure the actual package matches the expected package
        await self.__asset_directories_equal(get_test_data_path(__name__, "package"), output_dir)

        self.assertEqual(79, progress_mock.call_count)
        self.assertEqual(call(0, 1, "(1/7) Filtering the selected layers..."), progress_mock.call_args_list[0])
        self.assertEqual(call(3, 3, "(1/7) Filtering the selected layers..."), progress_mock.call_args_list[7])
        self.assertEqual(call(0, 13, "(2/7) Redirecting dependencies..."), progress_mock.call_args_list[8])
        self.assertEqual(call(13, 13, "(2/7) Redirecting dependencies..."), progress_mock.call_args_list[21])
        self.assertEqual(call(0, 10, "(3/7) Creating temporary layers..."), progress_mock.call_args_list[22])
        self.assertEqual(call(10, 10, "(3/7) Creating temporary layers..."), progress_mock.call_args_list[32])
        self.assertEqual(call(0, 13, "(4/7) Listing assets to collect..."), progress_mock.call_args_list[33])
        self.assertEqual(call(13, 13, "(4/7) Listing assets to collect..."), progress_mock.call_args_list[46])
        self.assertEqual(call(0, 10, "(5/7) Updating asset paths..."), progress_mock.call_args_list[47])
        self.assertEqual(call(10, 10, "(5/7) Updating asset paths..."), progress_mock.call_args_list[57])
        self.assertEqual(call(0, 9, "(6/7) Collecting assets..."), progress_mock.call_args_list[58])
        self.assertEqual(call(9, 9, "(6/7) Collecting assets..."), progress_mock.call_args_list[67])
        self.assertEqual(call(0, 10, "(7/7) Cleaning up temporary layers..."), progress_mock.call_args_list[68])
        self.assertEqual(call(10, 10, "(7/7) Cleaning up temporary layers..."), progress_mock.call_args_list[78])

        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(call([], False), completed_mock.call_args)

    async def __asset_directories_equal(self, expected: Path, actual: Path):
        # Make sure all the files in the expected directory are identical in the actual directory
        for (dirpath, _, filenames) in walk(expected):
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
        for (dirpath, _, filenames) in walk(actual):
            for filename in filenames:
                actual_path = Path(dirpath) / filename
                expected_path = expected / actual_path.relative_to(actual)
                self.assertTrue(
                    expected_path.exists(), msg=f"An extra file was found in the actual package: {actual_path}"
                )
