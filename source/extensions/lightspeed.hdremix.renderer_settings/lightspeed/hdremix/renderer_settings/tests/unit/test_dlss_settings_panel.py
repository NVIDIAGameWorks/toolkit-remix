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

__all__ = ("TestDlssSettingsPanel",)

from unittest.mock import MagicMock, call, patch

from omni.kit.test import AsyncTestCase

from ... import dlss_settings_panel as _dlss_settings_panel
from ...dlss_settings import (
    DLSS_ADVANCED_SETTINGS,
    DLSS_ENABLE,
    DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS,
    DLSS_INTENSITY,
    DLSS_MAIN_SETTINGS,
    DLSS_MODEL,
)
from ...dlss_settings_panel import DlssSettingsPanel


def _make_panel(settings=None):
    """Build a panel shell for isolated callback tests."""
    panel = DlssSettingsPanel.__new__(DlssSettingsPanel)
    panel._settings = settings or MagicMock()
    panel._setting_subscriptions = []
    panel._widget_subscriptions = []
    panel._widgets = {}
    panel._updating_models = False
    return panel


class TestDlssSettingsPanel(AsyncTestCase):
    """Verify DLSS panel synchronization and lifecycle behavior."""

    def test_build_uses_marketing_order_and_collapsed_advanced_section(self):
        """The panel should expose only main controls before a collapsed advanced section."""
        # Arrange
        panel = _make_panel()
        with (
            patch.object(_dlss_settings_panel.ui, "VStack", return_value=MagicMock()),
            patch.object(_dlss_settings_panel.ui, "CollapsableFrame", return_value=MagicMock()) as frame_type,
            patch.object(panel, "_build_row") as build_row,
        ):
            # Act
            panel._build()

        # Assert
        frame_type.assert_called_once_with("Advanced Settings", collapsed=True, height=0)
        build_row.assert_has_calls([call(setting) for setting in DLSS_MAIN_SETTINGS + DLSS_ADVANCED_SETTINGS])
        self.assertEqual(build_row.call_count, len(DLSS_MAIN_SETTINGS) + len(DLSS_ADVANCED_SETTINGS))

    def test_float4_model_change_preserves_other_components(self):
        """Editing one vector component should preserve the other persisted components."""
        # Arrange
        setting = DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS
        settings = MagicMock()
        settings.get.return_value = [1.0, 8.0, 0.75, 0.99]
        panel = _make_panel(settings)
        value_model = MagicMock()
        value_model.as_float = 64.0

        # Act
        panel._on_float4_changed(setting, 1, value_model)

        # Assert
        settings.set.assert_called_once_with(setting.setting_path, [1.0, 32.0, 0.75, 0.99])

    def test_setting_change_synchronizes_two_panels(self):
        """A shared setting change should refresh every panel subscribed to that path."""
        # Arrange
        values = {DLSS_ENABLE.setting_path: False}
        callbacks = []
        settings = MagicMock()
        settings.get.side_effect = values.get
        settings.subscribe_to_node_change_events.side_effect = lambda path, callback: (
            callbacks.append((path, callback)) or MagicMock()
        )
        panels = [_make_panel(settings), _make_panel(settings)]
        for panel in panels:
            panel._widgets[DLSS_ENABLE.setting_path] = [MagicMock()]
            panel._subscribe_to_settings()

        def publish(path, value):
            """Publish one mocked carb setting change to every subscriber."""
            values[path] = value
            for subscribed_path, callback in callbacks:
                if subscribed_path == path:
                    callback()

        settings.set.side_effect = publish

        # Act
        settings.set(DLSS_ENABLE.setting_path, True)

        # Assert
        for panel in panels:
            panel._widgets[DLSS_ENABLE.setting_path][0].model.set_value.assert_called_once_with(True)

    def test_setting_refresh_does_not_echo_to_carb(self):
        """Model callbacks should not write while a setting refresh is in progress."""
        cases = (
            ("Boolean callback", DlssSettingsPanel._on_bool_changed, (DLSS_ENABLE,)),
            ("enum callback", DlssSettingsPanel._on_enum_changed, (DLSS_MODEL,)),
            ("scalar callback", DlssSettingsPanel._on_float_changed, (DLSS_INTENSITY,)),
            ("vector callback", DlssSettingsPanel._on_float4_changed, (DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS, 0)),
        )

        for title, callback, callback_args in cases:
            with self.subTest(title=title):
                # Arrange
                panel = _make_panel()
                panel._updating_models = True
                value_model = MagicMock()

                # Act
                callback(panel, *callback_args, value_model)

                # Assert
                panel._settings.set.assert_not_called()

    def test_setting_model_changes_persist_exact_values(self):
        """Boolean, enum, and scalar callbacks should persist their coerced model values."""
        # Arrange
        cases = (
            ("Boolean value", DlssSettingsPanel._on_bool_changed, DLSS_ENABLE, {"as_bool": True}, True),
            ("Model 2", DlssSettingsPanel._on_enum_changed, DLSS_MODEL, {"as_int": 2}, 2),
            (
                "clamped scalar value",
                DlssSettingsPanel._on_float_changed,
                DLSS_INTENSITY,
                {"as_float": 2.0},
                1.0,
            ),
        )

        for title, callback, setting, value_model_attributes, expected in cases:
            with self.subTest(title=title):
                # Arrange
                panel = _make_panel()
                value_model = MagicMock(**value_model_attributes)

                # Act
                callback(panel, setting, value_model)

                # Assert
                panel._settings.set.assert_called_once_with(setting.setting_path, expected)

    def test_refresh_updates_enum_selection_model_with_guard_enabled(self):
        """Refreshing an enum should update its selection model without writing back."""
        # Arrange
        settings = MagicMock()
        settings.get.return_value = 2
        panel = _make_panel(settings)
        widget = MagicMock()
        selection_model = widget.model.get_item_value_model.return_value
        guard_values = []
        selection_model.set_value.side_effect = lambda _value: guard_values.append(panel._updating_models)
        panel._widgets[DLSS_MODEL.setting_path] = [widget]

        # Act
        panel._refresh(DLSS_MODEL)

        # Assert
        selection_model.set_value.assert_called_once_with(2)
        widget.model.set_value.assert_not_called()
        self.assertEqual(guard_values, [True])
        self.assertFalse(panel._updating_models)

    def test_refresh_updates_all_vector_models_with_guard_enabled(self):
        """Refreshing a vector should update each model while the write-back guard is enabled."""
        # Arrange
        setting = DLSS_HIGHLIGHT_RECOVERY_THRESHOLDS
        settings = MagicMock()
        settings.get.return_value = [2.0, 3.0, 4.0, 5.0]
        panel = _make_panel(settings)
        widgets = [MagicMock() for _ in range(4)]
        guard_values = []
        for widget in widgets:
            widget.model.set_value.side_effect = lambda _value: guard_values.append(panel._updating_models)
        panel._widgets[setting.setting_path] = widgets

        # Act
        panel._refresh(setting)

        # Assert
        for widget, expected in zip(widgets, settings.get.return_value):
            widget.model.set_value.assert_called_once_with(expected)
        self.assertEqual(guard_values, [True, True, True, True])
        self.assertFalse(panel._updating_models)

    def test_refresh_with_missing_widgets_does_not_read_setting(self):
        """Refreshing an unbuilt setting should not read persisted state or leave the guard set."""
        # Arrange
        panel = _make_panel()

        # Act
        panel._refresh(DLSS_ENABLE)

        # Assert
        panel._settings.get.assert_not_called()
        self.assertFalse(panel._updating_models)

    def test_refresh_restores_guard_when_model_update_fails(self):
        """A failed model update should still restore the write-back guard."""
        # Arrange
        settings = MagicMock()
        settings.get.return_value = True
        panel = _make_panel(settings)
        widget = MagicMock()
        widget.model.set_value.side_effect = RuntimeError("model update failed")
        panel._widgets[DLSS_ENABLE.setting_path] = [widget]

        # Act
        with self.assertRaisesRegex(RuntimeError, "model update failed") as raised:
            panel._refresh(DLSS_ENABLE)

        # Assert
        self.assertEqual(str(raised.exception), "model update failed")
        self.assertFalse(panel._updating_models)

    def test_destroy_unsubscribes_setting_changes(self):
        """Destroying the panel should release subscriptions and widget references."""
        # Arrange
        panel = _make_panel()
        subscriptions = [MagicMock(), MagicMock()]
        panel._setting_subscriptions = subscriptions.copy()
        panel._widget_subscriptions = [MagicMock()]
        panel._widgets = {DLSS_ENABLE.setting_path: [MagicMock()]}

        # Act
        panel.destroy()

        # Assert
        self.assertEqual(
            panel._settings.unsubscribe_to_change_events.call_args_list,
            [((subscription,), {}) for subscription in subscriptions],
        )
        self.assertEqual(panel._setting_subscriptions, [])
        self.assertEqual(panel._widget_subscriptions, [])
        self.assertEqual(panel._widgets, {})
