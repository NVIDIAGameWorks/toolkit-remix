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

__all__ = ("TestRenderPaneSetupUI",)

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from omni.kit.test import AsyncTestCase

from ... import setup_ui as _setup_ui
from ...setup_ui import RenderPane


class TestRenderPaneSetupUI(AsyncTestCase):
    """Verify that the render pane owns the shared DLSS panel."""

    def test_constructor_when_dlss_is_unavailable_embeds_hidden_shared_panel(self):
        """Construction should embed a hidden shared panel when DLSS NR is unavailable."""
        # Arrange
        settings = MagicMock()
        settings.get.return_value = False
        with (
            patch.object(_setup_ui.carb.settings, "get_settings", return_value=settings),
            patch.object(_setup_ui.ui, "Frame", side_effect=[MagicMock(), MagicMock()]) as frame_type,
            patch.object(_setup_ui.ui, "CollapsableFrame", return_value=MagicMock()) as collapsable_frame,
            patch.object(_setup_ui, "DlssSettingsPanel") as panel_type,
        ):
            # Act
            pane = RenderPane("")

            # Assert
            frame_type.assert_has_calls([call(), call(visible=False)])
            collapsable_frame.assert_called_once_with(
                "DLSS 3D-Guided Neural Generation [Experimental]", collapsed=False
            )
            panel_type.assert_called_once_with("render_settings_dlss_neural_rendering")
            settings.subscribe_to_node_change_events.assert_called_once_with(
                _setup_ui.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE,
                pane._RenderPane__on_dlss_neural_rendering_availability_changed,
            )
            pane.destroy()
            panel_type.return_value.destroy.assert_called_once_with()
            self.assertIsNone(pane._dlss_settings_panel)

    def test_destroy_with_existing_shared_dlss_panel_releases_panel(self):
        """Destruction should release an existing shared panel and its availability listener."""
        # Arrange
        pane = RenderPane.__new__(RenderPane)
        pane._dlss_settings_panel = MagicMock()
        pane._default_attr = {"_root_frame": None}
        pane._settings = MagicMock()
        pane._dlss_availability_subscription = MagicMock()
        pane._dlss_frame = MagicMock()
        panel = pane._dlss_settings_panel
        settings = pane._settings
        subscription = pane._dlss_availability_subscription

        with patch.object(_setup_ui, "_reset_default_attrs"):
            # Act
            pane.destroy()

            # Assert
            settings.unsubscribe_to_change_events.assert_called_once_with(subscription)
            panel.destroy.assert_called_once_with()
            self.assertIsNone(pane._dlss_settings_panel)
            self.assertIsNone(pane._settings)
            self.assertIsNone(pane._dlss_availability_subscription)
            self.assertIsNone(pane._dlss_frame)

    def test_on_dlss_availability_changed_with_setting_updates_frame_visibility(self):
        """The availability callback should mirror the shared setting onto the DLSS frame."""
        for available in (False, True):
            with self.subTest(title=f"available={available}"):
                # Arrange
                settings = MagicMock()
                settings.get.return_value = available
                frame = SimpleNamespace(visible=not available)
                pane = RenderPane.__new__(RenderPane)
                pane._settings = settings
                pane._dlss_frame = frame

                # Act
                pane._RenderPane__on_dlss_neural_rendering_availability_changed()

                # Assert
                self.assertIs(frame.visible, available)
                settings.get.assert_called_once_with(_setup_ui.SETTINGS_DLSS_NEURAL_RENDERING_AVAILABLE)
