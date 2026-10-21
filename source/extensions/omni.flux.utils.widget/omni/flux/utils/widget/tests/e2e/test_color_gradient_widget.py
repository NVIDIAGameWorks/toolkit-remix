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

__all__ = ("TestColorGradientWidget",)

import uuid

import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.kit.ui_test import Vec2
from omni.kit.ui_test.input import emulate_mouse_move_and_click

from omni.flux.utils.widget import InMemoryGroupedKeysModel
from omni.flux.utils.widget.color_gradient import ColorGradientWidget, GradientPreview

_GROUP_ID = "gradient"


def _payload_from_keyframes(keyframes):
    return {
        "times": [time for time, _color in keyframes],
        "values": [color for _time, color in keyframes],
    }


class _LoggingGroupedKeysModel(InMemoryGroupedKeysModel):
    def __init__(self, payload=None):
        """Initialize the model and its commit log."""
        payloads = {_GROUP_ID: payload} if payload is not None else None
        super().__init__(group_ids=[_GROUP_ID], payloads=payloads)
        self.commit_log = []

    def commit_payload(self, group_id: str, payload: dict) -> None:
        super().commit_payload(group_id, payload)
        self.commit_log.append((group_id, payload))


async def _wait_updates(n: int = 3):
    """Wait for *n* Kit UI update frames."""
    await omni.kit.ui_test.human_delay(n)


class TestColorGradientWidget(omni.kit.test.AsyncTestCase):
    """UI tests for the ColorGradientWidget standalone widget."""

    async def setUp(self):
        self._window = ui.Window(
            f"TestGradientWidget_{uuid.uuid1()}",
            height=200,
            width=400,
            position_x=0,
            position_y=0,
        )
        self._gradient_widget = None
        self._gradient_model = None

    async def tearDown(self):
        """Destroy the widget, model, and window in dependency order."""
        try:
            if self._gradient_widget:
                self._gradient_widget.destroy()
                await _wait_updates()
        finally:
            self._gradient_widget = None
            try:
                if self._gradient_model:
                    self._gradient_model.destroy()
            finally:
                self._gradient_model = None
                try:
                    if self._window:
                        self._window.destroy()
                finally:
                    self._window = None

    def _build_widget(self, keyframes=None):
        """Build the gradient editor with optional initial keyframes."""
        self._gradient_model = _LoggingGroupedKeysModel(
            _payload_from_keyframes(keyframes) if keyframes is not None else None
        )
        with self._window.frame:
            self._gradient_widget = ColorGradientWidget(self._gradient_model, _GROUP_ID, GradientPreview())
            self._gradient_widget.build_editor()

    async def _select_preset(self, name: str):
        """Select a preset or operation through the embedded editor's native menu."""
        await omni.kit.ui_test.find(f"{self._window.title}//Frame/**/Image[*].name=='MenuBurger'").click()
        await omni.kit.ui_test.human_delay()
        await omni.kit.ui_test.select_context_menu(name)
        await omni.kit.ui_test.human_delay()

    async def _assert_preset_keyframes(self, preset_name: str, expected_keyframes: list):
        """Apply a named preset and verify its rendered keyframes."""
        self._build_widget()
        await _wait_updates()
        await self._select_preset(preset_name)

        self.assertEqual(self._gradient_widget.get_keyframes(), expected_keyframes)

    async def test_embedded_bar_click_adds_interpolated_key_and_commits_complete_payload_once(self):
        """Embedded editing content adds one interpolated key without owning a window."""
        initial = [(0.0, (1.0, 0.0, 0.0, 1.0)), (1.0, (0.0, 0.0, 1.0, 1.0))]
        visible_windows = {window.title for window in ui.Workspace.get_windows() if window.visible}
        self._build_widget(keyframes=initial)
        await _wait_updates()
        self.assertEqual({window.title for window in ui.Workspace.get_windows() if window.visible}, visible_windows)
        bar = omni.kit.ui_test.find(
            f"{self._window.title}//Frame/**/Rectangle[*].name=='ColorGradientBarOverlay'"
        ).widget
        position = Vec2(
            round(bar.screen_position_x + bar.computed_width * 0.25),
            round(bar.screen_position_y + bar.computed_height / 2),
        )
        expected_time = round((position.x - bar.screen_position_x) / bar.computed_width, 5)
        expected_color = (1.0 - expected_time, 0.0, expected_time, 1.0)
        self._gradient_model.commit_log.clear()

        # Embedded content uses its own rendered bounds, without a property-editor host.
        await emulate_mouse_move_and_click(position)
        await omni.kit.ui_test.human_delay()

        expected = [initial[0], (expected_time, expected_color), initial[1]]
        self.assertEqual(self._gradient_widget.get_keyframes(), expected)
        self.assertEqual(self._gradient_model.commit_log, [(_GROUP_ID, _payload_from_keyframes(expected))])
        self.assertTrue(self._window.visible)

    async def test_preset_grayscale(self):
        """Grayscale should create a black-to-white gradient through the real menu."""
        await self._assert_preset_keyframes(
            "Grayscale",
            [(0.0, (0.0, 0.0, 0.0, 1.0)), (1.0, (1.0, 1.0, 1.0, 1.0))],
        )

    async def test_preset_linear_red(self):
        """Linear Red should create a black-to-red gradient through the real menu."""
        await self._assert_preset_keyframes(
            "Linear Red",
            [(0.0, (0.0, 0.0, 0.0, 1.0)), (1.0, (1.0, 0.0, 0.0, 1.0))],
        )

    async def test_preset_transparent_to_opaque(self):
        """Transparent to Opaque should create transparent and opaque white stops."""
        await self._assert_preset_keyframes(
            "Transparent to Opaque",
            [(0.0, (1.0, 1.0, 1.0, 0.0)), (1.0, (1.0, 1.0, 1.0, 1.0))],
        )

    async def test_operation_reverse_gradient(self):
        """Reverse should flip the active gradient through the real menu."""
        self._build_widget()
        await _wait_updates()
        await self._select_preset("Grayscale")
        await self._select_preset("Reverse")

        self.assertEqual(
            self._gradient_widget.get_keyframes(),
            [(0.0, (1.0, 1.0, 1.0, 1.0)), (1.0, (0.0, 0.0, 0.0, 1.0))],
        )
