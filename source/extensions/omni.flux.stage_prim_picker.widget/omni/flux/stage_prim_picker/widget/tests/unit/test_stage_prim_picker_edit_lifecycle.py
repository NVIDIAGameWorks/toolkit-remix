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
from unittest.mock import Mock, patch

import omni.kit.app
import omni.kit.test
import omni.ui as ui
from omni.flux.stage_prim_picker.widget import stage_prim_picker as _stage_prim_picker


class _ValueModel(ui.AbstractValueModel):
    def get_value_as_string(self) -> str:
        return ""


class TestStagePrimPickerEditLifecycle(omni.kit.test.AsyncTestCase):
    def _make_picker(self, end_edit_fn=None) -> _stage_prim_picker._SinglePrimPicker:
        return _stage_prim_picker._SinglePrimPicker(
            _ValueModel(),
            "",
            None,
            None,
            None,
            100,
            100,
            1000,
            "",
            "test",
            0,
            end_edit_fn=end_edit_fn,
        )

    async def test_hide_dropdown_when_teardown_fails_ends_edit(self):
        # Arrange
        end_edit_fn = Mock()
        picker = self._make_picker(end_edit_fn=end_edit_fn)
        picker._begin_edit()

        # Act
        with (
            patch.object(picker, "_close_dropdown_window", side_effect=RuntimeError("close failed")),
            self.assertRaisesRegex(RuntimeError, "close failed"),
        ):
            picker._hide_dropdown()

        # Assert
        self.assertFalse(picker._is_editing)
        end_edit_fn.assert_called_once_with()

    async def test_destroy_cancels_pending_load_more_task(self):
        # Arrange
        picker = self._make_picker()
        task = asyncio.ensure_future(asyncio.sleep(60))
        picker._load_more_task = task

        # Act
        picker.destroy()
        await omni.kit.app.get_app().next_update_async()

        # Assert
        self.assertTrue(task.cancelled())
        self.assertIsNone(picker._load_more_task)
