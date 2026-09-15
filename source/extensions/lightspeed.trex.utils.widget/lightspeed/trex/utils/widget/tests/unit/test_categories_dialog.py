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

from unittest.mock import patch

import omni.usd
from lightspeed.trex.utils.widget.categories_dialog import categories_dialog as _categories_dialog_module
from omni.kit.test import AsyncTestCase


class TestRemixCategoriesDialog(AsyncTestCase):
    """Tests the Remix render categories dialog."""

    async def setUp(self):
        """Create a clean default USD stage for the dialog."""
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._dialog = None

    async def tearDown(self):
        """Close the dialog, release its core, and close the test stage."""
        if self._dialog is not None:
            self._dialog.close()
            self._dialog._window.destroy()
            self._dialog._core.destroy()
            self._dialog = None
        if self._context.can_close_stage():
            await self._context.close_stage_async()
        self._context = None

    async def test_build_ui_without_schema_data_disables_assign_button(self):
        """Keep the empty-schema dialog open while disabling category assignment."""
        # Arrange
        categories = {}

        # Act
        with patch.object(_categories_dialog_module, "_ASSIGNABLE_REMIX_CATEGORIES", categories):
            self._dialog = _categories_dialog_module.RemixCategoriesDialog(context_name="")

        # Assert
        self.assertFalse(self._dialog._assign_button.enabled)
        self.assertTrue(self._dialog._window.visible)
