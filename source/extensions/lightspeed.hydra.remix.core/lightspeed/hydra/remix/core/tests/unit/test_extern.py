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

import ctypes
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.test

import lightspeed.hydra.remix.core.extern as _extern


class TestExtern(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self._original_instance = _extern._instance
        self._original_support_level = _extern._hdremix_support_level
        self._original_error_message = _extern._hdremix_error_message
        self._original_dll_path = _extern.RemixExtern._hdremix_dll_path
        self._original_dll_handle = _extern.RemixExtern._hdremix_dll_handle
        self._original_support_check_task = _extern._support_check_task
        _extern._instance = None
        _extern._hdremix_support_level = _extern.RemixSupport.NOT_SUPPORTED
        _extern._hdremix_error_message = "Driver unsupported"
        _extern.RemixExtern._hdremix_dll_path = "HdRemix.dll"
        _extern.RemixExtern._hdremix_dll_handle = None
        _extern._support_check_task = None

    async def tearDown(self):
        _extern._instance = self._original_instance
        _extern._hdremix_support_level = self._original_support_level
        _extern._hdremix_error_message = self._original_error_message
        _extern.RemixExtern._hdremix_dll_path = self._original_dll_path
        _extern.RemixExtern._hdremix_dll_handle = self._original_dll_handle
        _extern._support_check_task = self._original_support_check_task

    async def test_safe_remix_extern_raises_runtime_error_when_load_does_not_create_instance(self):
        with patch.object(_extern, "load_remix_extern", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "HdRemix extern is unavailable"):
                _extern.safe_remix_extern()

    async def test_safe_remix_extern_async_raises_runtime_error_when_load_does_not_create_instance(self):
        with patch.object(_extern, "load_remix_extern_async", new=AsyncMock(return_value=0)):
            with self.assertRaisesRegex(RuntimeError, "HdRemix extern is unavailable"):
                await _extern.safe_remix_extern_async()

    async def test_preload_hdremix_dll_uses_supplied_path_and_caches_handle(self):
        # Arrange
        dll_path = r"C:\hdremix\HdRemix.dll"
        dll_handle = MagicMock()

        # Act
        with patch.object(_extern.ctypes.cdll, "LoadLibrary", return_value=dll_handle) as load_library:
            ok, message = _extern.RemixExtern.preload_hdremix_dll(dll_path)

        # Assert
        self.assertTrue(ok)
        self.assertEqual("HdRemix.dll loaded.", message)
        load_library.assert_called_once_with(dll_path)
        self.assertIs(_extern.RemixExtern._hdremix_dll_handle, dll_handle)

    async def test_remix_extern_destroy_clears_cached_state(self):
        # Arrange
        _extern._instance = MagicMock()
        _extern._support_check_task = MagicMock()
        _extern.RemixExtern._hdremix_dll_handle = MagicMock()

        # Act
        _extern.remix_extern_destroy()

        # Assert
        self.assertIsNone(_extern._instance)
        self.assertIsNone(_extern._support_check_task)
        self.assertIsNone(_extern.RemixExtern._hdremix_dll_handle)

    async def test_check_support_returns_driver_guidance_and_logs_native_message(self):
        # Arrange
        native_message = "Native driver failure"

        def is_supported(out_error_message, out_error_code):
            out_error_message.contents.value = native_message.encode("utf-8")
            out_error_code.contents.value = 0x88960002
            return 0

        support_function = MagicMock(side_effect=is_supported)
        dll = SimpleNamespace(hdremix_issupported_ex=support_function)

        # Act
        with (
            patch.object(_extern.RemixExtern, "_RemixExtern__load_hdremix_library", return_value=dll),
            patch.object(_extern.carb, "log_error") as log_error,
        ):
            result = _extern.RemixExtern.check_support()

        # Assert
        self.assertEqual(
            (
                _extern.RemixSupport.NOT_SUPPORTED,
                "The installed graphics driver is incompatible with this version of the RTX Remix Toolkit.\n\n"
                "Please update to the latest available driver and relaunch the app.",
            ),
            result,
        )
        log_error.assert_called_once_with(native_message)
        self.assertEqual([ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_uint32)], support_function.argtypes)
        self.assertIs(support_function.restype, ctypes.c_int)
