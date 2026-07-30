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

from unittest.mock import MagicMock, patch

import omni.kit.test

import lightspeed.hydra.remix.core.extension as _extension


class TestHdRemixFinalizer(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._original_support_level = _extension.extern._hdremix_support_level
        self._original_error_message = _extension.extern._hdremix_error_message
        _extension.extern._hdremix_support_level = _extension.extern.RemixSupport.WAITING_FOR_INIT
        _extension.extern._hdremix_error_message = "<test waiting for init>"

    async def tearDown(self):
        _extension.extern._hdremix_support_level = self._original_support_level
        _extension.extern._hdremix_error_message = self._original_error_message

    async def test_on_startup_initializes_dll_directory_tokens(self):
        # Arrange
        finalizer = _extension.HdRemixFinalizer()

        # Act
        with patch.object(finalizer, "_preload_hdremix_dll") as preload_mock:
            finalizer.on_startup("lightspeed.hydra.remix.core")

        # Assert
        self.assertIsNone(finalizer._hdremix_dll_dir_tokens)
        preload_mock.assert_called_once_with("lightspeed.hydra.remix.core")

    async def test_on_shutdown_without_startup_is_noop(self):
        finalizer = _extension.HdRemixFinalizer()

        with patch.object(_extension.extern, "remix_extern_destroy") as destroy_mock:
            finalizer.on_shutdown()

        destroy_mock.assert_called_once_with()

    async def test_preload_hdremix_dll_logs_non_windows_noop(self):
        finalizer = _extension.HdRemixFinalizer()

        with (
            patch.object(_extension.sys, "platform", "linux"),
            patch.object(_extension.carb, "log_info") as log_info_mock,
            patch.object(_extension.os, "add_dll_directory") as add_dll_directory_mock,
        ):
            finalizer._preload_hdremix_dll("lightspeed.hydra.remix.core")

        add_dll_directory_mock.assert_not_called()
        log_info_mock.assert_any_call(
            "[lightspeed.hydra.remix.core] Skipping Windows HdRemix DLL registration on linux."
        )

    async def test_preload_hdremix_dll_logs_windows_load_failure(self):
        # Arrange
        finalizer = _extension.HdRemixFinalizer()
        finalizer._hdremix_dll_dir_tokens = None
        app = MagicMock()
        app.get_extension_manager.return_value.get_extension_path.return_value = r"C:\extensions\hdremix"
        dll_token = MagicMock()
        plugin = MagicMock()
        plugin.name = "HdRemixRendererPlugin"

        def isdir(path):
            return path.endswith("deps\\hdremix")

        # Act
        with (
            patch.object(_extension.sys, "platform", "win32"),
            patch.object(_extension.omni.kit.app, "get_app", return_value=app),
            patch.object(_extension.os.path, "isdir", side_effect=isdir),
            patch.object(_extension.os, "add_dll_directory", return_value=dll_token),
            patch.object(
                _extension.extern.RemixExtern, "preload_hdremix_dll", return_value=(False, "load failed")
            ) as preload_mock,
            patch.object(_extension.Plug, "Registry") as registry_mock,
            patch.object(_extension.carb, "log_error") as log_error_mock,
        ):
            registry_mock.return_value.RegisterPlugins.return_value = [plugin]

            finalizer._preload_hdremix_dll("lightspeed.hydra.remix.core")

        # Assert
        log_error_mock.assert_called_with("[lightspeed.hydra.remix.core] load failed")
        preload_mock.assert_called_once_with(r"C:\extensions\hdremix\deps\hdremix\HdRemix.dll")
        support_level, error_message = _extension.extern.is_remix_supported()
        self.assertEqual(_extension.extern.RemixSupport.NOT_SUPPORTED, support_level)
        self.assertEqual("load failed", error_message)

    async def test_preload_hdremix_dll_marks_missing_directory_not_supported(self):
        finalizer = _extension.HdRemixFinalizer()
        app = MagicMock()
        app.get_extension_manager.return_value.get_extension_path.return_value = r"C:\extensions\hdremix"

        with (
            patch.object(_extension.sys, "platform", "win32"),
            patch.object(_extension.omni.kit.app, "get_app", return_value=app),
            patch.object(_extension.os.path, "isdir", return_value=False),
            patch.object(_extension.carb, "log_error") as log_error_mock,
        ):
            finalizer._preload_hdremix_dll("lightspeed.hydra.remix.core")

        support_level, error_message = _extension.extern.is_remix_supported()
        self.assertEqual(_extension.extern.RemixSupport.NOT_SUPPORTED, support_level)
        self.assertIn("HdRemix DLL directory not found", error_message)
        log_error_mock.assert_called_once()

    async def test_preload_hdremix_dll_marks_missing_usd_plugins_not_supported(self):
        # Arrange
        finalizer = _extension.HdRemixFinalizer()
        finalizer._hdremix_dll_dir_tokens = None
        app = MagicMock()
        app.get_extension_manager.return_value.get_extension_path.return_value = r"C:\extensions\hdremix"
        dll_token = MagicMock()

        def isdir(path):
            return path.endswith("deps\\hdremix")

        # Act
        with (
            patch.object(_extension.sys, "platform", "win32"),
            patch.object(_extension.omni.kit.app, "get_app", return_value=app),
            patch.object(_extension.os.path, "isdir", side_effect=isdir),
            patch.object(_extension.os, "add_dll_directory", return_value=dll_token),
            patch.object(
                _extension.extern.RemixExtern, "preload_hdremix_dll", return_value=(True, "loaded")
            ) as preload_mock,
            patch.object(_extension.Plug, "Registry") as registry_mock,
            patch.object(_extension.carb, "log_error") as log_error_mock,
        ):
            registry_mock.return_value.RegisterPlugins.return_value = []

            finalizer._preload_hdremix_dll("lightspeed.hydra.remix.core")

        # Assert
        support_level, error_message = _extension.extern.is_remix_supported()
        self.assertEqual(_extension.extern.RemixSupport.NOT_SUPPORTED, support_level)
        self.assertIn("No USD plugins were registered", error_message)
        preload_mock.assert_called_once_with(r"C:\extensions\hdremix\deps\hdremix\HdRemix.dll")
        log_error_mock.assert_called_once()
