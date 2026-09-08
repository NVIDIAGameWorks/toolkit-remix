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

from unittest.mock import Mock, patch

import omni.kit.test
from omni import ui

from ...base import state_base

__all__ = ["TestStageManagerStateWidgetPlugin"]


class _ConcreteStateWidgetPlugin(state_base.StageManagerStateWidgetPlugin):
    """Provide a concrete state widget for action-image tests."""

    def build_icon_ui(self, model, item, level: int, expanded: bool):
        """Satisfy the state-widget interface without building UI."""
        pass


class TestStageManagerStateWidgetPlugin(omni.kit.test.AsyncTestCase):
    """Test shared Stage Manager action-image construction."""

    async def test_make_action_image_enabled_callback_owns_mouse_gesture(self):
        """Verify an enabled action callback owns the mouse gesture."""
        # Arrange
        plugin = _ConcreteStateWidgetPlugin()
        model = Mock()
        item = Mock()
        release_callback = Mock()

        with patch.object(state_base.ui, "Image") as mock_image:
            # Act
            plugin.make_action_image(
                model=model,
                item=item,
                name="Action",
                tooltip="Action tooltip",
                identifier="action_id",
                mouse_released_fn=release_callback,
            )
            image_kwargs = mock_image.call_args.kwargs

        # Assert
        self.assertEqual(mock_image.call_args.args, ("",))
        self.assertEqual(str(image_kwargs["width"]), str(plugin._icon_size))
        self.assertEqual(str(image_kwargs["height"]), str(plugin._icon_size))
        self.assertEqual(image_kwargs["name"], "Action")
        self.assertEqual(image_kwargs["tooltip"], "Action tooltip")
        self.assertEqual(image_kwargs["identifier"], "action_id")
        self.assertTrue(image_kwargs["enabled"])
        self.assertTrue(image_kwargs["opaque_for_mouse_events"])
        self.assertTrue(callable(image_kwargs["mouse_pressed_fn"]))
        self.assertIs(image_kwargs["mouse_released_fn"], release_callback)

    async def test_make_action_image_press_forwards_all_buttons_and_validates_left_and_right(self):
        """Verify all presses are forwarded while left and right validate selection."""
        for title, button, should_validate_selection in (
            ("left_button", 0, True),
            ("right_button", 1, True),
            ("middle_button", 2, False),
        ):
            with self.subTest(title=title):
                # Arrange
                plugin = _ConcreteStateWidgetPlugin()
                model = Mock()
                item = Mock()
                release_callback = Mock()
                with (
                    patch.object(state_base.ui, "Image") as mock_image,
                    patch.object(plugin, "_item_clicked") as mock_item_clicked,
                ):
                    plugin.make_action_image(
                        model=model,
                        item=item,
                        name="Action",
                        tooltip="Action tooltip",
                        mouse_released_fn=release_callback,
                    )
                    mouse_pressed_fn = mock_image.call_args.kwargs["mouse_pressed_fn"]

                    # Act
                    mouse_pressed_fn(0, 0, button, 0)

                    # Assert
                    mock_item_clicked.assert_called_once_with(button, should_validate_selection, model, item)

    async def test_make_action_image_disabled_callback_does_not_own_mouse_gesture(self):
        """Verify a disabled action callback leaves mouse gestures unowned."""
        # Arrange
        plugin = _ConcreteStateWidgetPlugin()
        model = Mock()
        item = Mock()
        release_callback = Mock()

        with patch.object(state_base.ui, "Image") as mock_image:
            # Act
            plugin.make_action_image(
                model=model,
                item=item,
                name="Action",
                tooltip="Action tooltip",
                mouse_released_fn=release_callback,
                enabled=False,
            )

        # Assert
        image_kwargs = mock_image.call_args.kwargs
        self.assertFalse(image_kwargs["enabled"])
        self.assertFalse(image_kwargs["opaque_for_mouse_events"])
        self.assertIsNone(image_kwargs["mouse_pressed_fn"])
        self.assertIs(image_kwargs["mouse_released_fn"], release_callback)

    async def test_make_action_image_without_callback_does_not_own_mouse_gesture(self):
        """Verify an image without an action callback leaves mouse gestures unowned."""
        # Arrange
        plugin = _ConcreteStateWidgetPlugin()
        model = Mock()
        item = Mock()
        custom_height = ui.Pixel(32)

        with patch.object(state_base.ui, "Image") as mock_image:
            # Act
            plugin.make_action_image(
                model=model,
                item=item,
                name="Action",
                tooltip="Action tooltip",
                height=custom_height,
            )

        # Assert
        image_kwargs = mock_image.call_args.kwargs
        self.assertFalse(image_kwargs["opaque_for_mouse_events"])
        self.assertIsNone(image_kwargs["mouse_pressed_fn"])
        self.assertIsNone(image_kwargs["mouse_released_fn"])
        self.assertIs(image_kwargs["height"], custom_height)
        self.assertEqual(str(image_kwargs["width"]), str(plugin._icon_size))
