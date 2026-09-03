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

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

NOTE_MARKER = "<!-- check-tests-written -->"
EXISTING_NOTE = f'[{{"id":555,"body":"{NOTE_MARKER}\\nold report"}}]'
UNRELATED_NOTE = '[{"id":111,"body":"looks good to me"}]'


class TestCommentMissingTests(unittest.TestCase):
    def test_comment_with_report_and_no_existing_note_creates_a_note(self):
        # Arrange
        environment, paths = self.__create_environment(report="- **ext.a** (1 changed source file(s))")

        # Act
        result = self.__run(environment, paths)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(paths["curl_log"].read_text(encoding="utf-8").splitlines(), ["POST notes"])
        self.assertIn(NOTE_MARKER, paths["curl_body"].read_text(encoding="utf-8"))
        self.assertIn("ext.a", paths["curl_body"].read_text(encoding="utf-8"))

    def test_comment_with_report_and_existing_note_updates_that_note(self):
        # Arrange
        environment, paths = self.__create_environment(
            report="- **ext.a** (1 changed source file(s))",
            notes_page_1=EXISTING_NOTE,
        )

        # Act
        result = self.__run(environment, paths)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(paths["curl_log"].read_text(encoding="utf-8").splitlines(), ["PUT 555"])

    def test_comment_without_report_and_existing_note_resolves_that_note(self):
        # Arrange
        environment, paths = self.__create_environment(report=None, notes_page_1=EXISTING_NOTE)

        # Act
        result = self.__run(environment, paths)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(paths["curl_log"].read_text(encoding="utf-8").splitlines(), ["PUT 555"])
        self.assertIn("Test check passed", paths["curl_body"].read_text(encoding="utf-8"))

    def test_comment_without_report_and_no_existing_note_stays_silent(self):
        # Arrange
        environment, paths = self.__create_environment(report=None, notes_page_1=UNRELATED_NOTE)

        # Act
        result = self.__run(environment, paths)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(paths["curl_log"].exists())

    def test_comment_with_marked_note_on_a_later_page_updates_that_note(self):
        # Arrange
        environment, paths = self.__create_environment(
            report="- **ext.a** (1 changed source file(s))",
            notes_page_1=UNRELATED_NOTE,
            notes_page_2=EXISTING_NOTE,
        )

        # Act
        result = self.__run(environment, paths)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(paths["curl_log"].read_text(encoding="utf-8").splitlines(), ["PUT 555"])

    def test_comment_without_token_skips_without_failing(self):
        # Arrange
        environment, paths = self.__create_environment(report="- **ext.a** (1 changed source file(s))")
        del environment["TOOLKIT_GITLAB_MR_NOTE_TOKEN"]

        # Act
        result = self.__run(environment, paths)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Skipping the merge request comment", result.stdout)
        self.assertFalse(paths["curl_log"].exists())

    def __run(self, environment: dict[str, str], paths: dict[str, Path]) -> subprocess.CompletedProcess:
        """Run the commenter against the stubbed curl."""
        return subprocess.run(
            [
                "bash",
                str(Path(__file__).with_name("comment_missing_tests.sh")),
                str(paths["report"]),
            ],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

    def __create_environment(
        self,
        report: str | None,
        notes_page_1: str = "[]",
        notes_page_2: str = "[]",
    ) -> tuple[dict[str, str], dict[str, Path]]:
        root = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)

        fake_curl_path = root / "curl"
        fake_curl_path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail

                method="GET"
                page=""
                body=""
                url=""
                previous=""
                for argument in "$@"; do
                    if [ "${previous}" = "-X" ]; then
                        method="${argument}"
                    fi
                    case "${argument}" in
                        page=*) page="${argument#page=}" ;;
                        body=*) body="${argument#body=}" ;;
                        http*) url="${argument}" ;;
                    esac
                    previous="${argument}"
                done

                if [ "${method}" = "GET" ]; then
                    page_variable="FAKE_NOTES_PAGE_${page}"
                    printf '%s\\n' "${!page_variable:-[]}"
                    exit 0
                fi

                printf '%s %s\\n' "${method}" "${url##*/}" >> "${FAKE_CURL_LOG:?FAKE_CURL_LOG must be set}"
                printf '%s\\n' "${body}" > "${FAKE_CURL_BODY:?FAKE_CURL_BODY must be set}"
                printf '%s\\n' '{}'
                """
            ),
            encoding="utf-8",
        )
        fake_curl_path.chmod(0o755)

        report_path = root / "missing-tests.md"
        if report is not None:
            report_path.write_text(report, encoding="utf-8")

        paths = {
            "report": report_path,
            "curl_log": root / "curl.log",
            "curl_body": root / "curl_body.txt",
        }
        environment = {
            **os.environ,
            "CI_API_V4_URL": "https://gitlab.example.com/api/v4",
            "CI_MERGE_REQUEST_IID": "17",
            "CI_PROJECT_ID": "7",
            "FAKE_CURL_BODY": str(paths["curl_body"]),
            "FAKE_CURL_LOG": str(paths["curl_log"]),
            "FAKE_NOTES_PAGE_1": notes_page_1,
            "FAKE_NOTES_PAGE_2": notes_page_2,
            "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
            "TOOLKIT_GITLAB_MR_NOTE_TOKEN": "test-token",
        }
        return environment, paths


if __name__ == "__main__":
    unittest.main()
