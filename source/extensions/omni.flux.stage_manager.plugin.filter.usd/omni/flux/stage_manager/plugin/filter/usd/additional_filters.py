"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from omni.flux.stage_manager.core import get_instance as _get_stage_manager_core_instance
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.kit.widget.options_menu.popup_menu import AbstractPopupMenu, PopupMenuDelegate, PopupMenuItemDelegate
from pydantic import Field, PrivateAttr

from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin
from .base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin

EXCLUDE_FILTERS = ["AdditionalFilterPlugin", "SearchFilterPlugin"]


class AdditionalFiltersPopupMenuItemDelegate(PopupMenuItemDelegate):
    def __init__(self, filter_obj: _StageManagerUSDFilterPlugin, value: dict, on_filter_changed_fn=None):
        super().__init__()
        self.filter_obj = filter_obj
        self.text = filter_obj.display_name
        self.filter_active = value.get("filter_active", False)
        self.filter_type = value.get("filter_type", "other")
        self._on_filter_changed_fn = on_filter_changed_fn
        self._filter_changed_sub = None
        self._container = None

    @property
    def container(self):
        """Get the UI container"""
        return self._container

    def build_item(self):
        """Build the item UI."""
        if not self.container:
            self._container = ui.HStack(height=0, spacing=ui.Pixel(8))
        else:
            self.container.clear()

        # Restore the saved filter_active state from the value dictionary
        if isinstance(self.filter_obj, _ToggleableUSDFilterPlugin):
            self.filter_obj.filter_active = self.filter_active

        # Add a subscription to the filter's _filter_items_changed to call function that updates the icon
        if self._on_filter_changed_fn and not self._filter_changed_sub:
            self._filter_changed_sub = self.filter_obj.subscribe_filter_items_changed(self._on_filter_changed_fn)

        with self._container:
            ui.Spacer(width=0)
            with ui.VStack(width=0, spacing=ui.Pixel(4)):
                self.filter_obj.build_ui()
                if not isinstance(self.filter_obj, _ToggleableUSDFilterPlugin):
                    ui.Spacer(width=0)
            ui.Spacer(width=0)

    def destroy(self):
        super().destroy()
        self._filter_changed_sub = None


class AdditionalFiltersPopupMenu(AbstractPopupMenu):
    def __init__(self, title, filters: list[_StageManagerUSDFilterPlugin], on_filter_changed_fn=None):
        self._delegate = AdditionalFiltersPopupMenuDelegate(filters, on_filter_changed_fn)
        super().__init__(title, self._delegate)
        self.filters = filters

    def build_menu_items(self):
        with ui.VStack(width=0, spacing=ui.Pixel(4)):
            ui.Spacer(width=0)
            with ui.HStack():
                ui.Spacer(width=4)
                ui.Label("Multi-Option Filters", name="PropertiesPaneSectionTitle")
            for item in self._delegate.items:
                if item.filter_type == "other":
                    item.build_item()
            with ui.HStack():
                ui.Spacer(width=4)
                ui.Label("Prim Filters", name="PropertiesPaneSectionTitle")
            for item in self._delegate.items:
                if item.filter_type == "prims":
                    item.build_item()
            with ui.HStack():
                ui.Spacer(width=4)
                ui.Label("Group Filters", name="PropertiesPaneSectionTitle")
            for item in self._delegate.items:
                if item.filter_type == "group":
                    item.build_item()


class AdditionalFiltersPopupMenuDelegate(PopupMenuDelegate):
    def __init__(self, filters: list[_StageManagerUSDFilterPlugin], on_filter_changed_fn=None):
        super().__init__()
        self.filters = filters
        self.items = []
        for result in filters:
            item = AdditionalFiltersPopupMenuItemDelegate(result[0], result[1], on_filter_changed_fn)
            self.items.append(item)

    def build_title(self, item: ui.MenuItem):
        super().build_title(item)
        self.enable_reset_all(True)

    def on_reset_all(self):
        """Reset all filter items to their default values."""
        for item in self.items:
            filter_obj = item.filter_obj

            # Reset all field values
            if isinstance(filter_obj, _ToggleableUSDFilterPlugin):
                filter_obj.filter_active = False
                item.filter_active = False

            for field_name, field_info in filter_obj.model_fields.items():
                if field_name in ["display_name", "tooltip", "enabled", "filter_active"]:
                    continue
                # Skip private or excluded fields
                if field_name.startswith("_") or field_info.exclude:
                    continue

                default_value = field_info.default
                # Handle default_factory if present
                if default_value is None and field_info.default_factory:
                    default_value = field_info.default_factory()

                setattr(filter_obj, field_name, default_value)

            # Rebuild UI with reset values
            item.build_item()
            filter_obj.refresh_filter_items()


class AdditionalFilterPlugin(_StageManagerUSDFilterPlugin):
    display_name: str = Field(default="Additional Filters", exclude=True)
    tooltip: str = Field(default="Additional filters to apply to the list of prims", exclude=True)

    _active_filters: list[tuple[_StageManagerUSDFilterPlugin, dict]] = PrivateAttr(default=[])
    _modified_filters: list[_StageManagerUSDFilterPlugin] = PrivateAttr(default=[])

    _icon: ui.Image | None = PrivateAttr(default=None)
    _counter_circle: ui.Circle | None = PrivateAttr(default=None)
    _counter_label: ui.Label | None = PrivateAttr(default=None)

    def filter_predicate(self, item: _StageManagerItem) -> bool:
        # This filter is not used, it is only here to satisfy the interface
        return True

    def _update_active_filters(self):
        """Sync the value dictionary with current filter states before reopening popup"""
        self._modified_filters = []

        for filter_obj, value in self._active_filters:
            if hasattr(filter_obj, "filter_active"):
                value["filter_active"] = filter_obj.filter_active

            # Check if filter has been modified from defaults
            if self._is_filter_modified(filter_obj):
                self._modified_filters.append(filter_obj)
            elif filter_obj in self._modified_filters:
                self._modified_filters.remove(filter_obj)

    def _is_filter_modified(self, filter_obj: _StageManagerUSDFilterPlugin) -> bool:
        """Check if the filter has been modified from its default values

        Args:
            filter_obj: The filter object to check.

        Returns:
            True if the filter has been modified from its default values, False otherwise.
        """
        is_modified = False
        for field_name, field_info in filter_obj.model_fields.items():
            if field_name in ["display_name", "tooltip", "enabled"]:
                continue
            # Skip private or excluded fields
            if field_name.startswith("_") or field_info.exclude:
                continue

            current_value = getattr(filter_obj, field_name, None)
            default_value = field_info.default

            # Handle default_factory if present
            if default_value is None and field_info.default_factory:
                default_value = field_info.default_factory()

            # Skip filter_active if it's False, since that is the default state
            if field_name == "filter_active" and current_value is False:
                continue

            if (field_name == "filter_active" and current_value is True) or (current_value != default_value):
                is_modified = True
                break

        return is_modified

    def _get_available_filters(self) -> list[_StageManagerUSDFilterPlugin]:
        """Get Additional registered filter plugins except self

        Returns:
            A list of additional filter plugins.
        """
        additional_filters = []
        self._modified_filters = []
        try:
            # Get the StageManagerCore instance to access resolved schema
            core = _get_stage_manager_core_instance()

            # Find the currently active interaction plugin
            active_interaction = core.get_active_interaction()

            if not active_interaction:
                return additional_filters

            active_filters = active_interaction.filters.copy()
            active_filters.extend(active_interaction.additional_filters)
            # Get additional filters from the active interaction plugin
            for filter_plugin in active_filters:
                if (
                    isinstance(filter_plugin, _StageManagerUSDFilterPlugin)
                    and filter_plugin.name not in EXCLUDE_FILTERS
                ):
                    # Get the filter's filter_active to correctly set checkbox state
                    value = {}
                    if isinstance(filter_plugin, _ToggleableUSDFilterPlugin):
                        value = {"filter_active": filter_plugin.filter_active}
                    if "Group" in filter_plugin.display_name:
                        value["filter_type"] = "group"
                    elif "Prims" in filter_plugin.display_name or filter_plugin.name.endswith("Systems"):
                        value["filter_type"] = "prims"
                    else:
                        value["filter_type"] = "other"
                    additional_filters.append([filter_plugin, value])
                elif not isinstance(filter_plugin, _StageManagerUSDFilterPlugin):
                    carb.log_error(
                        f"Filter plugin {filter_plugin.name} is not a valid filter plugin and will be ignored."
                    )
        except AttributeError as e:
            carb.log_error(f"Error getting active interaction plugin: {e}")

        return additional_filters

    def _on_filter_changed(self):
        """Callback when a filter is changed - updates the icon"""
        self._update_active_filters()
        if self._icon:
            self._icon.name = "FilterActive" if self._modified_filters else "Filter"
        if self._counter_circle is None or self._counter_label is None:
            return
        if self._modified_filters:
            self._counter_circle.visible = True
            self._counter_label.visible = True
            self._counter_label.text = str(len(self._modified_filters))
        else:
            self._counter_circle.visible = False
            self._counter_label.visible = False

    def _on_button_clicked(self):
        self._update_active_filters()
        menu = AdditionalFiltersPopupMenu("Additional Filters", self._active_filters, self._on_filter_changed)
        menu.show()

    def build_ui(self):
        # Gather available filters and update active filters
        if not self._active_filters:
            self._active_filters = self._get_available_filters()

        self._update_active_filters()

        # Clean up existing UI elements if they exist
        if self._icon:
            self._icon.destroy()
        if self._counter_circle:
            self._counter_circle.destroy()
        if self._counter_label:
            self._counter_label.destroy()

        with ui.HStack(height=0):
            with ui.ZStack(width=ui.Pixel(24), height=ui.Pixel(24)):
                self._icon = ui.Image(
                    "",
                    name="FilterActive" if self._modified_filters else "Filter",
                    tooltip="Additional Filters",
                    mouse_pressed_fn=lambda x, y, b, m: self._on_button_clicked(),
                    width=ui.Pixel(24),
                    height=ui.Pixel(24),
                )

                # A counter badge to show the number of modified filters.
                # It is hidden by default and shown when there are modified filters.
                count = len(self._modified_filters)
                with ui.VStack(padding=8):
                    with ui.HStack(padding=8):
                        with ui.ZStack(width=ui.Pixel(14), height=ui.Pixel(14)):
                            self._counter_circle = ui.Circle(radius=12, style={"background_color": 0xFF646464})
                            self._counter_circle.visible = bool(self._modified_filters)
                            self._counter_label = ui.Label(
                                str(count), alignment=ui.Alignment.CENTER, style={"font_size": 10, "color": 0xFFFFFFFF}
                            )
                            self._counter_label.visible = bool(self._modified_filters)
                        ui.Spacer()
                    ui.Spacer()
