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

__all__ = ["DlssSettingsPanel"]

import carb.settings
import omni.ui as ui

from .dlss_settings import (
    DLSS_ADVANCED_SETTINGS,
    DLSS_FLOAT4_RANGE,
    DLSS_MAIN_SETTINGS,
    DLSS_SETTINGS,
    DLSS_UNIT_FLOAT_RANGE,
    DlssSetting,
    DlssSettingKind,
    coerce_dlss_value,
)

_ROW_HEIGHT = ui.Pixel(24)
_CHECKBOX_WIDTH = ui.Pixel(20)
_COMPONENT_SPACING = ui.Pixel(2)


class DlssSettingsPanel:
    """Build and synchronize the shared DLSS Neural Rendering controls."""

    def __init__(self, identifier_prefix: str, label_style: str | None = None):
        """Build controls in the active UI scope.

        Args:
            identifier_prefix: Prefix that makes widget identifiers unique to the host panel.
            label_style: Optional style override for row labels.
        """
        self._settings = carb.settings.get_settings()
        self._identifier_prefix = identifier_prefix
        self._label_style = label_style
        self._setting_subscriptions = []
        self._widget_subscriptions = []
        self._widgets: dict[str, list[object]] = {}
        self._updating_models = False
        self._build()
        self._subscribe_to_settings()

    def _build(self) -> None:
        """Build every control from the shared setting descriptors."""
        with ui.VStack(spacing=ui.Pixel(4)):
            for setting in DLSS_MAIN_SETTINGS:
                self._build_row(setting)
            with ui.CollapsableFrame("Advanced Settings", collapsed=True, height=0):
                with ui.VStack(spacing=ui.Pixel(4)):
                    for setting in DLSS_ADVANCED_SETTINGS:
                        self._build_row(setting)

    def _build_row(self, setting: DlssSetting) -> None:
        """Build the label and editor for one setting."""
        label_args = {
            "width": ui.Percent(50),
            "tooltip": setting.tooltip,
        }
        if self._label_style is not None:
            label_args["style_type_name_override"] = self._label_style

        with ui.HStack(height=_ROW_HEIGHT):
            ui.Label(setting.label, **label_args)
            if setting.kind == DlssSettingKind.BOOL:
                self._build_bool(setting)
            elif setting.kind == DlssSettingKind.ENUM:
                self._build_enum(setting)
            elif setting.kind == DlssSettingKind.UNIT_FLOAT:
                self._build_float(setting)
            else:
                self._build_float4(setting)

    def _build_bool(self, setting: DlssSetting) -> None:
        """Build a Boolean setting editor."""
        widget = ui.CheckBox(
            width=_CHECKBOX_WIDTH,
            identifier=f"{self._identifier_prefix}_{setting.identifier}",
        )
        widget.model.set_value(coerce_dlss_value(setting, self._settings.get(setting.setting_path)))
        self._widgets[setting.setting_path] = [widget]
        self._widget_subscriptions.append(
            widget.model.subscribe_value_changed_fn(
                lambda value_model, current=setting: self._on_bool_changed(current, value_model)
            )
        )

    def _build_enum(self, setting: DlssSetting) -> None:
        """Build an integer-enum setting editor."""
        selected = coerce_dlss_value(setting, self._settings.get(setting.setting_path))
        widget = ui.ComboBox(
            selected,
            *setting.options,
            identifier=f"{self._identifier_prefix}_{setting.identifier}",
        )
        self._widgets[setting.setting_path] = [widget]
        self._widget_subscriptions.append(
            widget.model.get_item_value_model().subscribe_value_changed_fn(
                lambda value_model, current=setting: self._on_enum_changed(current, value_model)
            )
        )

    def _build_float(self, setting: DlssSetting) -> None:
        """Build a unit-float setting editor."""
        widget = ui.FloatDrag(
            min=DLSS_UNIT_FLOAT_RANGE[0],
            max=DLSS_UNIT_FLOAT_RANGE[1],
            identifier=f"{self._identifier_prefix}_{setting.identifier}",
        )
        widget.model.set_value(coerce_dlss_value(setting, self._settings.get(setting.setting_path)))
        self._widgets[setting.setting_path] = [widget]
        self._widget_subscriptions.append(
            widget.model.subscribe_value_changed_fn(
                lambda value_model, current=setting: self._on_float_changed(current, value_model)
            )
        )

    def _build_float4(self, setting: DlssSetting) -> None:
        """Build a four-component float setting editor."""
        widgets = []
        values = coerce_dlss_value(setting, self._settings.get(setting.setting_path))
        with ui.HStack(spacing=_COMPONENT_SPACING):
            for index, value in enumerate(values):
                widget = ui.FloatDrag(
                    min=DLSS_FLOAT4_RANGE[0],
                    max=DLSS_FLOAT4_RANGE[1],
                    identifier=f"{self._identifier_prefix}_{setting.identifier}_{index}",
                )
                widget.model.set_value(value)
                widgets.append(widget)
                self._widget_subscriptions.append(
                    widget.model.subscribe_value_changed_fn(
                        lambda value_model, component=index, current=setting: self._on_float4_changed(
                            current, component, value_model
                        )
                    )
                )
        self._widgets[setting.setting_path] = widgets

    def _subscribe_to_settings(self) -> None:
        """Subscribe the panel to persistent setting changes."""
        for setting in DLSS_SETTINGS:
            subscription = self._settings.subscribe_to_node_change_events(
                setting.setting_path,
                lambda *_args, current=setting, **_kwargs: self._refresh(current),
            )
            self._setting_subscriptions.append(subscription)

    def _refresh(self, setting: DlssSetting) -> None:
        """Refresh the widgets associated with one setting."""
        widgets = self._widgets.get(setting.setting_path)
        if widgets is None:
            return
        value = coerce_dlss_value(setting, self._settings.get(setting.setting_path))
        values = value if isinstance(value, list) else [value]
        value_models = (
            [widgets[0].model.get_item_value_model()]
            if setting.kind == DlssSettingKind.ENUM
            else [widget.model for widget in widgets]
        )
        self._updating_models = True
        try:
            for value_model, component in zip(value_models, values):
                value_model.set_value(component)
        finally:
            self._updating_models = False

    def _on_bool_changed(self, setting: DlssSetting, value_model: ui.AbstractValueModel) -> None:
        """Persist a Boolean editor change."""
        if not self._updating_models:
            self._settings.set(setting.setting_path, bool(value_model.as_bool))

    def _on_enum_changed(self, setting: DlssSetting, value_model: ui.AbstractValueModel) -> None:
        """Persist an integer-enum editor change."""
        if not self._updating_models:
            self._settings.set(setting.setting_path, coerce_dlss_value(setting, value_model.as_int))

    def _on_float_changed(self, setting: DlssSetting, value_model: ui.AbstractValueModel) -> None:
        """Persist a unit-float editor change."""
        if not self._updating_models:
            self._settings.set(setting.setting_path, coerce_dlss_value(setting, value_model.as_float))

    def _on_float4_changed(self, setting: DlssSetting, index: int, value_model: ui.AbstractValueModel) -> None:
        """Persist one component of a four-component editor."""
        if self._updating_models:
            return
        values = coerce_dlss_value(setting, self._settings.get(setting.setting_path))
        values[index] = value_model.as_float
        self._settings.set(setting.setting_path, coerce_dlss_value(setting, values))

    def destroy(self) -> None:
        """Unsubscribe from persistent setting changes and release UI references."""
        for subscription in self._setting_subscriptions:
            self._settings.unsubscribe_to_change_events(subscription)
        self._setting_subscriptions.clear()
        self._widget_subscriptions.clear()
        self._widgets.clear()
