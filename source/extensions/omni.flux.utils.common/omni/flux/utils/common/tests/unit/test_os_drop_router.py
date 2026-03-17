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

from unittest.mock import MagicMock, patch

import omni.kit.test

from omni.flux.utils.common.os_drop_router import WidgetDropRouter


def _make_widget(*, visible=True, drop_handler=None, computed_width=100, computed_height=100):
    """Create a MagicMock widget satisfying the WidgetDropRouter contract."""
    widget = MagicMock()
    widget.drop_handler = drop_handler or MagicMock()
    widget.visible = visible
    widget.computed_width = computed_width
    widget.computed_height = computed_height
    return widget


class TestWidgetDropRouter(omni.kit.test.AsyncTestCase):
    def setUp(self):
        WidgetDropRouter.reset()

    def tearDown(self):
        WidgetDropRouter.reset()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def test_register_rejects_widget_without_callable_drop_handler(self):
        # Arrange
        widget = MagicMock(spec=[])
        widget.visible = True

        # Act / Assert
        with self.assertRaises(TypeError) as ctx:
            WidgetDropRouter.register_widget(widget)

        self.assertIn("drop_handler", str(ctx.exception))

    async def test_register_rejects_widget_without_visible_attribute(self):
        # Arrange
        class NoVisible:
            def drop_handler(self, e):
                return None

        widget = NoVisible()

        # Act / Assert
        with self.assertRaises(TypeError) as ctx:
            WidgetDropRouter.register_widget(widget)

        self.assertIn("visible", str(ctx.exception))

    async def test_register_succeeds_when_widget_satisfies_drop_contract(self):
        # Arrange
        widget = _make_widget()

        with patch("omni.appwindow.get_default_app_window") as mock_get_app_window:
            mock_stream = MagicMock()
            mock_get_app_window.return_value.get_window_drop_event_stream.return_value = mock_stream
            mock_stream.create_subscription_to_pop.return_value = MagicMock()

            # Act
            WidgetDropRouter.register_widget(widget)

            # Assert
            self.assertIn(widget, WidgetDropRouter._registered_widgets)
            mock_stream.create_subscription_to_pop.assert_called_once()

            WidgetDropRouter.unregister_widget(widget)

    async def test_register_raises_runtime_error_for_duplicate_widget(self):
        # Arrange
        widget = _make_widget()

        with patch("omni.appwindow.get_default_app_window") as mock_get_app_window:
            mock_stream = MagicMock()
            mock_get_app_window.return_value.get_window_drop_event_stream.return_value = mock_stream
            mock_stream.create_subscription_to_pop.return_value = MagicMock()
            WidgetDropRouter.register_widget(widget)

        # Act / Assert
        with self.assertRaises(RuntimeError) as ctx:
            WidgetDropRouter.register_widget(widget)

        self.assertIn("already registered", str(ctx.exception))

        WidgetDropRouter.unregister_widget(widget)

    async def test_first_register_creates_drop_event_subscription(self):
        # Arrange
        widget = _make_widget()

        with patch("omni.appwindow.get_default_app_window") as mock_get_app_window:
            mock_stream = MagicMock()
            mock_get_app_window.return_value.get_window_drop_event_stream.return_value = mock_stream
            mock_stream.create_subscription_to_pop.return_value = MagicMock()

            # Act
            WidgetDropRouter.register_widget(widget)

            # Assert
            self.assertIn(widget, WidgetDropRouter._registered_widgets)
            mock_stream.create_subscription_to_pop.assert_called_once()

            WidgetDropRouter.unregister_widget(widget)

    async def test_unregister_removes_widget_from_registry(self):
        # Arrange
        widget = _make_widget()

        with patch("omni.appwindow.get_default_app_window") as mock_get_app_window:
            mock_stream = MagicMock()
            mock_get_app_window.return_value.get_window_drop_event_stream.return_value = mock_stream
            mock_stream.create_subscription_to_pop.return_value = MagicMock()
            WidgetDropRouter.register_widget(widget)
            self.assertIn(widget, WidgetDropRouter._registered_widgets)

        # Act
        WidgetDropRouter.unregister_widget(widget)

        # Assert
        self.assertNotIn(widget, WidgetDropRouter._registered_widgets)

    # ------------------------------------------------------------------
    # Callback — position unknown
    # ------------------------------------------------------------------

    async def test_drop_with_unknown_mouse_position_logs_warning_and_skips_all_handlers(self):
        # Arrange
        widget = _make_widget()
        WidgetDropRouter._registered_widgets.add(widget)
        drop_event = MagicMock()

        # Act
        with (
            patch("omni.flux.utils.common.os_drop_router.get_mouse_position", return_value=None),
            patch("omni.flux.utils.common.os_drop_router.carb.log_warn") as mock_log_warn,
        ):
            WidgetDropRouter._global_drop_widget_router_callback(drop_event)

        # Assert
        widget.drop_handler.assert_not_called()
        mock_log_warn.assert_called_once()
        self.assertIn("mouse position could not be determined", mock_log_warn.call_args[0][0])

    # ------------------------------------------------------------------
    # Callback — position known, hit-test
    # ------------------------------------------------------------------

    async def test_drop_routes_to_only_the_widget_containing_the_mouse_point(self):
        # Arrange
        widget_inside = _make_widget()
        widget_outside = _make_widget()
        WidgetDropRouter._registered_widgets.add(widget_inside)
        WidgetDropRouter._registered_widgets.add(widget_outside)
        drop_event = MagicMock()

        # Act
        with (
            patch("omni.flux.utils.common.os_drop_router.get_mouse_position", return_value=(50, 50)),
            patch(
                "omni.flux.utils.common.os_drop_router.is_point_inside_widget",
                side_effect=lambda w, _pt: w is widget_inside,
            ),
        ):
            WidgetDropRouter._global_drop_widget_router_callback(drop_event)

        # Assert
        widget_inside.drop_handler.assert_called_once_with(drop_event)
        widget_outside.drop_handler.assert_not_called()

    async def test_drop_with_overlapping_widgets_routes_to_smallest_by_area(self):
        # Arrange
        widget_big = _make_widget(computed_width=200, computed_height=200)
        widget_small = _make_widget(computed_width=50, computed_height=50)
        WidgetDropRouter._registered_widgets.add(widget_big)
        WidgetDropRouter._registered_widgets.add(widget_small)
        drop_event = MagicMock()

        # Act
        with (
            patch("omni.flux.utils.common.os_drop_router.get_mouse_position", return_value=(75, 75)),
            patch("omni.flux.utils.common.os_drop_router.is_point_inside_widget", return_value=True),
        ):
            WidgetDropRouter._global_drop_widget_router_callback(drop_event)

        # Assert
        widget_small.drop_handler.assert_called_once_with(drop_event)
        widget_big.drop_handler.assert_not_called()

    async def test_drop_outside_all_widget_bounds_invokes_no_handler(self):
        # Arrange
        widget = _make_widget()
        WidgetDropRouter._registered_widgets.add(widget)
        drop_event = MagicMock()

        # Act
        with (
            patch("omni.flux.utils.common.os_drop_router.get_mouse_position", return_value=(100, 100)),
            patch("omni.flux.utils.common.os_drop_router.is_point_inside_widget", return_value=False),
        ):
            WidgetDropRouter._global_drop_widget_router_callback(drop_event)

        # Assert
        widget.drop_handler.assert_not_called()

    async def test_drop_skips_invisible_widgets_during_hit_test(self):
        # Arrange
        widget_visible = _make_widget(visible=True)
        widget_invisible = _make_widget(visible=False)
        WidgetDropRouter._registered_widgets.add(widget_visible)
        WidgetDropRouter._registered_widgets.add(widget_invisible)
        drop_event = MagicMock()

        # Act
        with (
            patch("omni.flux.utils.common.os_drop_router.get_mouse_position", return_value=(50, 50)),
            patch("omni.flux.utils.common.os_drop_router.is_point_inside_widget", return_value=True),
        ):
            WidgetDropRouter._global_drop_widget_router_callback(drop_event)

        # Assert
        widget_visible.drop_handler.assert_called_once_with(drop_event)
        widget_invisible.drop_handler.assert_not_called()

    # ------------------------------------------------------------------
    # Callback — error handling
    # ------------------------------------------------------------------

    async def test_drop_handler_exception_is_logged_without_crashing_the_router(self):
        # Arrange
        widget_bad = _make_widget(drop_handler=MagicMock(side_effect=ValueError("drop failed")))
        WidgetDropRouter._registered_widgets.add(widget_bad)
        drop_event = MagicMock()

        # Act
        with (
            patch("omni.flux.utils.common.os_drop_router.get_mouse_position", return_value=(50, 50)),
            patch("omni.flux.utils.common.os_drop_router.is_point_inside_widget", return_value=True),
            patch("omni.flux.utils.common.os_drop_router.carb.log_error") as mock_log_error,
        ):
            WidgetDropRouter._global_drop_widget_router_callback(drop_event)

        # Assert
        widget_bad.drop_handler.assert_called_once_with(drop_event)
        mock_log_error.assert_called_once()
        self.assertIn("drop_handler failed", mock_log_error.call_args[0][0])

    # ------------------------------------------------------------------
    # Callback — empty registry
    # ------------------------------------------------------------------

    async def test_drop_with_empty_registry_completes_without_error(self):
        # Arrange
        drop_event = MagicMock()

        # Act
        with patch("omni.flux.utils.common.os_drop_router.get_mouse_position", return_value=(50, 50)):
            WidgetDropRouter._global_drop_widget_router_callback(drop_event)

        # Assert
        self.assertEqual(len(WidgetDropRouter._registered_widgets), 0)
