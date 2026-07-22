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
import shutil
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from remix_target_dep_bot import (
    REMIX_RUNTIME_PACKAGE,
    TARGET_PACKAGES,
    HttpPackageProbe,
    PinUpdate,
    collect_dxvk_commits,
    format_changelog_entry,
    list_package_versions,
    read_packman_versions,
    select_latest_runtime_release,
    select_target_update,
    update_changelog,
    update_packman_versions,
)


class PackageProbe:
    def __init__(self, available, runtime_versions):
        self.available = available
        self.runtime_versions = runtime_versions

    def artifact_exists(self, package: str, version: str) -> bool:
        return (package, version) in self.available

    def list_runtime_versions(self) -> list[str]:
        return self.runtime_versions


class UrlopenResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self._body


class TestRemixTargetDepBot(unittest.TestCase):
    def test_collect_dxvk_commits_reads_commit_ids_from_gitlab_api(self):
        # Arrange
        sha = "cccccccccccccccccccccccccccccccccccccccc"
        with patch("remix_target_dep_bot.subprocess.run") as run:
            run.return_value.stdout = f'[{{"id": "{sha}"}}]'

            # Act
            commits = list(collect_dxvk_commits("https://gitlab.example.com/example/dxvk-remix.git", "main", 1))

            # Assert
            self.assertEqual(commits, [sha])
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0:3], ["glab", "api", "--hostname"])
            self.assertIn("projects/example%2Fdxvk-remix/repository/commits", run.call_args.args[0][-1])

    def test_collect_dxvk_commits_stops_after_requested_commit_count(self):
        # Arrange
        first_page = "[" + ",".join(f'{{"id": "{index:040x}"}}' for index in range(100)) + "]"
        second_page = '[{"id": "ffffffffffffffffffffffffffffffffffffffff"}]'
        with patch(
            "remix_target_dep_bot.subprocess.run",
            side_effect=[unittest.mock.Mock(stdout=first_page), unittest.mock.Mock(stdout=second_page)],
        ) as run:
            # Act
            commits = list(collect_dxvk_commits("https://gitlab.example.com/example/dxvk-remix.git", "main", 101))

            # Assert
            self.assertEqual(len(commits), 101)
            self.assertEqual(run.call_count, 2)
            self.assertIn("page=2&per_page=1", run.call_args_list[1].args[0][-1])

    def test_select_target_update_walks_history_until_both_paired_artifacts_exist(self):
        # Arrange
        probe = PackageProbe(
            available={
                ("rtx-remix-hdremix", "ext-ccccccc-main"),
                ("rtx-remix-hdremix", "ext-bbbbbbb-main"),
                ("rtx-remix-omni_core_materials", "ext-bbbbbbb-main"),
                ("rtx-remix-remix_runtime", "remix-1.5.3"),
            },
            runtime_versions=["remix-1.5.0", "remix-1.5.3"],
        )

        # Act
        update = select_target_update(
            current_versions={
                "rtx-remix-hdremix": "ext-aaaaaaa-main",
                "rtx-remix-omni_core_materials": "ext-aaaaaaa-main",
                "rtx-remix-remix_runtime": "remix-1.5.2",
            },
            dxvk_commits=["cccccccccccccccccccccccccccccccccccccccc", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
            package_probe=probe,
        )

        # Assert
        self.assertEqual(
            update.pins,
            {
                "rtx-remix-hdremix": PinUpdate("ext-aaaaaaa-main", "ext-bbbbbbb-main"),
                "rtx-remix-omni_core_materials": PinUpdate("ext-aaaaaaa-main", "ext-bbbbbbb-main"),
                "rtx-remix-remix_runtime": PinUpdate("remix-1.5.2", "remix-1.5.3"),
            },
        )
        self.assertEqual(update.dxvk_source_sha, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    def test_select_target_update_noops_when_all_versions_are_current(self):
        # Arrange
        probe = PackageProbe(
            available={
                ("rtx-remix-hdremix", "ext-bbbbbbb-main"),
                ("rtx-remix-omni_core_materials", "ext-bbbbbbb-main"),
                ("rtx-remix-remix_runtime", "remix-1.5.3"),
            },
            runtime_versions=["remix-1.5.3"],
        )

        # Act
        update = select_target_update(
            current_versions={
                "rtx-remix-hdremix": "ext-bbbbbbb-main",
                "rtx-remix-omni_core_materials": "ext-bbbbbbb-main",
                "rtx-remix-remix_runtime": "remix-1.5.3",
            },
            dxvk_commits=["bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
            package_probe=probe,
        )

        # Assert
        self.assertFalse(update.pins)
        self.assertTrue(update.is_noop)

    def test_select_latest_runtime_release_ignores_prerelease_versions(self):
        # Act
        version = select_latest_runtime_release(
            [
                "remix-1.5.2",
                "remix-1.6.0-alpha.1",
                "remix-1.5.10",
                "remix-2.0.0-rc.1",
            ]
        )

        # Assert
        self.assertEqual(version, "remix-1.5.10")

    def test_artifact_exists_rejects_empty_omnipackages_metadata(self):
        # Arrange
        probe = HttpPackageProbe("https://omnipackages.nvidia.com/packages/cloudfront")
        body = '{"name":"","extension":"","url":"","modificationTime":"","size":0}'
        with patch("remix_target_dep_bot.urllib.request.urlopen", return_value=UrlopenResponse(body)):
            # Act
            exists = probe.artifact_exists("rtx-remix-hdremix", "ext-acfce16-main")

        # Assert
        self.assertFalse(exists)

    def test_list_package_versions_reads_omnipackages_api_pages(self):
        # Arrange
        responses = [
            UrlopenResponse('{"items":[{"name":"remix-1.5.2","extension":".7z"}],"pageNum":1,"pageCount":2}'),
            UrlopenResponse(
                '{"items":[{"name":"remix-1.5.10","extension":".7z"},'
                '{"name":"readme","extension":".txt"}],"pageNum":2,"pageCount":2}'
            ),
        ]
        with patch("remix_target_dep_bot.urllib.request.urlopen", side_effect=responses) as urlopen:
            # Act
            versions = list_package_versions(
                "https://omnipackages.nvidia.com/packages/cloudfront", REMIX_RUNTIME_PACKAGE
            )

        # Assert
        self.assertCountEqual(versions, ["remix-1.5.2", "remix-1.5.10"])
        self.assertIn(
            "/api/v3/packages/rtx-remix-remix_runtime/?version=&remote=cloudfront&page=1&pageSize=100",
            urlopen.call_args_list[0].args[0],
        )

    def test_update_packman_versions_changes_only_remix_target_pins(self):
        # Arrange
        xml_path = self._write_temp_file(
            "target-deps.packman.xml",
            """
            <project toolsVersion="5.6">
              <dependency name="python" linkPath="../_build/target-deps/python">
                <package name="python" version="3.10.10+nv1-${platform}" />
              </dependency>
              <dependency name="rtx-remix-hdremix" linkPath="../_build/target-deps/hdremix">
                <package name="rtx-remix-hdremix" version="ext-aaaaaaa-main" />
              </dependency>
              <dependency name="rtx-remix-omni_core_materials" linkPath="../_build/target-deps/omni_core_materials">
                <package name="rtx-remix-omni_core_materials" version="ext-aaaaaaa-main" />
              </dependency>
              <dependency name="rtx-remix-remix_runtime" linkPath="../_build/${platform}/${config}/deps/remix_runtime">
                <package name="rtx-remix-remix_runtime" version="remix-1.5.2" />
              </dependency>
            </project>
            """,
        )

        # Act
        update_packman_versions(
            xml_path,
            {
                "rtx-remix-hdremix": "ext-bbbbbbb-main",
                "rtx-remix-omni_core_materials": "ext-bbbbbbb-main",
                "rtx-remix-remix_runtime": "remix-1.5.3",
            },
        )

        # Assert
        versions = read_packman_versions(xml_path, TARGET_PACKAGES | {REMIX_RUNTIME_PACKAGE})
        self.assertEqual(
            versions,
            {
                "rtx-remix-hdremix": "ext-bbbbbbb-main",
                "rtx-remix-omni_core_materials": "ext-bbbbbbb-main",
                "rtx-remix-remix_runtime": "remix-1.5.3",
            },
        )
        self.assertIn('version="3.10.10+nv1-${platform}"', xml_path.read_text(encoding="utf-8"))

    def test_update_changelog_appends_entry_to_unreleased_changed_section(self):
        # Arrange
        changelog_path = self._write_temp_file(
            "CHANGELOG.md",
            """
            # Changelog

            ## [Unreleased]

            ### Added
            - Existing added entry

            ### Changed
            - Existing changed entry

            ### Fixed
            - Existing fixed entry
            """,
        )

        # Act
        update_changelog(
            changelog_path,
            "- Update Remix target dependencies: hdremix `ext-bbbbbbb-main`, runtime `remix-1.5.3`",
        )

        # Assert
        text = changelog_path.read_text(encoding="utf-8")
        self.assertIn(
            "### Changed\n"
            "- Existing changed entry\n"
            "- Update Remix target dependencies: hdremix `ext-bbbbbbb-main`, runtime `remix-1.5.3`\n\n"
            "### Fixed",
            text,
        )

    def test_update_changelog_replaces_existing_remix_dependency_entry(self):
        # Arrange
        changelog_path = self._write_temp_file(
            "CHANGELOG.md",
            """
            # Changelog

            ## [Unreleased]

            ### Changed
            - Existing changed entry
            - Update Remix target dependencies: hdremix and omni_core_materials to `ext-bbbbbbb-main`

            ### Fixed
            - Existing fixed entry
            """,
        )
        entry = (
            "- Update Remix target dependencies: hdremix and omni_core_materials to `ext-ccccccc-main`, "
            "remix_runtime to `remix-1.5.4`"
        )

        # Act
        update_changelog(changelog_path, entry)

        # Assert
        text = changelog_path.read_text(encoding="utf-8")
        self.assertNotIn("ext-bbbbbbb-main", text)
        self.assertEqual(text.count("- Update Remix target dependencies:"), 1)
        self.assertIn("- Existing changed entry\n" + entry + "\n\n### Fixed", text)

    def test_format_changelog_entry_includes_changed_targets(self):
        # Arrange
        update = select_target_update(
            current_versions={
                "rtx-remix-hdremix": "ext-aaaaaaa-main",
                "rtx-remix-omni_core_materials": "ext-aaaaaaa-main",
                "rtx-remix-remix_runtime": "remix-1.5.2",
            },
            dxvk_commits=["bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
            package_probe=PackageProbe(
                available={
                    ("rtx-remix-hdremix", "ext-bbbbbbb-main"),
                    ("rtx-remix-omni_core_materials", "ext-bbbbbbb-main"),
                    ("rtx-remix-remix_runtime", "remix-1.5.3"),
                },
                runtime_versions=["remix-1.5.3"],
            ),
        )

        # Act
        entry = format_changelog_entry(update)

        # Assert
        self.assertEqual(
            entry,
            "- Update Remix target dependencies: hdremix and omni_core_materials to `ext-bbbbbbb-main`, "
            "remix_runtime to `remix-1.5.3`",
        )

    def _write_temp_file(self, name: str, content: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        file_path = root / name
        file_path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
        return file_path


if __name__ == "__main__":
    unittest.main()
