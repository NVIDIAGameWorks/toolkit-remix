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

__all__ = ["TestMCPDiscovery"]

import contextlib
import json
import tempfile
from pathlib import Path
from unittest import mock

import omni.kit.test

from lightspeed.trex.mcp.core import discovery


class TestMCPDiscovery(omni.kit.test.AsyncTestCase):
    """Test discovery publication and ownership with isolated filesystem fixtures."""

    async def setUp(self):
        """Isolate filesystem writes and mock operating system access controls."""
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        directory = stack.enter_context(tempfile.TemporaryDirectory())
        self.local_app_data = Path(directory)
        self.path = self.local_app_data / "NVIDIA" / "RTX Remix" / "mcp.json"
        self.manifest = {
            "mcp_endpoint": "http://127.0.0.1:18015/mcp",
            "rest_endpoint": "http://127.0.0.1:8011",
            "port": 18015,
            "rest_port": 8011,
            "version": "1.29.0",
            "pid": 22896,
        }
        stack.enter_context(mock.patch.object(discovery.sys, "platform", "win32"))
        stack.enter_context(mock.patch.dict(discovery.os.environ, {"LOCALAPPDATA": directory}))
        self.current_user = stack.enter_context(
            mock.patch.object(discovery, "_current_user_sid", return_value="S-1-5-21-1")
        )
        self.restrict_access = stack.enter_context(mock.patch.object(discovery, "_restrict_access"))
        self.manifest_lock = stack.enter_context(
            mock.patch.object(discovery, "_manifest_lock", side_effect=lambda *_: contextlib.nullcontext())
        )

    def __write_manifest(self, manifest):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(manifest), encoding="utf-8")

    async def test_publish_manifest_on_windows_writes_complete_discovery_payload(self):
        """Publish the supplied live endpoints at the documented user location."""
        # Arrange
        manifest = self.manifest.copy()

        # Act
        path = discovery.publish_manifest(manifest)

        # Assert
        self.assertEqual(path, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), manifest)
        self.manifest_lock.assert_called_once_with(self.path, "S-1-5-21-1")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    async def test_publish_manifest_with_existing_file_replaces_only_after_private_payload_is_ready(self):
        """Keep the previous endpoint readable until the secured replacement is complete."""
        # Arrange
        previous = {**self.manifest, "port": 18014, "mcp_endpoint": "http://127.0.0.1:18014/mcp"}
        self.__write_manifest(previous)
        replace = discovery.os.replace
        events = []

        def restrict_access(path, _sid):
            events.append(("restricted", Path(path).read_bytes()))

        def replace_manifest(source, destination):
            events.append(("replaced", json.loads(Path(source).read_text(encoding="utf-8"))))
            events.append(("previous", json.loads(Path(destination).read_text(encoding="utf-8"))))
            replace(source, destination)

        self.restrict_access.side_effect = restrict_access
        with mock.patch.object(discovery.os, "replace", side_effect=replace_manifest):
            # Act
            discovery.publish_manifest(self.manifest)

        # Assert
        self.assertEqual(events, [("restricted", b""), ("replaced", self.manifest), ("previous", previous)])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.manifest)

    async def test_publish_manifest_when_acl_fails_preserves_previous_file_and_removes_temporary_file(self):
        """Never publish an endpoint without its requested access control."""
        # Arrange
        previous = {**self.manifest, "pid": 1}
        self.__write_manifest(previous)
        self.restrict_access.side_effect = PermissionError("ACL denied")

        # Act
        with self.assertRaisesRegex(PermissionError, "ACL denied"):
            discovery.publish_manifest(self.manifest)

        # Assert
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), previous)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    async def test_publish_manifest_when_replace_fails_preserves_previous_file_and_removes_temporary_file(self):
        """Leave the prior discovery record intact if atomic replacement fails."""
        # Arrange
        previous = {**self.manifest, "pid": 1}
        self.__write_manifest(previous)
        with mock.patch.object(discovery.os, "replace", side_effect=PermissionError("replace denied")):
            # Act
            with self.assertRaisesRegex(PermissionError, "replace denied"):
                discovery.publish_manifest(self.manifest)

        # Assert
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), previous)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    async def test_publish_manifest_when_serialization_fails_preserves_previous_file_and_removes_temporary_file(self):
        """Prevent partial JSON from replacing a usable discovery record."""
        # Arrange
        self.__write_manifest(self.manifest)
        invalid = {**self.manifest, "version": object()}

        # Act
        with self.assertRaises(TypeError):
            discovery.publish_manifest(invalid)

        # Assert
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.manifest)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    async def test_publish_manifest_on_other_platforms_does_not_create_windows_discovery_file(self):
        """Keep the Windows discovery location platform specific."""
        for platform in ("linux", "darwin"):
            with self.subTest(title=platform):
                # Arrange
                with mock.patch.object(discovery.sys, "platform", platform):
                    # Act
                    path = discovery.publish_manifest(self.manifest)

                # Assert
                self.assertIsNone(path)
                self.assertFalse(self.path.exists())
                self.current_user.assert_not_called()

    async def test_publish_manifest_without_local_app_data_reports_error_before_writing(self):
        """Do not publish into an unintended directory when user profile lookup fails."""
        for environment in ({}, {"LOCALAPPDATA": ""}):
            with self.subTest(title=str(environment)):
                # Arrange
                with mock.patch.dict(discovery.os.environ, environment, clear=True):
                    # Act
                    with self.assertRaises(OSError):
                        discovery.publish_manifest(self.manifest)

                # Assert
                self.assertFalse(self.path.exists())
                self.current_user.assert_not_called()

    async def test_publish_manifest_when_user_identity_fails_preserves_previous_file(self):
        """Require a known user identity before preparing replacement discovery data."""
        # Arrange
        self.__write_manifest(self.manifest)
        self.current_user.side_effect = ValueError("Missing current user SID")

        # Act
        with self.assertRaisesRegex(ValueError, "Missing current user SID"):
            discovery.publish_manifest(self.manifest)

        # Assert
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.manifest)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        self.restrict_access.assert_not_called()

    async def test_remove_manifest_when_contents_match_removes_owned_record_under_lock(self):
        """Remove the running server's own record during shutdown."""
        # Arrange
        self.__write_manifest(self.manifest)

        # Act
        discovery.remove_manifest(self.path, self.manifest)

        # Assert
        self.assertFalse(self.path.exists())
        self.manifest_lock.assert_called_once_with(self.path, "S-1-5-21-1")

    async def test_remove_manifest_when_contents_changed_preserves_newer_record(self):
        """Do not remove another instance or a newer bind from the same process."""
        for changed_field in ({"pid": 22900}, {"port": 18016, "mcp_endpoint": "http://127.0.0.1:18016/mcp"}):
            with self.subTest(title=str(changed_field)):
                # Arrange
                newer = {**self.manifest, **changed_field}
                self.__write_manifest(newer)

                # Act
                discovery.remove_manifest(self.path, self.manifest)

                # Assert
                self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), newer)

    async def test_remove_manifest_when_file_is_missing_does_not_raise(self):
        """Allow shutdown after another process or the user removes discovery data."""
        # Arrange
        self.path.parent.mkdir(parents=True)

        # Act
        discovery.remove_manifest(self.path, self.manifest)

        # Assert
        self.assertFalse(self.path.exists())

    async def test_remove_manifest_when_json_is_invalid_preserves_file_and_reports_error(self):
        """Retain records whose ownership cannot be established."""
        # Arrange
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{invalid", encoding="utf-8")

        # Act
        with self.assertRaises(json.JSONDecodeError):
            discovery.remove_manifest(self.path, self.manifest)

        # Assert
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{invalid")

    async def test_remove_manifest_when_unlink_fails_reports_error(self):
        """Expose cleanup failures for the server's shutdown logging."""
        # Arrange
        self.__write_manifest(self.manifest)
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("remove denied")):
            # Act
            with self.assertRaisesRegex(PermissionError, "remove denied"):
                discovery.remove_manifest(self.path, self.manifest)

        # Assert
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), self.manifest)
