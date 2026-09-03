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

import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from repo_check_tests_written import (  # noqa: E402  isort:skip
    find_extensions_missing_tests,
    format_report,
    group_changes_by_extension,
    has_skip_label,
    parse_name_status,
)

EXTENSION_PATH_PREFIX = "source/extensions"
TEST_DIR_NAME = "tests"
EXCLUDE_PATTERNS = [
    "source/extensions/example.*",
    "source/extensions/lightspeed.trex.logic.ogn/python/nodes/*",
]


def _group(changed_files):
    """Group changed files with the settings used by the repository."""
    return group_changes_by_extension(changed_files, EXTENSION_PATH_PREFIX, EXCLUDE_PATTERNS, TEST_DIR_NAME)


class TestParseNameStatus(unittest.TestCase):
    def test_parse_name_status_with_simple_changes_returns_change_type_and_path(self):
        # Arrange
        diff_output = textwrap.dedent(
            """\
            M\tsource/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/setup.py
            A\tsource/extensions/omni.flux.utils.common/omni/flux/utils/common/new.py
            D\tsource/extensions/omni.flux.utils.common/omni/flux/utils/common/old.py
            """
        )

        # Act
        changed_files = parse_name_status(diff_output)

        # Assert
        self.assertEqual(
            changed_files,
            [
                ("M", "source/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/setup.py"),
                ("A", "source/extensions/omni.flux.utils.common/omni/flux/utils/common/new.py"),
                ("D", "source/extensions/omni.flux.utils.common/omni/flux/utils/common/old.py"),
            ],
        )

    def test_parse_name_status_with_rename_splits_into_deletion_and_addition(self):
        # Arrange
        diff_output = "R100\tsource/extensions/ext.a/a/old.py\tsource/extensions/ext.b/b/new.py\n"

        # Act
        changed_files = parse_name_status(diff_output)

        # Assert
        self.assertEqual(
            changed_files,
            [("D", "source/extensions/ext.a/a/old.py"), ("A", "source/extensions/ext.b/b/new.py")],
        )

    def test_parse_name_status_with_copy_splits_into_deletion_and_addition(self):
        # Arrange
        diff_output = "C75\tsource/extensions/ext.a/a/original.py\tsource/extensions/ext.b/b/copy.py\n"

        # Act
        changed_files = parse_name_status(diff_output)

        # Assert
        self.assertEqual(
            changed_files,
            [("D", "source/extensions/ext.a/a/original.py"), ("A", "source/extensions/ext.b/b/copy.py")],
        )

    def test_parse_name_status_with_blank_lines_ignores_them(self):
        # Arrange
        diff_output = "\nM\tsource/extensions/ext.a/a/mod.py\n\n"

        # Act
        changed_files = parse_name_status(diff_output)

        # Assert
        self.assertEqual(changed_files, [("M", "source/extensions/ext.a/a/mod.py")])


class TestFindExtensionsMissingTests(unittest.TestCase):
    def test_find_missing_with_source_only_change_flags_the_extension(self):
        # Arrange
        grouped = _group([("M", "source/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/setup.py")])

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, ["lightspeed.trex.app.setup"])

    def test_find_missing_with_source_and_test_change_flags_nothing(self):
        # Arrange
        grouped = _group(
            [
                ("M", "source/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/setup.py"),
                ("M", "source/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/tests/unit/test_setup.py"),
            ]
        )

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, [])

    def test_find_missing_with_test_only_change_flags_nothing(self):
        # Arrange
        grouped = _group(
            [("M", "source/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/tests/unit/test_setup.py")]
        )

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, [])

    def test_find_missing_with_deletion_only_change_flags_nothing(self):
        # Arrange
        grouped = _group([("D", "source/extensions/omni.flux.utils.common/omni/flux/utils/common/removed.py")])

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, [])

    def test_find_missing_with_excluded_path_flags_nothing(self):
        # Arrange
        grouped = _group(
            [
                ("M", "source/extensions/example.python_ext/example/python_ext/extension.py"),
                ("M", "source/extensions/lightspeed.trex.logic.ogn/python/nodes/generated_node.py"),
            ]
        )

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, [])

    def test_find_missing_with_non_python_change_flags_nothing(self):
        # Arrange
        grouped = _group(
            [
                ("M", "source/extensions/lightspeed.trex.app.setup/config/extension.toml"),
                ("M", "source/extensions/lightspeed.trex.app.setup/docs/CHANGELOG.md"),
            ]
        )

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, [])

    def test_find_missing_with_mixed_extensions_flags_only_the_untested_one(self):
        # Arrange
        grouped = _group(
            [
                ("M", "source/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/setup.py"),
                ("M", "source/extensions/lightspeed.trex.app.setup/lightspeed/trex/app/setup/tests/unit/test_setup.py"),
                ("M", "source/extensions/omni.flux.utils.common/omni/flux/utils/common/path_utils.py"),
            ]
        )

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, ["omni.flux.utils.common"])

    def test_find_missing_with_renamed_source_file_flags_the_receiving_extension(self):
        # Arrange
        grouped = _group(
            parse_name_status("R100\tsource/extensions/ext.a/a/moved.py\tsource/extensions/ext.b/b/moved.py\n")
        )

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, ["ext.b"])

    def test_find_missing_with_file_outside_extensions_flags_nothing(self):
        # Arrange
        grouped = _group([("M", "tools/utils/repo_check_tests_written.py")])

        # Act
        missing = find_extensions_missing_tests(grouped)

        # Assert
        self.assertEqual(missing, [])


class TestHasSkipLabel(unittest.TestCase):
    def test_has_skip_label_with_label_present_returns_true(self):
        # Arrange
        labels = "documentation,no-tests-needed,ready-for-review"

        # Act
        result = has_skip_label("no-tests-needed", labels)

        # Assert
        self.assertTrue(result)

    def test_has_skip_label_with_similar_label_returns_false(self):
        # Arrange
        labels = "no-tests-needed-later"

        # Act
        result = has_skip_label("no-tests-needed", labels)

        # Assert
        self.assertFalse(result)

    def test_has_skip_label_with_empty_labels_returns_false(self):
        # Arrange
        labels = ""

        # Act
        result = has_skip_label("no-tests-needed", labels)

        # Assert
        self.assertFalse(result)


class TestFormatReport(unittest.TestCase):
    def test_format_report_with_missing_extension_lists_the_changed_source_files(self):
        # Arrange
        grouped = _group([("M", "source/extensions/omni.flux.utils.common/omni/flux/utils/common/path_utils.py")])
        missing = find_extensions_missing_tests(grouped)

        # Act
        report = format_report(missing, grouped, TEST_DIR_NAME)

        # Assert
        self.assertIn("omni.flux.utils.common", report)
        self.assertIn("`source/extensions/omni.flux.utils.common/omni/flux/utils/common/path_utils.py`", report)
        self.assertIn("no-tests-needed", report)

    def test_format_report_with_custom_test_dir_name_names_that_directory(self):
        # Arrange
        changed_files = [("M", "source/extensions/omni.flux.utils.common/omni/flux/utils/common/path_utils.py")]
        grouped = group_changes_by_extension(changed_files, EXTENSION_PATH_PREFIX, EXCLUDE_PATTERNS, "checks")
        missing = find_extensions_missing_tests(grouped)

        # Act
        report = format_report(missing, grouped, "checks")

        # Assert
        self.assertIn("`checks/` directory", report)
        self.assertNotIn("`tests/` directory", report)


if __name__ == "__main__":
    unittest.main()
