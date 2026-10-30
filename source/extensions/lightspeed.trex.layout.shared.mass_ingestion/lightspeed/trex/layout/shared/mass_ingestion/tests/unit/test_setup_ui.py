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
from unittest.mock import MagicMock

from lightspeed.trex.layout.shared.mass_ingestion import SetupUI
from omni.kit.test import AsyncTestCase


class TestSetupUIDestroy(AsyncTestCase):
    async def test_destroy_with_mass_ingest_widget_destroys_and_clears_child(self):
        # Arrange
        setup_ui = SetupUI.__new__(SetupUI)
        setup_ui._sub_mass_cores_started = []
        setup_ui._sub_mass_cores_finished = []
        setup_ui._mass_cores_are_running = {}
        setup_ui._mass_ingest_widget = MagicMock()
        setup_ui.root_widget = MagicMock()
        mass_ingest_widget = setup_ui._mass_ingest_widget

        # Act
        setup_ui.destroy()

        # Assert
        mass_ingest_widget.destroy.assert_called_once()
        self.assertIsNone(setup_ui._mass_ingest_widget)

    async def test_destroy_after_destroy_does_not_destroy_mass_ingest_widget_again(self):
        # Arrange
        setup_ui = SetupUI.__new__(SetupUI)
        setup_ui._sub_mass_cores_started = []
        setup_ui._sub_mass_cores_finished = []
        setup_ui._mass_cores_are_running = {}
        setup_ui._mass_ingest_widget = MagicMock()
        setup_ui.root_widget = MagicMock()
        mass_ingest_widget = setup_ui._mass_ingest_widget
        setup_ui.destroy()
        mass_ingest_widget.destroy.reset_mock()

        # Act
        setup_ui.destroy()

        # Assert
        mass_ingest_widget.destroy.assert_not_called()
        self.assertIsNone(setup_ui._mass_ingest_widget)


class TestSetupUIVisibility(AsyncTestCase):
    """Verify ingestion suspension at the viewport boundary without constructing live UI."""

    async def test_show_window_with_running_core_keeps_preview_suspended(self):
        """Showing or re-showing the window must preserve an ingestion-owned pause."""
        for was_visible in (False, True):
            with self.subTest(was_visible=was_visible):
                # Arrange
                setup_ui = self.__create_setup(was_visible)
                setup_ui._mass_cores_are_running = {1: True}

                # Act
                setup_ui.show(True)

                # Assert
                setup_ui._viewport.show.assert_called_once_with(False)

    async def test_core_started_with_hidden_window_records_running_core(self):
        """Ingestion started while hidden must still suspend a later preview."""
        # Arrange
        setup_ui = self.__create_setup(False)
        core = MagicMock()

        # Act
        setup_ui._on_mass_cores_started(core)

        # Assert
        self.assertTrue(setup_ui._mass_cores_are_running[id(core)])
        setup_ui._viewport.show.assert_called_once_with(False)

    async def test_core_finished_with_another_running_core_keeps_preview_suspended(self):
        """The first completed core must not resume the preview."""
        # Arrange
        setup_ui = self.__create_setup(True)
        core = MagicMock()
        setup_ui._mass_cores_are_running = {id(core): True, 1: True}

        # Act
        setup_ui._on_mass_cores_finished(core, True)

        # Assert
        self.assertFalse(setup_ui._mass_cores_are_running[id(core)])
        setup_ui._viewport.show.assert_not_called()
        setup_ui._stage_view_widget.enable_context_event.assert_not_called()

    async def test_last_core_finished_resumes_only_visible_expanded_preview(self):
        """Finishing ingestion must respect both window and preview visibility."""
        for window_visible, preview_visible, expected in (
            (True, True, True),
            (False, True, False),
            (True, False, False),
        ):
            with self.subTest(window_visible=window_visible, preview_visible=preview_visible):
                # Arrange
                setup_ui = self.__create_setup(window_visible)
                setup_ui._frame_viewport.visible = preview_visible
                core = MagicMock()
                setup_ui._mass_cores_are_running = {id(core): True}

                # Act
                setup_ui._on_mass_cores_finished(core, True)

                # Assert
                self.assertFalse(setup_ui._mass_cores_are_running[id(core)])
                setup_ui._viewport.show.assert_called_once_with(expected)
                setup_ui._stage_view_widget.enable_context_event.assert_called_once_with(True)

    @staticmethod
    def __create_setup(visible):
        setup_ui = SetupUI.__new__(SetupUI)
        setup_ui._window_visible = visible
        setup_ui._mass_ingest_widget = MagicMock()
        setup_ui._viewport = MagicMock()
        setup_ui._frame_viewport = SimpleNamespace(visible=True)
        setup_ui._stage_view_widget = MagicMock()
        setup_ui._mass_cores_are_running = {}
        return setup_ui
