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

import asyncio
import ctypes
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import omni.kit.test

import lightspeed.hydra.remix.core.extern as _extern


class TestExtern(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        """Save and reset shared extern state before each test."""
        self._original_instance = _extern._instance
        self._original_support_level = _extern._hdremix_support_level
        self._original_error_message = _extern._hdremix_error_message
        self._original_last_waiting_message = _extern._last_waiting_message
        self._original_dll_path = _extern.RemixExtern._hdremix_dll_path
        self._original_dll_handle = _extern.RemixExtern._hdremix_dll_handle
        self._original_support_check_task = _extern._support_check_task
        _extern._instance = None
        _extern._hdremix_support_level = _extern.RemixSupport.NOT_SUPPORTED
        _extern._hdremix_error_message = "Driver unsupported"
        _extern._last_waiting_message = None
        _extern.RemixExtern._hdremix_dll_path = "HdRemix.dll"
        _extern.RemixExtern._hdremix_dll_handle = None
        _extern._support_check_task = None

    async def tearDown(self):
        """Restore shared extern state after each test."""
        _extern._instance = self._original_instance
        _extern._hdremix_support_level = self._original_support_level
        _extern._hdremix_error_message = self._original_error_message
        _extern._last_waiting_message = self._original_last_waiting_message
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

    async def test_remix_extern_destroy_when_support_check_is_pending_cancels_task(self):
        """Core shutdown should cancel its unfinished shared support task."""
        # Arrange
        support_check_task = MagicMock()
        support_check_task.done.return_value = False
        _extern._support_check_task = support_check_task

        # Act
        _extern.remix_extern_destroy()

        # Assert
        support_check_task.cancel.assert_called_once_with()
        self.assertIsNone(_extern._support_check_task)

    async def test_load_impl_when_timeout_expires_caches_guidance_and_logs_original_diagnostic(self):
        """A local support timeout should cache guidance without changing its logged diagnostic."""
        # Arrange
        timeout_diagnostic = "Remix initialization timeout (async)"
        app = SimpleNamespace(next_update_async=AsyncMock())
        _extern._hdremix_support_level = _extern.RemixSupport.WAITING_FOR_INIT
        _extern._hdremix_error_message = "Remix is being initialized..."

        # Act
        with (
            patch.object(
                _extern.RemixExtern,
                "check_support",
                return_value=(_extern.RemixSupport.WAITING_FOR_INIT, "Remix is being initialized..."),
            ),
            patch.object(_extern.omni.kit.app, "get_app", return_value=app),
            patch.object(_extern.carb, "log_error") as log_error,
        ):
            frames_passed = await _extern._load_remix_extern_impl(is_async=True, timeout_frames=0)

        # Assert
        self.assertEqual(1, frames_passed)
        log_error.assert_called_once_with(timeout_diagnostic)
        self.assertEqual(_extern.RemixSupport.NOT_SUPPORTED, _extern._hdremix_support_level)
        self.assertTrue(_extern._hdremix_error_message.startswith(timeout_diagnostic))
        self.assertIn(
            "connecting the monitor to a motherboard or integrated-graphics port", _extern._hdremix_error_message
        )
        self.assertIn("Connect the monitor directly to the NVIDIA GPU", _extern._hdremix_error_message)
        self.assertTrue(_extern.is_remix_timeout())

    async def test_load_impl_when_support_resolves_at_timeout_boundary_preserves_result(self):
        """A definitive support result should win when it arrives on the timeout boundary."""
        cases = (
            (_extern.RemixSupport.SUPPORTED, "Success"),
            (_extern.RemixSupport.NOT_SUPPORTED, "Native error"),
        )
        for expected_support, expected_message in cases:
            with self.subTest(title=expected_support.name):
                # Arrange
                app = SimpleNamespace(next_update_async=AsyncMock())
                _extern._hdremix_support_level = _extern.RemixSupport.WAITING_FOR_INIT
                _extern._hdremix_error_message = "Remix is being initialized..."

                # Act
                with (
                    patch.object(
                        _extern.RemixExtern,
                        "check_support",
                        return_value=(expected_support, expected_message),
                    ),
                    patch.object(_extern.omni.kit.app, "get_app", return_value=app),
                    patch.object(_extern, "remix_extern_init"),
                    patch.object(_extern.carb, "log_error") as log_error,
                ):
                    frames_passed = await _extern._load_remix_extern_impl(is_async=True, timeout_frames=0)

                # Assert
                self.assertEqual(1, frames_passed)
                self.assertEqual(expected_support, _extern._hdremix_support_level)
                self.assertEqual(expected_message, _extern._hdremix_error_message)
                log_error.assert_not_called()

    async def test_load_async_when_one_waiter_is_cancelled_keeps_shared_task_running(self):
        """Cancelling one waiter should not cancel the shared support task."""
        # Arrange
        load_started = asyncio.Event()
        allow_load_to_finish = asyncio.Event()

        async def load_impl(**load_kwargs):
            """Wait until the test permits the shared support load to finish."""
            load_started.set()
            await allow_load_to_finish.wait()
            return load_kwargs["timeout_frames"]

        async def cancel_one_waiter():
            """Cancel one waiter while allowing the shared support task to complete."""
            first_waiter = asyncio.create_task(_extern.load_remix_extern_async(timeout_frames=17))
            second_waiter = asyncio.create_task(_extern.load_remix_extern_async(timeout_frames=17))
            await load_started.wait()
            first_waiter.cancel()
            cancelled_waiter_result = await asyncio.gather(first_waiter, return_exceptions=True)
            shared_task_cancelled = _extern._support_check_task.cancelled()
            allow_load_to_finish.set()
            second_result = await second_waiter
            return cancelled_waiter_result, shared_task_cancelled, second_result

        with patch.object(_extern, "_load_remix_extern_impl", new=AsyncMock(side_effect=load_impl)) as load_mock:
            # Act
            cancelled_waiter_result, shared_task_cancelled, second_result = await cancel_one_waiter()

        # Assert
        self.assertIsInstance(cancelled_waiter_result[0], asyncio.CancelledError)
        self.assertFalse(shared_task_cancelled)
        self.assertEqual(17, second_result)
        load_mock.assert_awaited_once_with(is_async=True, timeout_frames=17)

    async def test_reset_remix_support_for_retry_updates_state_only_without_pending_task(self):
        """Reset support state only after the shared support task has completed."""
        for title, task_done, expected_task, expected_support, expected_message, expected_waiting in (
            (
                "unfinished task preserves cached support state",
                False,
                True,
                _extern.RemixSupport.NOT_SUPPORTED,
                "cached error",
                "cached waiting diagnostic",
            ),
            (
                "completed task resets cached support state",
                True,
                None,
                _extern.RemixSupport.WAITING_FOR_INIT,
                "<HdRemix support retry requested>",
                None,
            ),
        ):
            with self.subTest(title=title):
                # Arrange
                support_check_task = MagicMock()
                support_check_task.done.return_value = task_done
                _extern._support_check_task = support_check_task
                _extern._hdremix_support_level = _extern.RemixSupport.NOT_SUPPORTED
                _extern._hdremix_error_message = "cached error"
                _extern._last_waiting_message = "cached waiting diagnostic"

                # Act
                _extern.reset_remix_support_for_retry("retry")

                # Assert
                self.assertIs(_extern._support_check_task, support_check_task if expected_task else None)
                self.assertEqual(expected_support, _extern._hdremix_support_level)
                self.assertEqual(expected_message, _extern._hdremix_error_message)
                self.assertEqual(expected_waiting, _extern._last_waiting_message)

    async def test_retry_remix_support_async_when_retry_cannot_help_skips_reset_and_load(self):
        """Retry skips reset and loading when cached support cannot benefit."""
        for title, support_level, error_message in (
            ("supported result", _extern.RemixSupport.SUPPORTED, "Success"),
            ("definitive native failure", _extern.RemixSupport.NOT_SUPPORTED, "Native failure"),
        ):
            with self.subTest(title=title):
                # Arrange
                _extern._hdremix_support_level = support_level
                _extern._hdremix_error_message = error_message

                with (
                    patch.object(_extern, "reset_remix_support_for_retry") as reset_mock,
                    patch.object(_extern, "load_remix_extern_async", new=AsyncMock()) as load_mock,
                ):
                    # Act
                    result = await _extern.retry_remix_support_async()

                # Assert
                self.assertEqual(0, result)
                reset_mock.assert_not_called()
                load_mock.assert_not_awaited()

    async def test_load_remix_extern_when_called_from_running_loop_raises_async_api_guidance(self):
        """Blocking loading reports the asynchronous API when called in a running loop."""
        # Arrange
        expected_message = (
            r"^Cannot call load_remix_extern\(\) from within a running event loop\. "
            r"Use load_remix_extern_async\(\) instead\.$"
        )

        # Act / Assert
        with self.assertRaisesRegex(RuntimeError, expected_message):
            _extern.load_remix_extern()

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
