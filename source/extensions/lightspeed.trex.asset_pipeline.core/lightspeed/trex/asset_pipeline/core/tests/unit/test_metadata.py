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

import json
import pathlib
import tempfile
from unittest.mock import MagicMock, patch

import omni.flux.utils.common.path_utils as path_utils_module
import omni.kit.test
from omni.client import is_local_url
from omni.flux.utils.common.path_utils import hash_file, read_metadata

import lightspeed.trex.asset_pipeline.core.metadata as metadata_module
from lightspeed.trex.asset_pipeline.core.constants import (
    BASE_HASH_KEY,
    VALIDATION_EXTENSIONS_KEY,
    VALIDATION_PASSED_KEY,
)
from lightspeed.trex.asset_pipeline.core.metadata import (
    capture_metadata_receipt,
    get_current_validation_extensions,
    revert_metadata,
    write_input_sidecars,
    write_metadata_for_paths,
)


def _json_round_trip(value):
    """Return ``value`` after one JSON encode/decode pass.

    A metadata sidecar is JSON, so a tuple written through it reads back as a list. Comparing
    live in-memory data (which may carry tuples, e.g. an extension's ``version``) against a value
    read from a sidecar must normalize through the same encode/decode pass first.

    Args:
        value: JSON-serializable data to normalize.

    Returns:
        The value after round-tripping through ``json.dumps``/``json.loads``.
    """
    return json.loads(json.dumps(value))


class TestMetadataUtilities(omni.kit.test.AsyncTestCase):
    """Test the .meta sidecar utilities a consumer's Apply handler composes."""

    def test_get_current_validation_extensions_with_real_records_preserves_legacy_sidecar_shape(self):
        """The snapshot keeps enabled states and legacy fields, but removes local paths."""
        # Arrange
        manager = MagicMock()
        manager.get_extensions.return_value = [
            {
                "id": "omni.flux.validator.custom.alpha-9.8.7",
                "package_id": "omni.flux.validator.custom.alpha-9.8.7",
                "version": [9, 8, 7, "rc", "41"],
                "enabled": True,
                "name": "omni.flux.validator.custom.alpha",
                "title": "Custom Alpha Validator",
                "path": "D:/runtime/alpha",
            },
            {
                "id": "omni.flux.validator.custom.beta-6.5.4",
                "package_id": "omni.flux.validator.custom.beta-6.5.4",
                "version": [6, 5, 4, "beta", "23"],
                "enabled": False,
                "name": "omni.flux.validator.custom.beta",
                "title": "Custom Beta Validator",
                "path": "E:/runtime/beta",
            },
        ]
        app = MagicMock()
        app.get_extension_manager.return_value = manager

        with patch.object(metadata_module.omni.kit.app, "get_app", return_value=app):
            # Act
            extensions = get_current_validation_extensions()

        # Assert
        self.assertEqual(
            [(entry["name"], entry["version"], entry["enabled"]) for entry in extensions],
            [
                ("omni.flux.validator.custom.alpha", [9, 8, 7, "rc", "41"], True),
                ("omni.flux.validator.custom.beta", [6, 5, 4, "beta", "23"], False),
            ],
        )
        self.assertTrue(
            all(set(entry) == {"enabled", "id", "name", "package_id", "title", "version"} for entry in extensions)
        )

    def test_write_input_sidecars_writes_only_base_hash_key_for_existing_local_files(self):
        """write_input_sidecars hashes existing local inputs and writes base_hash only, no validation keys."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            input_a = temp_path / "a.png"
            input_a.write_bytes(b"a")
            input_b = temp_path / "b.png"
            input_b.write_bytes(b"bb")

            # Act
            write_input_sidecars([input_a, input_b])

            # Assert
            for path in (input_a, input_b):
                self.assertEqual(read_metadata(str(path), BASE_HASH_KEY), hash_file(str(path)))
                self.assertIsNone(read_metadata(str(path), VALIDATION_PASSED_KEY))
                self.assertIsNone(read_metadata(str(path), VALIDATION_EXTENSIONS_KEY))

    def test_write_input_sidecars_skips_missing_input_without_raising_or_writing(self):
        """A missing input is silently skipped: write_input_sidecars writes no sidecar and raises nothing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            missing_input = temp_path / "missing.png"

            # Act
            write_input_sidecars([missing_input])

            # Assert
            self.assertFalse(missing_input.with_suffix(".png.meta").exists())

    def test_write_metadata_for_paths_writes_all_three_keys_and_honors_validation_failure(self):
        """write_metadata_for_paths writes base_hash, validation_passed, and validation_extensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output = temp_path / "model.usd"
            output.write_bytes(b"USDA")
            extensions = [{"id": "omni.flux.validator.core-1.0.0", "enabled": True}]

            # Act
            write_metadata_for_paths([output], extensions, validation_passed=False)

            # Assert
            self.assertEqual(read_metadata(str(output), BASE_HASH_KEY), hash_file(str(output)))
            self.assertIs(read_metadata(str(output), VALIDATION_PASSED_KEY), False)
            self.assertEqual(read_metadata(str(output), VALIDATION_EXTENSIONS_KEY), extensions)

    def test_write_metadata_for_paths_raises_file_not_found_for_unhashable_path(self):
        """A missing output raises FileNotFoundError before metadata is written."""
        with tempfile.TemporaryDirectory() as temp_dir:
            unhashable_path = pathlib.Path(temp_dir) / "missing.dds"

            with (
                patch.object(path_utils_module.carb, "log_error"),
                self.assertRaises(FileNotFoundError) as caught,
            ):
                write_metadata_for_paths([unhashable_path], [], validation_passed=True)
            self.assertIn(str(unhashable_path), str(caught.exception))
            self.assertFalse(unhashable_path.with_suffix(".dds.meta").exists())

    def test_capture_write_revert_round_trip_restores_prior_sidecar_content(self):
        """Revert restores a sidecar's exact prior text when Apply overwrote an existing sidecar."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output = temp_path / "processed.dds"
            output.write_bytes(b"DDS ")
            meta_path = output.with_suffix(".dds.meta")
            prior_text = '{"prior": "sidecar"}'
            meta_path.write_text(prior_text)
            receipt = capture_metadata_receipt([output])

            # Act
            write_metadata_for_paths([output], [], validation_passed=True)
            revert_metadata(receipt)

            # Assert
            self.assertEqual(meta_path.read_text(), prior_text)

    def test_capture_write_revert_round_trip_deletes_sidecar_that_did_not_exist_before(self):
        """Revert deletes a sidecar that Apply created when no sidecar existed before Apply."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output = temp_path / "model.usd"
            output.write_bytes(b"USDA")
            meta_path = output.with_suffix(".usd.meta")
            receipt = capture_metadata_receipt([output])

            # Act
            write_metadata_for_paths([output], [], validation_passed=True)
            revert_metadata(receipt)

            # Assert
            self.assertFalse(meta_path.exists())

    def test_apply_equivalent_writes_local_sidecars_skips_missing_input_and_revert_restores_prior_content(self):
        """A filtered consumer writes local sidecars, skips a missing input, and Revert restores them exactly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            local_input = temp_path / "source.png"
            local_input.write_bytes(b"PNG")
            missing_input = temp_path / "missing.png"
            local_output = temp_path / "processed.dds"
            local_output.write_bytes(b"DDS ")
            input_meta = local_input.with_suffix(".png.meta")
            output_meta = local_output.with_suffix(".dds.meta")
            prior_input = '{\n  "prior": "input"\n}\n'
            prior_output = '{"prior":"output"}'
            input_meta.write_text(prior_input)
            output_meta.write_text(prior_output)

            # A consumer's Apply handler filters remote outputs before reaching these utilities; only
            # the local candidate below is ever passed to write_metadata_for_paths.
            candidate_outputs = (str(local_output), "omniverse://server/project/remote.dds")
            local_outputs = [pathlib.Path(url) for url in candidate_outputs if is_local_url(url)]
            self.assertEqual(local_outputs, [local_output])
            local_inputs = [local_input, missing_input]

            # Act
            receipt = capture_metadata_receipt([*local_outputs, *local_inputs])
            validation_extensions = get_current_validation_extensions()
            write_input_sidecars(local_inputs)
            write_metadata_for_paths(local_outputs, validation_extensions, validation_passed=False)

            # Assert
            self.assertEqual(read_metadata(str(local_output), BASE_HASH_KEY), hash_file(str(local_output)))
            self.assertIs(read_metadata(str(local_output), VALIDATION_PASSED_KEY), False)
            self.assertEqual(
                read_metadata(str(local_output), VALIDATION_EXTENSIONS_KEY),
                _json_round_trip(validation_extensions),
            )
            input_metadata = json.loads(input_meta.read_text())
            self.assertEqual(input_metadata[BASE_HASH_KEY], hash_file(str(local_input)))
            self.assertNotIn(VALIDATION_PASSED_KEY, input_metadata)
            self.assertNotIn(VALIDATION_EXTENSIONS_KEY, input_metadata)
            self.assertFalse(missing_input.with_suffix(".png.meta").exists())

            revert_metadata(receipt)
            self.assertEqual(input_meta.read_text(), prior_input)
            self.assertEqual(output_meta.read_text(), prior_output)
