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
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


class TestNotifyRemixTargetDepBot(unittest.TestCase):
    def test_notify_no_updates_with_comma_separated_always_channels_posts_to_each_channel(self):
        # Arrange
        environment, curl_log_path = self.__create_environment(
            always_channels="C_TOOLS,C_CI",
            failure_channels="C_RTX",
        )

        # Act
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("notify_remix_target_dep_bot.sh")), "no-updates"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(curl_log_path.read_text(encoding="utf-8").splitlines(), ["C_TOOLS", "C_CI"])

    def test_notify_scheduled_failure_with_failure_channels_posts_to_always_and_failure_channels(self):
        # Arrange
        environment, curl_log_path = self.__create_environment(
            always_channels="C_TOOLS",
            failure_channels="C_RTX,C_RENDERING",
        )

        # Act
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("notify_remix_target_dep_bot.sh")), "scheduled-failure"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            curl_log_path.read_text(encoding="utf-8").splitlines(),
            ["C_TOOLS", "C_RTX", "C_RENDERING"],
        )

    def test_notify_scheduled_failure_with_duplicate_channels_posts_once_per_unique_channel(self):
        # Arrange
        environment, curl_log_path = self.__create_environment(
            always_channels="C_TOOLS,C_RTX",
            failure_channels="C_RTX,C_TOOLS,C_RENDERING",
        )

        # Act
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("notify_remix_target_dep_bot.sh")), "scheduled-failure"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            curl_log_path.read_text(encoding="utf-8").splitlines(),
            ["C_TOOLS", "C_RTX", "C_RENDERING"],
        )

    def test_notify_no_updates_when_first_channel_post_fails_continues_to_later_channels(self):
        # Arrange
        environment, curl_log_path = self.__create_environment(
            always_channels="C_INVALID,C_TOOLS",
            failure_channels="",
            failed_channel="C_INVALID",
        )

        # Act
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("notify_remix_target_dep_bot.sh")), "no-updates"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

        # Assert
        self.assertEqual(result.returncode, 1)
        self.assertIn("Slack notification failed: channel_not_found", result.stderr)
        self.assertEqual(curl_log_path.read_text(encoding="utf-8").splitlines(), ["C_INVALID", "C_TOOLS"])

    def test_notify_no_updates_with_trailing_comma_rejects_empty_channel(self):
        # Arrange
        environment, curl_log_path = self.__create_environment(
            always_channels="C_TOOLS,",
            failure_channels="",
        )

        # Act
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("notify_remix_target_dep_bot.sh")), "no-updates"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

        # Assert
        self.assertEqual(result.returncode, 1)
        self.assertIn("Slack channel lists must not contain empty entries.", result.stderr)
        self.assertFalse(curl_log_path.exists())

    def test_notify_pipeline_with_no_failed_jobs_posts_only_to_always_channels(self):
        # Arrange
        environment, curl_log_path = self.__create_environment(
            always_channels="C_TOOLS,C_CI",
            failure_channels="C_RTX",
            failed_jobs_response="[]",
        )

        # Act
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("notify_remix_target_dep_bot.sh")), "pipeline"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(curl_log_path.read_text(encoding="utf-8").splitlines(), ["C_TOOLS", "C_CI"])

    def test_notify_pipeline_with_failed_job_posts_to_always_and_failure_channels(self):
        # Arrange
        environment, curl_log_path = self.__create_environment(
            always_channels="C_TOOLS",
            failure_channels="C_RTX",
            failed_jobs_response='[{"name":"unit-tests","allow_failure":false}]',
        )

        # Act
        result = subprocess.run(
            ["bash", str(Path(__file__).with_name("notify_remix_target_dep_bot.sh")), "pipeline"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(curl_log_path.read_text(encoding="utf-8").splitlines(), ["C_TOOLS", "C_RTX"])

    def __create_environment(
        self,
        always_channels: str,
        failure_channels: str,
        failed_channel: str = "",
        failed_jobs_response: str = "[]",
    ) -> tuple[dict[str, str], Path]:
        root = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        fake_curl_path = root / "curl"
        fake_curl_path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail

                channel_id=""
                for argument in "$@"; do
                    case "${argument}" in
                        */jobs)
                            printf '%s\\n' "${FAKE_GITLAB_JOBS_RESPONSE:?FAKE_GITLAB_JOBS_RESPONSE must be set}"
                            exit 0
                            ;;
                        channel=*)
                            channel_id="${argument#channel=}"
                            ;;
                    esac
                done

                printf '%s\\n' "${channel_id}" >> "${FAKE_CURL_LOG:?FAKE_CURL_LOG must be set}"
                if [ "${channel_id}" = "${FAKE_CURL_FAILURE_CHANNEL:-}" ]; then
                    printf '%s\\n' '{"ok":false,"error":"channel_not_found"}'
                else
                    printf '%s\\n' '{"ok":true}'
                fi
                """
            ),
            encoding="utf-8",
        )
        fake_curl_path.chmod(0o755)
        curl_log_path = root / "curl.log"
        environment = {
            **os.environ,
            "CI_API_V4_URL": "https://gitlab.example.com/api/v4",
            "CI_COMMIT_SHA": "0123456789abcdef0123456789abcdef01234567",
            "CI_MERGE_REQUEST_IID": "17",
            "CI_PIPELINE_ID": "42",
            "CI_PIPELINE_URL": "https://gitlab.example.com/example/project/-/pipelines/42",
            "CI_PROJECT_ID": "7",
            "CI_PROJECT_PATH": "example/project",
            "CI_PROJECT_URL": "https://gitlab.example.com/example/project",
            "FAKE_CURL_FAILURE_CHANNEL": failed_channel,
            "FAKE_CURL_LOG": str(curl_log_path),
            "FAKE_GITLAB_JOBS_RESPONSE": failed_jobs_response,
            "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
            "REMIX_TARGET_DEP_BOT_BRANCH": "dependabot/update-rtx-remix-target-deps",
            "SLACK_CHANNEL_IDS_LIGHTSPEED_CI": always_channels,
            "SLACK_FAILURE_CHANNEL_IDS_LIGHTSPEED_CI": failure_channels,
            "SLACK_TOKEN_LIGHTSPEED_CI": "test-token",
        }
        return environment, curl_log_path


if __name__ == "__main__":
    unittest.main()
