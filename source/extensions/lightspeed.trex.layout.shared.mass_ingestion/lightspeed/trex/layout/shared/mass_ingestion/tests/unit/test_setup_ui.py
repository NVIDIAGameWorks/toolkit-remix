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
