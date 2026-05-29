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

import carb
import carb.settings
import omni.ui as ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.window.preferences import PreferenceBuilder

from .settings_bridge import (
    DEFAULT_INTEGRATE_INDIRECT_MODE,
    DEFAULT_OVERRIDE_CAPTURE_INTEGRATOR,
    INTEGRATE_INDIRECT_MODE_LABELS,
    SETTINGS_INTEGRATE_INDIRECT_MODE,
    SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR,
    coerce_mode,
)


class HdRemixRendererPreferencePage(PreferenceBuilder):
    """Preferences page adding HdRemix renderer toggles under Edit > Preferences > HdRemix Renderer."""

    def __init__(self):
        super().__init__("HdRemix Renderer")
        # default_attr drives destroy() via _reset_default_attrs — matches the bridge
        # cleanup pattern. Anything held on to and released on destroy must be listed here.
        self.default_attr = {
            "_settings": None,
            "_integrate_indirect_combo": None,
            "_integrate_indirect_sub": None,
            "_override_capture_checkbox": None,
            "_override_capture_sub": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._settings = carb.settings.get_settings()
        if self._settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE) is None:
            self._settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, DEFAULT_INTEGRATE_INDIRECT_MODE)
        if self._settings.get(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR) is None:
            self._settings.set(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, DEFAULT_OVERRIDE_CAPTURE_INTEGRATOR)

    def build(self) -> None:
        # Re-acquire the carb settings handle on every build: Kit's preference
        # window destroys + rebuilds the page on tab switches and after closing
        # the window, and our destroy() nullifies _settings via
        # _reset_default_attrs(). Without this, the SECOND build() (user
        # navigates away then back) crashes silently in _build_integrator_row
        # with AttributeError: 'NoneType' has no attribute 'get', leaving the
        # right pane empty.
        if self._settings is None:
            self._settings = carb.settings.get_settings()
        with ui.VStack(height=0):
            # Section + control labels match the dxvk-remix runtime overlay
            # ("INDIRECT ILLUMINATION" section, "Integrate Indirect Illumination Mode"
            # combo) so this Kit preferences page reads identical to the in-game UI.
            with self.add_frame("Indirect Illumination"):
                with ui.VStack(spacing=4):
                    self._build_override_capture_row()
                    self._build_integrator_row()

    def _build_override_capture_row(self) -> None:
        # When unchecked (default), the bridge skips its startup push so each loaded
        # capture's preset value applies. When checked, the global preference is
        # pushed to the runtime on startup and overrides the capture-supplied value.
        # User toggles of the combo below always push regardless (explicit action).
        self._override_capture_sub = None
        self._override_capture_checkbox = None
        current = bool(self._settings.get(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR))
        with ui.HStack(height=24):
            ui.Label(
                "Override Capture Value",
                style_type_name_override="Setting.Label",
                width=ui.Percent(50),
                tooltip=(
                    "When OFF (default), the loaded capture's integrator preset wins on "
                    "stage open.\nWhen ON, the global value in the combo below is pushed "
                    "to the renderer and overrides the capture's preset."
                ),
            )
            self._override_capture_checkbox = ui.CheckBox(width=20)
            self._override_capture_checkbox.model.set_value(current)
        self._override_capture_sub = self._override_capture_checkbox.model.subscribe_value_changed_fn(
            self._on_override_capture_changed
        )

    def _on_override_capture_changed(self, value_model: ui.AbstractValueModel):
        self._settings.set(SETTINGS_OVERRIDE_CAPTURE_INTEGRATOR, bool(value_model.as_bool))

    def _build_integrator_row(self) -> None:
        # PreferenceBuilder.build() can fire more than once per page lifetime (Kit
        # rebuilds preference pages on tab switch); drop any prior subscription +
        # combo before creating new ones so we don't accumulate orphan handlers
        # that double-write the carb setting on every change.
        self._integrate_indirect_sub = None
        self._integrate_indirect_combo = None
        current_index = coerce_mode(self._settings.get(SETTINGS_INTEGRATE_INDIRECT_MODE))
        with ui.HStack(height=24):
            ui.Label(
                "Integrate Indirect Illumination Mode",
                style_type_name_override="Setting.Label",
                width=ui.Percent(50),
                tooltip=(
                    "Indirect lighting integrator used by the HdRemix renderer.\n"
                    "Switches live without re-capturing the scene."
                ),
            )
            self._integrate_indirect_combo = ui.ComboBox(current_index, *INTEGRATE_INDIRECT_MODE_LABELS)
        self._integrate_indirect_sub = (
            self._integrate_indirect_combo.model.get_item_value_model().subscribe_value_changed_fn(
                self._on_integrator_changed
            )
        )

    def _on_integrator_changed(self, value_model: ui.AbstractValueModel):
        index = value_model.as_int
        if not (0 <= index < len(INTEGRATE_INDIRECT_MODE_LABELS)):
            return
        self._settings.set(SETTINGS_INTEGRATE_INDIRECT_MODE, index)

    def destroy(self):
        _reset_default_attrs(self)
