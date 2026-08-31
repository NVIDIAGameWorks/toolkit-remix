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

import pathlib
import tempfile
import threading
from unittest.mock import MagicMock, patch

import omni.kit.test
from omni.flux.nvtt.core import library as nvtt_library


class TestNvttLibrary(omni.kit.test.AsyncTestCase):
    """Test the NVTT ctypes binding without loading the real library."""

    async def test_block_format_ordinals_match_nvtt_abi(self):
        """The ordinals are the NVTT ABI; a silent renumber would corrupt every encoded texture."""
        self.assertEqual(nvtt_library.BlockFormat.BC4, 6)
        self.assertEqual(nvtt_library.BlockFormat.BC5, 9)
        self.assertEqual(nvtt_library.BlockFormat.BC7, 15)

    async def test_mipmap_filter_ordinals_match_nvtt_abi(self):
        """The filter ordinals are the NVTT C wrapper ABI."""
        self.assertEqual(nvtt_library.MipmapFilter.BOX, 0)
        self.assertEqual(nvtt_library.MipmapFilter.TRIANGLE, 1)
        self.assertEqual(nvtt_library.MipmapFilter.KAISER, 2)
        self.assertEqual(nvtt_library.MipmapFilter.MITCHELL, 3)
        self.assertEqual(nvtt_library.MipmapFilter.MIN, 4)
        self.assertEqual(nvtt_library.MipmapFilter.MAX, 5)

    async def test_pin_device_survives_a_missing_cuda_driver(self):
        """A machine with no CUDA driver still encodes, with NVTT choosing the device."""
        # Arrange
        library = MagicMock()
        state = nvtt_library._ThreadState()

        # Act
        with (
            patch.object(nvtt_library, "_thread_state", state),
            patch("ctypes.CDLL", side_effect=OSError("nvcuda.dll is absent")),
        ):
            nvtt_library._pin_device(library)

        # Assert
        library.nvttUseCurrentDevice.assert_not_called()

    async def test_pin_device_stops_after_a_failing_driver_call(self):
        """A driver error leaves NVTT to choose the device instead of pinning a wrong one."""
        # Arrange
        library = MagicMock()
        driver = MagicMock()
        driver.cuInit.return_value = 0
        # A non-zero CUDA result means the call failed.
        driver.cuDeviceGet.return_value = 101
        state = nvtt_library._ThreadState()

        # Act
        with patch.object(nvtt_library, "_thread_state", state), patch("ctypes.CDLL", return_value=driver):
            nvtt_library._pin_device(library)

        # Assert
        driver.cuDevicePrimaryCtxRetain.assert_not_called()
        library.nvttUseCurrentDevice.assert_not_called()

    async def test_pin_device_runs_once_per_thread(self):
        """The second call on one thread does no driver work."""
        # Arrange
        library = MagicMock()
        driver = MagicMock()
        driver.cuInit.return_value = 0
        driver.cuDeviceGet.return_value = 0
        driver.cuDevicePrimaryCtxRetain.return_value = 0
        driver.cuCtxSetCurrent.return_value = 0
        state = nvtt_library._ThreadState()

        # Act
        with patch.object(nvtt_library, "_thread_state", state), patch("ctypes.CDLL", return_value=driver):
            nvtt_library._pin_device(library)
            nvtt_library._pin_device(library)

        # Assert
        self.assertEqual(driver.cuInit.call_count, 1)
        self.assertEqual(library.nvttUseCurrentDevice.call_count, 1)

    async def test_loading_the_library_does_not_probe_cuda(self):
        """The CUDA probe can call cudaSetDevice, so is_available must not move any thread's GPU."""
        # Arrange
        library = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            pathlib.Path(directory, "nvtt30000.dll").touch()

            # Act
            with (
                patch.object(nvtt_library, "_library", None),
                patch.object(nvtt_library, "_load_error", None),
                patch.object(nvtt_library, "_cuda_supported", None),
                patch.object(nvtt_library, "_nvtt_directory", return_value=pathlib.Path(directory)),
                patch("ctypes.CDLL", return_value=library),
            ):
                self.assertTrue(nvtt_library.is_available())

        # Assert
        library.nvttIsCudaSupported.assert_not_called()

    async def test_context_pins_the_device_before_probing_cuda(self):
        """Pinning must come first, because the probe itself can choose a device."""
        # Arrange
        calls = []
        library = MagicMock()
        library.nvttIsCudaSupported.side_effect = lambda: calls.append("probe") or 1
        state = nvtt_library._ThreadState()

        # Act
        with (
            patch.object(nvtt_library, "_thread_state", state),
            patch.object(nvtt_library, "_cuda_supported", None),
            patch.object(nvtt_library, "_pin_device", side_effect=lambda _: calls.append("pin")),
        ):
            nvtt_library._context(library, use_cuda=True)

        # Assert
        self.assertEqual(calls, ["pin", "probe"])

    async def test_cuda_support_is_probed_once_per_process(self):
        """Every later encode reads the cached answer instead of calling the library again."""
        # Arrange
        library = MagicMock()
        library.nvttIsCudaSupported.return_value = 1

        # Act
        with (
            patch.object(nvtt_library, "_cuda_supported", None),
            patch.object(nvtt_library, "_thread_state", nvtt_library._ThreadState()),
            patch.object(nvtt_library, "_pin_device"),
        ):
            nvtt_library._context(library, use_cuda=True)
            nvtt_library._context(library, use_cuda=True)

        # Assert
        self.assertEqual(library.nvttIsCudaSupported.call_count, 1)

    async def test_context_captures_the_destroy_function(self):
        """Every context creation records how to free it, so cleanup never guesses."""
        # Arrange
        library = MagicMock()
        state = nvtt_library._ThreadState()

        # Act
        with (
            patch.object(nvtt_library, "_thread_state", state),
            patch.object(nvtt_library, "_pin_device"),
            patch.object(nvtt_library, "_cuda_supported", True),
        ):
            nvtt_library._context(library, use_cuda=False)

        # Assert
        self.assertIs(state.holder.destroy_context, library.nvttDestroyContext)

    async def test_context_creates_and_cleans_up_both_acceleration_modes(self):
        """Cleanup must free every context a thread created, CUDA and CPU alike."""
        # Arrange
        library = MagicMock()
        library.nvttCreateContext.side_effect = [111, 222]
        state = nvtt_library._ThreadState()

        # Act
        with (
            patch.object(nvtt_library, "_thread_state", state),
            patch.object(nvtt_library, "_pin_device"),
            patch.object(nvtt_library, "_cuda_supported", True),
        ):
            nvtt_library._context(library, use_cuda=True)
            nvtt_library._context(library, use_cuda=False)
        state.holder.__del__()

        # Assert
        self.assertEqual(library.nvttDestroyContext.call_count, 2)
        library.nvttDestroyContext.assert_any_call(111)
        library.nvttDestroyContext.assert_any_call(222)
        self.assertEqual(state.holder.contexts, {})

    async def test_holder_cleanup_survives_a_failing_destroy_call(self):
        """A destroy call failing during shutdown must not raise out of __del__."""
        # Arrange
        holder = nvtt_library._ContextHolder()
        holder.destroy_context = MagicMock(side_effect=OSError("library already unloaded"))
        holder.contexts = {True: 1}

        # Act
        holder.__del__()

        # Assert
        holder.destroy_context.assert_called_once_with(1)
        self.assertEqual(holder.contexts, {})

    async def test_holder_cleanup_without_any_context_is_a_no_op(self):
        """A thread that never encoded must not call an unset destroy function."""
        # Arrange
        holder = nvtt_library._ContextHolder()

        # Act
        holder.__del__()

        # Assert
        self.assertEqual(holder.contexts, {})

    async def test_holder_cleanup_destroys_each_context_only_once(self):
        """A second cleanup pass, such as a later GC, must not free a context twice."""
        # Arrange
        holder = nvtt_library._ContextHolder()
        holder.destroy_context = MagicMock()
        holder.contexts = {True: 1}

        # Act
        holder.__del__()
        holder.__del__()

        # Assert
        holder.destroy_context.assert_called_once_with(1)

    async def test_worker_thread_exit_destroys_its_own_context(self):
        """A worker thread's context must be freed the moment that thread exits, not later.

        ``_ThreadState.__del__`` never runs for a plain ``threading.local`` subclass when a
        worker thread exits, only the ``_ContextHolder`` it stores does. This drives the real
        library entry points across a real thread, with no manual ``__del__`` call, to prove the
        holder design actually frees a background thread's context.
        """
        # Arrange
        library = MagicMock()
        library.nvttCreateContext.return_value = 999
        state = nvtt_library._ThreadState()

        def worker() -> None:
            with (
                patch.object(nvtt_library, "_pin_device"),
                patch.object(nvtt_library, "_cuda_supported", True),
            ):
                nvtt_library._context(library, use_cuda=False)

        # Act
        with patch.object(nvtt_library, "_thread_state", state):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

        # Assert
        library.nvttDestroyContext.assert_called_once_with(999)
