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

import unittest

from tools.utils.repo_check_tests_written import (
    find_extensions_missing_tests,
    format_report,
    group_changes_by_extension,
    has_skip_label,
    is_excluded,
    parse_name_status,
)


class TestParseNameStatus(unittest.TestCase):
    def test_single_modified_file(self):
        self.assertEqual(
            parse_name_status("M\tsource/extensions/foo/a.py"),
            [("M", "source/extensions/foo/a.py")],
        )

    def test_added_and_deleted_files(self):
        self.assertEqual(
            parse_name_status("A\tnew.py\nD\told.py"),
            [("A", "new.py"), ("D", "old.py")],
        )

    def test_rename_is_split_into_deletion_and_addition(self):
        self.assertEqual(
            parse_name_status("R100\tsource/extensions/foo/a.py\tsource/extensions/bar/a.py"),
            [("D", "source/extensions/foo/a.py"), ("A", "source/extensions/bar/a.py")],
        )

    def test_copy_is_split_into_deletion_and_addition(self):
        self.assertEqual(
            parse_name_status("C075\told/a.py\tnew/a.py"),
            [("D", "old/a.py"), ("A", "new/a.py")],
        )

    def test_blank_lines_are_ignored(self):
        self.assertEqual(parse_name_status("\nM\tx.py\n\n"), [("M", "x.py")])

    def test_empty_output_returns_empty_list(self):
        self.assertEqual(parse_name_status(""), [])


class TestIsExcluded(unittest.TestCase):
    def test_matching_pattern_excludes_file(self):
        self.assertTrue(is_excluded("source/pythonapps/thing.py", ["source/pythonapps/*"]))

    def test_star_crosses_directory_separators(self):
        # fnmatch's `*` matches `/`, so the whole subtree below the pattern is excluded.
        self.assertTrue(is_excluded("source/pythonapps/a/b/c.py", ["source/pythonapps/*"]))

    def test_non_matching_pattern_does_not_exclude_file(self):
        self.assertFalse(is_excluded("source/extensions/foo/a.py", ["source/pythonapps/*"]))

    def test_no_patterns_excludes_nothing(self):
        self.assertFalse(is_excluded("source/extensions/foo/a.py", []))


class TestGroupChangesByExtension(unittest.TestCase):
    prefix = "source/extensions"

    def _group(self, changed_files, exclude_patterns=None):
        return group_changes_by_extension(
            changed_files, self.prefix, exclude_patterns or [], "tests"
        )

    def test_source_and_tests_are_grouped_per_extension(self):
        grouped = self._group([
            ("M", "source/extensions/foo/a.py"),
            ("M", "source/extensions/foo/tests/test_a.py"),
        ])
        self.assertEqual(
            grouped,
            {
                "foo": {
                    "source": ["source/extensions/foo/a.py"],
                    "tests": ["source/extensions/foo/tests/test_a.py"],
                }
            },
        )

    def test_multiple_extensions_are_kept_separate(self):
        grouped = self._group([
            ("M", "source/extensions/foo/a.py"),
            ("A", "source/extensions/bar/b.py"),
        ])
        self.assertEqual(set(grouped), {"foo", "bar"})
        self.assertEqual(grouped["foo"]["source"], ["source/extensions/foo/a.py"])
        self.assertEqual(grouped["bar"]["source"], ["source/extensions/bar/b.py"])

    def test_deletions_are_dropped(self):
        # Removing code must not create an obligation to write tests.
        self.assertEqual(self._group([("D", "source/extensions/foo/a.py")]), {})

    def test_excluded_files_are_ignored(self):
        grouped = self._group(
            [("M", "source/extensions/foo/a.py")],
            exclude_patterns=["source/extensions/foo/*"],
        )
        self.assertEqual(grouped, {})

    def test_non_python_files_are_ignored(self):
        self.assertEqual(self._group([("M", "source/extensions/foo/readme.md")]), {})

    def test_files_outside_the_prefix_are_ignored(self):
        self.assertEqual(self._group([("M", "tools/utils/thing.py")]), {})

    def test_file_directly_under_the_prefix_is_ignored(self):
        # Not nested inside an extension directory, so it cannot belong to one.
        self.assertEqual(self._group([("M", "source/extensions/loose.py")]), {})

    def test_nested_test_directory_counts_as_tests(self):
        grouped = self._group([("A", "source/extensions/foo/unit/tests/test_x.py")])
        self.assertEqual(grouped["foo"]["tests"], ["source/extensions/foo/unit/tests/test_x.py"])

    def test_source_file_whose_name_contains_tests_is_not_a_test(self):
        grouped = self._group([("M", "source/extensions/foo/tests_helpers/util.py")])
        self.assertEqual(grouped["foo"]["source"], ["source/extensions/foo/tests_helpers/util.py"])
        self.assertEqual(grouped["foo"]["tests"], [])


class TestFindExtensionsMissingTests(unittest.TestCase):
    def test_source_without_tests_is_reported(self):
        grouped = {"foo": {"source": ["source/extensions/foo/a.py"], "tests": []}}
        self.assertEqual(find_extensions_missing_tests(grouped), ["foo"])

    def test_source_with_tests_is_not_reported(self):
        grouped = {"foo": {"source": ["a.py"], "tests": ["tests/test_a.py"]}}
        self.assertEqual(find_extensions_missing_tests(grouped), [])

    def test_tests_only_change_is_not_reported(self):
        grouped = {"foo": {"source": [], "tests": ["tests/test_a.py"]}}
        self.assertEqual(find_extensions_missing_tests(grouped), [])

    def test_results_are_sorted(self):
        grouped = {
            "zeta": {"source": ["z.py"], "tests": []},
            "alpha": {"source": ["a.py"], "tests": []},
        }
        self.assertEqual(find_extensions_missing_tests(grouped), ["alpha", "zeta"])


class TestFormatReport(unittest.TestCase):
    def test_report_lists_extension_and_its_source_files(self):
        grouped = {"foo": {"source": ["source/extensions/foo/b.py", "source/extensions/foo/a.py"], "tests": []}}
        report = format_report(["foo"], grouped, "tests")
        self.assertIn("**foo**", report)
        self.assertIn("source/extensions/foo/a.py", report)
        self.assertIn("source/extensions/foo/b.py", report)

    def test_report_mentions_the_skip_label_remedy(self):
        report = format_report([], {}, "tests")
        self.assertIn("not a merge blocker", report)
        self.assertIn("`no-tests-needed`", report)

    def test_source_files_are_listed_sorted(self):
        grouped = {"foo": {"source": ["source/extensions/foo/z.py", "source/extensions/foo/a.py"], "tests": []}}
        report = format_report(["foo"], grouped, "tests")
        self.assertLess(report.index("a.py"), report.index("z.py"))


class TestHasSkipLabel(unittest.TestCase):
    def test_label_present(self):
        self.assertTrue(has_skip_label("no-tests-needed", "bug,no-tests-needed,urgent"))

    def test_label_present_with_surrounding_whitespace(self):
        self.assertTrue(has_skip_label("no-tests-needed", "bug, no-tests-needed ,urgent"))

    def test_label_absent(self):
        self.assertFalse(has_skip_label("no-tests-needed", "bug,urgent"))

    def test_empty_label_list(self):
        self.assertFalse(has_skip_label("no-tests-needed", ""))

    def test_empty_skip_label(self):
        self.assertFalse(has_skip_label("", "no-tests-needed"))

    def test_substring_label_does_not_match(self):
        # Labels are matched exactly, not as substrings.
        self.assertFalse(has_skip_label("no-tests-needed", "no-tests-needed-extra"))


if __name__ == "__main__":
    unittest.main()
