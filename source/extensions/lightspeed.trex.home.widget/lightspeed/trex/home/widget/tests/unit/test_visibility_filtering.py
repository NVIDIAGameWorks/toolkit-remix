"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import omni.kit.app
import omni.ui as ui
from lightspeed.trex.home.widget.home_widget import HomePageWidget
from lightspeed.trex.utils.widget.decorators import SKIPPED
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestHomePageWidgetVisibilityFiltering(AsyncTestCase):
    """
    Test that @skip_when_widget_is_invisible decorator works on HomePageWidget's decorated methods.
    """

    async def setUp(self):
        await arrange_windows()

    async def test_decorated_methods_skip_when_invisible(self):  # noqa: PLW0212
        """Test that all decorated methods return _SKIPPED_ when widget is invisible"""
        # Arrange
        window = ui.Window("test_decorated_methods", width=600, height=800)
        with window.frame:
            widget = HomePageWidget("")
        await omni.kit.app.get_app().next_update_async()

        # Act & Assert: When visible
        widget.root_widget.visible = True
        await omni.kit.app.get_app().next_update_async()

        self.assertNotEqual(widget._show_in_explorer(), SKIPPED)  # noqa: PLW0212
        self.assertNotEqual(widget._remove_project_from_recent(["/test/path"]), SKIPPED)  # noqa: PLW0212
        self.assertNotEqual(widget._load_work_file("/test/path"), SKIPPED)  # noqa: PLW0212

        # Act & Assert: When invisible
        widget.root_widget.visible = False
        await omni.kit.app.get_app().next_update_async()

        self.assertEqual(widget._show_in_explorer(), SKIPPED)  # noqa: PLW0212
        self.assertEqual(widget._remove_project_from_recent(["/test/path"]), SKIPPED)  # noqa: PLW0212
        self.assertEqual(widget._load_work_file("/test/path"), SKIPPED)  # noqa: PLW0212

        window.destroy()
