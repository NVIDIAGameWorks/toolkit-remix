"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import carb
from omni import ui
from omni.kit.widget.settings import create_setting_widget
from omni.kit.window.preferences import PreferenceBuilder, SettingType

from .core import SETTINGS_ENABLED, SETTINGS_INTERVAL_SECONDS, _DEFAULT_INTERVAL_SECONDS

# Preset labels and their corresponding interval in seconds (None = custom)
_PRESET_LABELS = ["30 seconds", "1 minute", "5 minutes", "10 minutes", "30 minutes", "1 hour", "Custom..."]
_PRESET_SECONDS = [30, 60, 300, 600, 1800, 3600, None]

_SETTINGS_PRESET_INDEX = "/persistent/exts/lightspeed.event.autosave/preset_index"
_SETTINGS_CUSTOM_VALUE = "/persistent/exts/lightspeed.event.autosave/custom_value"
_SETTINGS_CUSTOM_UNIT = "/persistent/exts/lightspeed.event.autosave/custom_unit"

_UNIT_LABELS = ["Seconds", "Minutes", "Hours"]
_UNIT_MULTIPLIERS = [1, 60, 3600]

_DEFAULT_PRESET_INDEX = 2  # "5 minutes"
_DEFAULT_CUSTOM_VALUE = 5
_DEFAULT_CUSTOM_UNIT = 1  # Minutes

_CUSTOM_INDEX = len(_PRESET_LABELS) - 1


def _read_int(key: str, default: int) -> int:
    """Read an integer carb setting, returning default if unset (avoids falsy-0 bug with `or`)."""
    value = carb.settings.get_settings().get(key)
    return int(value) if value is not None else default


def _get_preset_index_for_seconds(seconds: int) -> int:
    """Return the preset index matching the given interval, or the Custom index if no match."""
    for i, preset_seconds in enumerate(_PRESET_SECONDS):
        if preset_seconds == seconds:
            return i
    return _CUSTOM_INDEX


class AutoSavePreferencePage(PreferenceBuilder):
    """Preference page that adds Auto-Save settings to the Kit preferences window."""

    def __init__(self):
        super().__init__("Auto-Save")
        self._settings = carb.settings.get_settings()
        self._preset_sub = None
        self._custom_value_sub = None
        self._custom_unit_sub = None
        self._custom_stack = None
        self._preset_combo = None
        self._unit_combo = None

        # Initialise settings that may not exist yet
        if self._settings.get(_SETTINGS_PRESET_INDEX) is None:
            current_interval = self._settings.get(SETTINGS_INTERVAL_SECONDS) or _DEFAULT_INTERVAL_SECONDS
            self._settings.set(_SETTINGS_PRESET_INDEX, _get_preset_index_for_seconds(current_interval))
        if self._settings.get(_SETTINGS_CUSTOM_VALUE) is None:
            self._settings.set(_SETTINGS_CUSTOM_VALUE, _DEFAULT_CUSTOM_VALUE)
        if self._settings.get(_SETTINGS_CUSTOM_UNIT) is None:
            self._settings.set(_SETTINGS_CUSTOM_UNIT, _DEFAULT_CUSTOM_UNIT)

    def build(self):
        with ui.VStack(height=0):
            with self.add_frame("Auto-Save"):
                with ui.VStack(spacing=4):
                    self._build_enable_row()
                    self._build_preset_row()
                    self._build_custom_row()

    def _build_enable_row(self):
        with ui.HStack(height=24):
            ui.Label("Enable Auto-Save", style_type_name_override="Setting.Label", width=ui.Percent(50))
            create_setting_widget(SETTINGS_ENABLED, SettingType.BOOL)

    def _build_preset_row(self):
        preset_index = _read_int(_SETTINGS_PRESET_INDEX, _DEFAULT_PRESET_INDEX)
        with ui.HStack(height=24):
            ui.Label("Interval", style_type_name_override="Setting.Label", width=ui.Percent(50))
            self._preset_combo = ui.ComboBox(preset_index, *_PRESET_LABELS)
        # Subscribe to the IntValueModel that tracks the current selection index.
        # subscribe_item_changed_fn fires when the item LIST changes, not the selection;
        # the selection is an integer on the combo's value model.
        self._preset_sub = self._preset_combo.model.get_item_value_model().subscribe_value_changed_fn(
            self._on_preset_selection_changed
        )

    def _build_custom_row(self):
        preset_index = _read_int(_SETTINGS_PRESET_INDEX, _DEFAULT_PRESET_INDEX)
        self._custom_stack = ui.HStack(height=24, visible=(preset_index == _CUSTOM_INDEX))
        with self._custom_stack:
            ui.Label("Custom Interval", style_type_name_override="Setting.Label", width=ui.Percent(50))
            _value_widget, value_model = create_setting_widget(
                _SETTINGS_CUSTOM_VALUE, SettingType.INT, min=1, max=99999
            )
            # Update SETTINGS_INTERVAL_SECONDS whenever the typed value changes
            self._custom_value_sub = value_model.subscribe_value_changed_fn(
                lambda _m: self._recompute_custom_interval()
            )

            custom_unit = _read_int(_SETTINGS_CUSTOM_UNIT, _DEFAULT_CUSTOM_UNIT)
            self._unit_combo = ui.ComboBox(custom_unit, *_UNIT_LABELS)
            self._custom_unit_sub = self._unit_combo.model.get_item_value_model().subscribe_value_changed_fn(
                lambda _m: self._recompute_custom_interval()
            )

    def _on_preset_selection_changed(self, value_model):
        index = value_model.as_int
        self._settings.set(_SETTINGS_PRESET_INDEX, index)

        is_custom = index == _CUSTOM_INDEX
        if self._custom_stack:
            self._custom_stack.visible = is_custom

        if not is_custom:
            self._settings.set(SETTINGS_INTERVAL_SECONDS, _PRESET_SECONDS[index])
        else:
            self._recompute_custom_interval()

    def _recompute_custom_interval(self):
        value = _read_int(_SETTINGS_CUSTOM_VALUE, _DEFAULT_CUSTOM_VALUE)
        unit_index = self._unit_combo.model.get_item_value_model().as_int if self._unit_combo else _DEFAULT_CUSTOM_UNIT
        self._settings.set(_SETTINGS_CUSTOM_UNIT, unit_index)
        self._settings.set(SETTINGS_INTERVAL_SECONDS, max(1, value * _UNIT_MULTIPLIERS[unit_index]))

    def destroy(self):
        self._preset_sub = None
        self._custom_value_sub = None
        self._custom_unit_sub = None
        self._preset_combo = None
        self._unit_combo = None
        self._custom_stack = None
