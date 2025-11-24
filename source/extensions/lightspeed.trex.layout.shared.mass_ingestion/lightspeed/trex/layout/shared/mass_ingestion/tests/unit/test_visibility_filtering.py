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
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared.mass_ingestion.setup_ui import SetupUI
from lightspeed.trex.utils.widget.decorators import SKIPPED
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestMassIngestionVisibilityFiltering(AsyncTestCase):
    """
    Test that @skip_when_widget_is_invisible decorator works on SetupUI's decorated methods.
    """

    async def setUp(self):
        await arrange_windows()

    async def test_decorated_methods_skip_when_invisible(self):  # noqa: PLW0212
        """Test that decorated methods return SKIPPED when widget is invisible"""
        window = ui.Window("test_mass_ingestion", width=800, height=600)
        with window.frame:
            widget = SetupUI(schemas=[], context=TrexContexts.STAGE_CRAFT)
        await omni.kit.app.get_app().next_update_async()

        # When visible - should NOT skip
        widget.root_widget.visible = True
        self.assertNotEqual(widget._on_mass_queue_action_pressed(None, "show_in_viewport"), SKIPPED)  # noqa: PLW0212

        # When invisible - should skip
        widget.root_widget.visible = False
        self.assertEqual(widget._on_mass_queue_action_pressed(None, "show_in_viewport"), SKIPPED)  # noqa: PLW0212

        window.destroy()
