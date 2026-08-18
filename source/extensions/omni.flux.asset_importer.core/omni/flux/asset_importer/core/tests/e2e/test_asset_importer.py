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

from pathlib import Path
from tempfile import TemporaryDirectory

import carb
import carb.tokens
import omni.kit
import omni.kit.test
import omni.usd
from pxr import Usd
from pydantic import ValidationError

from ... import ImporterCore

_TEST_DATA_ROOT = Path(__file__).parents[6] / "data" / "tests"


class TestAssetImporterE2E(omni.kit.test.AsyncTestCase):
    """Verify batch asset conversion success and failure paths."""

    test_paths = [
        "SM_Fixture_Elevator_Interior/SM_Fixture_Elevator_Interior_Textured.fbx",
        "SM_Fixture_IndustrialValveCap/SM_Fixture_IndustrialValveCap.fbx",
        "SM_Prop_Mug/SM_Prop_Mug.fbx",
        "SM_Prop_RTX4090/SM_Prop_RTX4090_A1_01.fbx",
        "filingcabinet_1.fbx",
        "subfolder/ref.usda",
    ]

    async def setUp(self):
        """Create an importer and temporary output directory for each test."""
        self.temp_dir = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.temp_path = Path(self.temp_dir.name)
        self._importer = ImporterCore()
        self.test_config_path = _TEST_DATA_ROOT / "test_config.json"

    async def tearDown(self):
        """Remove the temporary output directory after each test."""
        self.temp_dir.cleanup()

    async def _import_one_asset(self) -> Path:
        """Import one fixture for tests that inspect the generated stage.

        Returns:
            Path to the generated USD stage.
        """
        input_path = _TEST_DATA_ROOT / TestAssetImporterE2E.test_paths[0]
        output_path = self.temp_path / input_path.with_suffix(".usd").name
        await self._importer.import_batch_async({"data": [{"input_path": str(input_path)}]}, str(self.temp_path))
        return output_path

    async def test_import_batch_with_multiple_assets_writes_outputs_and_reports_progress(self):
        """Batch conversion writes every output and reports progress."""

        def sub_finished_count_fn(_value):
            """Record a batch completion event.

            Args:
                _value: Completion status emitted by the importer.
            """
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        def sub_progress_count_fn(_value):
            """Record a batch progress event.

            Args:
                _value: Progress percentage emitted by the importer.
            """
            nonlocal sub_progress_count
            sub_progress_count.append(_value)

        sub_finished_count = []
        sub_progress_count = []

        _sub = self._importer.subscribe_batch_finished(sub_finished_count_fn)
        _sub1 = self._importer.subscribe_batch_progress(sub_progress_count_fn)

        # Build one real batch from the extension fixtures while recording its production notifications.
        config = {"data": []}
        expected_outputs = []
        inputs_exist = []
        outputs_were_absent = []
        for path in TestAssetImporterE2E.test_paths:
            input_path = _TEST_DATA_ROOT / path
            config["data"].append(
                {
                    "input_path": str(input_path),
                }
            )
            expected_outputs.append(self.temp_path / Path(path).with_suffix(".usd").name)
            inputs_exist.append(input_path.exists())
            outputs_were_absent.append(not expected_outputs[-1].exists())

        # Import every fixture into the temporary output directory through the public asynchronous API.
        conversion_succeeded = await self._importer.import_batch_async(config, str(self.temp_path))

        # Every stage is written and progress spans the complete batch from zero to one hundred percent.
        self.assertTrue(all(inputs_exist))
        self.assertTrue(all(outputs_were_absent))
        self.assertTrue(conversion_succeeded)
        self.assertTrue(all(path.exists() for path in expected_outputs))
        self.assertTrue(sub_finished_count[-1])
        self.assertEqual(0.0, sub_progress_count[0])
        self.assertEqual(50.0, sub_progress_count[3])
        self.assertEqual(100.0, sub_progress_count[-1])

    async def test_import_batch_writes_loadable_stage(self):
        """A generated USD stage can be opened by the USD runtime."""
        # Import one production fixture, then hand the resulting file to USD rather than inspecting text output.
        output_path = await self._import_one_asset()

        stage = Usd.Stage.Open(str(output_path))

        # Successful import means the actual USD runtime can construct the stage.
        self.assertIsNotNone(stage)

    async def test_import_batch_with_explicit_output_paths_writes_each_stage(self):
        """Batch conversion honors an explicit output path for each asset."""
        config = {"data": []}
        expected_outputs = []
        outputs_were_absent = []
        output_folder = self.temp_path / Path("output")
        output_folder.mkdir(exist_ok=True)
        for path in TestAssetImporterE2E.test_paths:
            output_path = output_folder / Path(path).with_suffix(".usda").name
            input_path = _TEST_DATA_ROOT / path
            config["data"].append(
                {
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                }
            )
            expected_outputs.append(output_path)
            carb.log_info(f"converting {str(input_path)} to {str(output_path)}")
            outputs_were_absent.append(not output_path.exists())

        # Submit the batch with a different explicit destination for every source asset.
        conversion_succeeded = await self._importer.import_batch_async(config, str(self.temp_path))

        # The importer honors every per-item path instead of falling back to the batch directory.
        self.assertTrue(all(outputs_were_absent))
        self.assertTrue(conversion_succeeded)
        self.assertTrue(all(path.exists() for path in expected_outputs))

    async def test_import_batch_with_json_config_writes_stages(self):
        """Batch conversion accepts a valid JSON configuration and writes its stages."""
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        # Feed the public importer its real JSON configuration fixture.
        conversion_succeeded = await self._importer.import_batch_async(self.test_config_path, str(output_folder))

        # Each configured asset produces a stage in the requested output directory.
        self.assertTrue(conversion_succeeded)
        expected_outputs = [output_folder / Path(path).with_suffix(".usd").name for path in self.test_paths]
        self.assertTrue(all(path.exists() for path in expected_outputs))

    async def test_import_batch_with_missing_json_config_returns_false(self):
        """Batch conversion rejects a missing JSON configuration file."""
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        # Send a nonexistent configuration path through the non-raising batch API.
        conversion_succeeded = await self._importer.import_batch_async("file/does/not/exist.json", str(output_folder))

        # Recoverable configuration errors are reported through the boolean result.
        self.assertFalse(conversion_succeeded)

    async def test_import_batch_with_invalid_json_config_returns_false(self):
        """Batch conversion rejects an invalid JSON configuration."""
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        # Load the malformed configuration fixture through the same public entry point.
        conversion_succeeded = await self._importer.import_batch_async(
            "${omni.flux.asset_importer.core}/data/tests/test_bad_config.json", str(output_folder)
        )

        # Invalid configuration content is rejected without producing a successful batch.
        self.assertFalse(conversion_succeeded)

    async def test_import_batch_with_error_for_missing_input_raises_validation_error(self):
        """Error-reporting batch conversion raises for a missing input asset."""
        fake_file = "file/does/not/exist.fbx"
        config = {"data": [{"input_path": fake_file}]}
        fake_file_exists = Path(fake_file).exists()

        # Use the error-reporting API so an invalid source crosses the real validation boundary.
        with self.assertRaises(ValidationError) as error_context:
            await self._importer.import_batch_async_with_error(config, str(self.temp_path))

        # The importer reports its domain validation error rather than creating or masking the missing input.
        self.assertFalse(fake_file_exists)
        self.assertIsInstance(error_context.exception, ValidationError)

    async def test_import_batch_with_missing_output_directory_returns_false(self):
        """Batch conversion rejects an output directory that does not exist."""
        output_folder = self.temp_path / Path("unmade_folder")

        # Submit valid inputs with an output directory that was deliberately never created.
        conversion_succeeded = await self._importer.import_batch_async(self.test_config_path, str(output_folder))

        # The non-raising API reports that the batch could not start.
        self.assertFalse(conversion_succeeded)
