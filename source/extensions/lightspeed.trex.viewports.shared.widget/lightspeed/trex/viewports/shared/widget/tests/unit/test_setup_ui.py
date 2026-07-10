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

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import omni.kit.test
from lightspeed.trex.viewports.shared.widget.setup_ui import SetupUI

_ENSURE_EDITABLE = "lightspeed.trex.viewports.shared.widget.setup_ui._ensure_editable_camera"
_FRAME_SELECTION = "lightspeed.trex.viewports.shared.widget.setup_ui._frame_viewport_selection"


class TestSetupUIGameCameraBoundary(omni.kit.test.AsyncTestCase):
    async def test_mouse_press_focuses_viewport_without_redirecting_game_camera(self):
        """Clicking into a viewport should not leave the game camera unless the camera is being moved."""
        setup_ui = SetupUI.__new__(SetupUI)
        setup_ui._viewport_layers = SimpleNamespace(viewport_api=MagicMock())
        setup_ui.set_active = MagicMock()

        with patch(_ENSURE_EDITABLE) as mock_ensure_editable:
            setup_ui._on_viewport_frame_mouse_pressed(0.0, 0.0, 0, 0)

        mock_ensure_editable.assert_not_called()
        setup_ui.set_active.assert_called_once_with(True)

    async def test_frame_selection_redirects_game_camera_before_framing(self):
        """Frame/focus commands still switch away from the game camera before mutating the view."""
        viewport_api = MagicMock()
        setup_ui = SetupUI.__new__(SetupUI)
        setup_ui._viewport_layers = SimpleNamespace(viewport_api=viewport_api)

        with (
            patch(_ENSURE_EDITABLE, return_value=True) as mock_ensure_editable,
            patch(_FRAME_SELECTION) as mock_frame_selection,
        ):
            setup_ui.frame_viewport_selection()

        mock_ensure_editable.assert_called_once_with(viewport_api, "Frame/focus")
        mock_frame_selection.assert_called_once_with(viewport_api=viewport_api)

    async def test_frame_selection_cancels_when_game_camera_redirect_fails(self):
        """Frame/focus commands should not mutate the read-only game camera if redirect fails."""
        viewport_api = MagicMock()
        setup_ui = SetupUI.__new__(SetupUI)
        setup_ui._viewport_layers = SimpleNamespace(viewport_api=viewport_api)

        with (
            patch(_ENSURE_EDITABLE, return_value=False) as mock_ensure_editable,
            patch(_FRAME_SELECTION) as mock_frame_selection,
        ):
            setup_ui.frame_viewport_selection()

        mock_ensure_editable.assert_called_once_with(viewport_api, "Frame/focus")
        mock_frame_selection.assert_not_called()
