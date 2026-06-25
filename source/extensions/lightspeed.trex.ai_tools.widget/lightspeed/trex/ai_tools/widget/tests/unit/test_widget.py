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

import omni.kit.test
from lightspeed.trex.ai_tools.widget.widget import AIToolsWidget
from lightspeed.trex.utils.widget import WorkspaceWidget


class TestAIToolsWidget(omni.kit.test.AsyncTestCase):
    """Unit coverage for the workspace lifecycle contract."""

    async def test_ai_tools_widget_initializes_workspace_widget_state(self):
        """Ensure AI Tools content exposes WorkspaceWindowBase lifecycle state."""
        with patch.object(AIToolsWidget, "build"):
            widget = AIToolsWidget()

        self.assertIsInstance(widget, WorkspaceWidget)
        self.assertFalse(widget.destroyed)
        self.assertFalse(widget.window_visible)

        widget.show(True)

        self.assertTrue(widget.window_visible)

        widget.destroy()

        self.assertTrue(widget.destroyed)
