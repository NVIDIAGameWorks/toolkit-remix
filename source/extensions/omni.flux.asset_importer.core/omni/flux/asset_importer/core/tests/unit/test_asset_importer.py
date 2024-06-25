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

from pathlib import Path
from tempfile import TemporaryDirectory

import carb
import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.asset_importer.core import ImporterCore
from pxr import Usd
from pydantic.error_wrappers import ValidationError

# import subprocess


class TestAssetImporter(omni.kit.test.AsyncTestCase):
    test_paths = [
        (
            "source/extensions/omni.flux.asset_importer.core/data/tests/SM_Fixture_Elevator_Interior"
            "/SM_Fixture_Elevator_Interior_Textured.fbx"
        ),
        (
            "source/extensions/omni.flux.asset_importer.core/data/tests/SM_Fixture_IndustrialValveCap"
            "/SM_Fixture_IndustrialValveCap.fbx"
        ),
        "source/extensions/omni.flux.asset_importer.core/data/tests/SM_Prop_Mug/SM_Prop_Mug.fbx",
        "source/extensions/omni.flux.asset_importer.core/data/tests/SM_Prop_RTX4090/SM_Prop_RTX4090_A1_01.fbx",
        "source/extensions/omni.flux.asset_importer.core/data/tests/filingcabinet_1.fbx",
        "source/extensions/omni.flux.asset_importer.core/data/tests/subfolder/ref.usda",
    ]

    # Before running each test
    async def setUp(self):
        self.temp_dir = TemporaryDirectory()  # noqa PLR1732
        self.temp_path = Path(self.temp_dir.name)
        self._importer = ImporterCore()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()

    async def test_batch_conversion(self):
        def sub_finished_count_fn(_value):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        def sub_progress_count_fn(_value):
            nonlocal sub_progress_count
            sub_progress_count.append(_value)

        sub_finished_count = []
        sub_progress_count = []

        _sub = self._importer.subscribe_batch_finished(sub_finished_count_fn)  # noqa
        _sub1 = self._importer.subscribe_batch_progress(sub_progress_count_fn)  # noqa

        config = {"data": []}
        expected_outputs = []
        for path in TestAssetImporter.test_paths:
            config["data"].append(
                {
                    "input_path": path,
                }
            )
            expected_outputs.append(self.temp_path / Path(path).with_suffix(".usd").name)
            self.assertTrue(Path(path).exists())
            self.assertFalse(expected_outputs[-1].exists())

        self.assertTrue(await self._importer.import_batch_async(config, str(self.temp_path)))

        for path in expected_outputs:
            self.assertTrue(path.exists())
            stage = Usd.Stage.Open(str(path))
            self.assertIsNotNone(stage)

        self.assertTrue(sub_finished_count[-1])
        self.assertEqual(0.0, sub_progress_count[0])
        self.assertEqual(50.0, sub_progress_count[3])
        self.assertEqual(100.0, sub_progress_count[-1])

    async def test_batch_conversion_separate_folders(self):
        config = {"data": []}
        expected_outputs = []
        output_folder = self.temp_path / Path("output")
        output_folder.mkdir(exist_ok=True)
        for path in TestAssetImporter.test_paths:
            output_path = output_folder / Path(path).with_suffix(".usda").name
            config["data"].append(
                {
                    "input_path": path,
                    "output_path": output_path,
                }
            )
            expected_outputs.append(output_path)
            carb.log_info("converting " + path + " to " + str(expected_outputs[-1]))
            self.assertFalse(expected_outputs[-1].exists())

        self.assertTrue(await self._importer.import_batch_async(config, str(self.temp_path)))

        for path in expected_outputs:
            self.assertTrue(path.exists())
            stage = Usd.Stage.Open(str(path))
            self.assertIsNotNone(stage)

    async def test_batch_conversion_json(self):
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        self.assertTrue(
            await self._importer.import_batch_async(
                "source/extensions/omni.flux.asset_importer.core/data/tests/test_config.json", str(output_folder)
            )
        )

        for input_path in TestAssetImporter.test_paths:
            path = output_folder / Path(input_path).with_suffix(".usd").name
            self.assertTrue(path.exists())
            stage = Usd.Stage.Open(str(path))
            self.assertIsNotNone(stage)

    async def test_batch_conversion_no_json(self):
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        self.assertFalse(await self._importer.import_batch_async("file/does/not/exist.json", str(output_folder)))

    async def test_batch_conversion_bad_json(self):
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        self.assertFalse(
            await self._importer.import_batch_async(
                "source/extensions/omni.flux.asset_importer.core/data/tests/test_bad_config.json", str(output_folder)
            )
        )

    async def test_fail_batch_conversion(self):
        fake_file = "file/does/not/exist.fbx"
        config = {"data": [{"input_path": fake_file}]}
        self.assertFalse(Path(fake_file).exists())

        with self.assertRaises(ValidationError):
            await self._importer.import_batch_async_with_error(config, str(self.temp_path))

    async def test_bad_output_folder(self):
        output_folder = self.temp_path / Path("unmade_folder")

        self.assertFalse(
            await self._importer.import_batch_async(
                "source/extensions/omni.flux.asset_importer.core/data/tests/test_config.json", str(output_folder)
            )
        )

    # TODO test the CLI parsing - is this even possible?
    # async def test_command_line_json(self):
    #     output_folder = self.temp_path / Path("json")
    #     cmd = ""
    #     if platform.system() == "Windows":
    #         cmd = (
    #             "_build\windows-x86_64\release\omni.flux.app.asset_importer_cli.bat -c"
    #             " source\extensions\omni.flux.asset_importer.core\data\tests\test_config.json -d "
    #             + str(output_folder)
    #         )
    #     else:
    #         cmd = (
    #             "_build/windows-x86_64/release/omni.flux.app.asset_importer_cli.sh -c"
    #             " source/extensions/omni.flux.asset_importer.core/data/tests/test_config.json -d "
    #             + str(output_folder)
    #         )

    #     subprocess.check_call(cmd)

    #     for input_path in TestAssetImporter.test_paths:
    #         path = output_folder / Path(input_path).with_suffix(".usd").name
    #         self.assertTrue(path.exists())
    #         stage = Usd.Stage.Open(str(path))
    #         self.assertIsNotNone(stage)
