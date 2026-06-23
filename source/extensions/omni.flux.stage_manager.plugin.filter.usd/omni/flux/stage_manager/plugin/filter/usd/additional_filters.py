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
import omni.appwindow
from omni import ui
from omni.flux.stage_manager.core import get_instance as _get_stage_manager_core_instance
from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.stage_manager.factory.plugins.filter_plugin import FilterCategory as _FilterCategory
from omni.kit.widget.options_menu.popup_menu import AbstractPopupMenu, PopupMenuDelegate, PopupMenuItemDelegate
from pydantic import Field, PrivateAttr

from .base import CheckboxGroupFilterPlugin as _CheckboxGroupFilterPlugin
from .base import StageManagerUSDFilterPlugin as _StageManagerUSDFilterPlugin
from .base import ToggleableUSDFilterPlugin as _ToggleableUSDFilterPlugin

EXCLUDE_FILTERS = ["AdditionalFilterPlugin", "SearchFilterPlugin"]
_FILTER_CATEGORY_SPACING = 8
_FILTER_CATEGORY_PADDING = 4
_FILTER_CATEGORY_HEADER_TOP_SPACING = 8
_FILTER_CATEGORY_ACTION_TRAILING_PADDING = 12
_FILTER_POPUP_EDGE_MARGIN = 8
_FILTER_POPUP_NON_BODY_HEIGHT = 28
_FILTER_POPUP_MAX_BODY_HEIGHT = 500
_FILTER_POPUP_WIDTH = 340

# Section titles for each FilterCategory in the additional filters popup
_FILTER_CATEGORY_TITLES = {
    _FilterCategory.OTHER: "Multi-Option Filters",
    _FilterCategory.PRIMS: "Prim Filters",
    _FilterCategory.GROUP: "Group Filters",
    _FilterCategory.TAGS: "Custom Tags Filter",
}


def _clamp_filter_popup_x(anchor_x: float, app_width: float) -> float:
    """Clamp the filter popup's X position inside the app window."""
    max_x = max(_FILTER_POPUP_EDGE_MARGIN, app_width - _FILTER_POPUP_WIDTH - _FILTER_POPUP_EDGE_MARGIN)
    return max(_FILTER_POPUP_EDGE_MARGIN, min(anchor_x, max_x))


def _get_app_window_width_points() -> float:
    """Return the app window width in UI points."""
    app_window = omni.appwindow.get_default_app_window()
    if not app_window:
        return 0
    return app_window.get_size()[0] / ui.Workspace.get_dpi_scale()


def _get_app_window_height_points() -> float:
    """Return the app window height in UI points."""
    app_window = omni.appwindow.get_default_app_window()
    if not app_window:
        return 0
    return app_window.get_size()[1] / ui.Workspace.get_dpi_scale()


def _get_filter_popup_body_height(anchor_y: float | None = None) -> float:
    """Return the maximum popup body height allowed by the app window."""
    if anchor_y is None:
        return _FILTER_POPUP_MAX_BODY_HEIGHT

    app_height = _get_app_window_height_points()
    if not app_height:
        return _FILTER_POPUP_MAX_BODY_HEIGHT

    available_height = app_height - anchor_y - _FILTER_POPUP_EDGE_MARGIN - _FILTER_POPUP_NON_BODY_HEIGHT
    return max(1, min(_FILTER_POPUP_MAX_BODY_HEIGHT, available_height))


class AdditionalFiltersPopupMenuItemDelegate(PopupMenuItemDelegate):
    def __init__(self, filter_obj: _StageManagerUSDFilterPlugin, value: dict, on_filter_changed_fn=None):
        super().__init__()
        self.filter_obj = filter_obj
        self.text = filter_obj.display_name
        self.filter_active = value.get("filter_active", False)
        self.filter_category = getattr(filter_obj, "filter_category", _FilterCategory.OTHER)
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
            self._container = ui.HStack(spacing=ui.Pixel(8))
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
            with ui.VStack(spacing=ui.Pixel(4)):
                self.filter_obj.build_ui()
                if not isinstance(self.filter_obj, _ToggleableUSDFilterPlugin):
                    ui.Spacer(width=0)
            ui.Spacer(width=0)

    def destroy(self):
        super().destroy()
        self._filter_changed_sub = None


class AdditionalFiltersPopupMenu(AbstractPopupMenu):
    def __init__(
        self,
        title,
        filters: list[_StageManagerUSDFilterPlugin],
        on_filter_changed_fn=None,
        body_height: float | None = None,
    ):
        self._on_filter_changed_fn = on_filter_changed_fn
        self._category_header_frames = {}
        self._body_height = body_height or _FILTER_POPUP_MAX_BODY_HEIGHT
        self._delegate = AdditionalFiltersPopupMenuDelegate(filters, self._on_filter_changed)
        self._scrolling_frame = None
        self._body_stack = None
        super().__init__(title, self._delegate)
        self.filters = filters

    def build_menu_items(self):
        self._category_header_frames.clear()
        self._body_stack = None
        self._scrolling_frame = ui.ScrollingFrame(
            width=ui.Pixel(_FILTER_POPUP_WIDTH),
            height=ui.Pixel(self._body_height),
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            computed_content_size_changed_fn=self._update_body_height,
        )
        with self._scrolling_frame:
            self._build_menu_body()

    def _update_body_height(self):
        if not self._scrolling_frame:
            return

        if self._scrolling_frame.scroll_y_max:
            self._scrolling_frame.height = ui.Pixel(self._body_height)
            return

        content_height = (
            self._body_stack.computed_height if self._body_stack else self._scrolling_frame.computed_content_height
        )
        if content_height:
            self._scrolling_frame.height = ui.Pixel(max(1, min(self._body_height, content_height)))

    def _build_menu_body(self):
        categories = [category for category in _FilterCategory if self._delegate.items[category]]
        last_category = categories[-1] if categories else None

        with ui.HStack(width=ui.Pixel(_FILTER_POPUP_WIDTH), height=0, spacing=ui.Pixel(_FILTER_CATEGORY_SPACING)):
            ui.Spacer(width=0)
            self._body_stack = ui.VStack(height=0)
            with self._body_stack:
                for category in categories:
                    items = self._delegate.items[category]
                    ui.Spacer(height=ui.Pixel(_FILTER_CATEGORY_HEADER_TOP_SPACING))
                    self._category_header_frames[category] = ui.Frame(
                        height=0, build_fn=lambda c=category: self._build_category_header(c)
                    )
                    ui.Spacer(height=ui.Pixel(8))
                    for item in items:
                        item.build_item()
                        if category != _FilterCategory.OTHER:
                            ui.Spacer(height=ui.Pixel(4))
                    bottom_spacing = _FILTER_CATEGORY_HEADER_TOP_SPACING if category == last_category else 4
                    ui.Spacer(height=ui.Pixel(bottom_spacing))

    def _build_category_header(self, category: _FilterCategory):
        with ui.HStack(height=0, spacing=ui.Pixel(_FILTER_CATEGORY_SPACING)):
            ui.Spacer(width=ui.Pixel(_FILTER_CATEGORY_PADDING))
            ui.Label(_FILTER_CATEGORY_TITLES[category], name="PropertiesPaneSectionTitle", width=0)
            if not self._delegate.has_bulk_actions(category):
                return
            ui.Spacer()
            self._build_category_action("Select All", category, True)
            ui.Spacer(width=ui.Pixel(_FILTER_CATEGORY_SPACING))
            self._build_category_action("Deselect All", category, False)
            ui.Spacer(width=ui.Pixel(_FILTER_CATEGORY_ACTION_TRAILING_PADDING))

    def _build_category_action(self, text: str, category: _FilterCategory, selected: bool):
        enabled = self._delegate.can_set_all_selected(category, selected)
        ui.Label(
            text,
            width=0,
            name="FilterSectionAction",
            identifier=f"additional_filters_{category.value.lower()}_{'select' if selected else 'deselect'}_all",
            enabled=enabled,
            mouse_pressed_fn=lambda *_, c=category, s=selected: self._set_all_selected(c, s),
        )

    def _set_all_selected(self, category: _FilterCategory, selected: bool):
        if not self._delegate.can_set_all_selected(category, selected):
            return
        if not self._delegate.set_all_selected(category, selected):
            return
        self._rebuild_category_headers()

    def _on_filter_changed(self):
        self._rebuild_category_headers()
        if self._on_filter_changed_fn:
            self._on_filter_changed_fn()

    def _rebuild_category_headers(self):
        for frame in self._category_header_frames.values():
            frame.rebuild()

    def destroy(self):
        self._category_header_frames.clear()
        self._body_stack = None
        super().destroy()


class AdditionalFiltersPopupMenuDelegate(PopupMenuDelegate):
    def __init__(self, filters: list[_StageManagerUSDFilterPlugin], on_filter_changed_fn=None):
        super().__init__()
        self.filters = filters
        self._on_filter_changed_fn = on_filter_changed_fn
        self.items = {category: [] for category in _FilterCategory}
        for result in filters:
            filter_obj, value = result[0], result[1]
            item = AdditionalFiltersPopupMenuItemDelegate(filter_obj, value, on_filter_changed_fn)
            category = getattr(filter_obj, "filter_category", _FilterCategory.OTHER)
            self.items[category].append(item)

    def build_title(self, item: ui.MenuItem):
        super().build_title(item)
        self.enable_reset_all(True)

    def has_bulk_actions(self, category: _FilterCategory) -> bool:
        return any(self._supports_bulk_actions(item) for item in self.items[category])

    def can_set_all_selected(self, category: _FilterCategory, selected: bool) -> bool:
        return any(self._can_set_item_selected(item, selected) for item in self.items[category])

    def set_all_selected(self, category: _FilterCategory, selected: bool) -> bool:
        changed = False
        for item in self.items[category]:
            if not self._can_set_item_selected(item, selected):
                continue
            self._set_item_selected(item, selected)
            changed = True
        return changed

    def _supports_bulk_actions(self, item: AdditionalFiltersPopupMenuItemDelegate) -> bool:
        return item.filter_category.is_or and isinstance(
            item.filter_obj, (_CheckboxGroupFilterPlugin, _ToggleableUSDFilterPlugin)
        )

    def _can_set_item_selected(self, item: AdditionalFiltersPopupMenuItemDelegate, selected: bool) -> bool:
        if not self._supports_bulk_actions(item):
            return False
        filter_obj = item.filter_obj
        if isinstance(filter_obj, _ToggleableUSDFilterPlugin):
            return filter_obj.filter_active != selected
        if isinstance(filter_obj, _CheckboxGroupFilterPlugin):
            return filter_obj.can_set_all_selected(selected)
        return False

    def _set_item_selected(self, item: AdditionalFiltersPopupMenuItemDelegate, selected: bool):
        filter_obj = item.filter_obj
        if isinstance(filter_obj, _ToggleableUSDFilterPlugin):
            item.filter_active = selected
            filter_obj.filter_active = selected
            item.build_item()
            filter_obj.refresh_filter_items()
        elif isinstance(filter_obj, _CheckboxGroupFilterPlugin):
            filter_obj.set_all_selected(selected)

    def on_reset_all(self):
        """Reset all filter items to their default values."""
        for category_items in self.items.values():
            for item in category_items:
                filter_obj = item.filter_obj

                # Reset toggle state
                if isinstance(filter_obj, _ToggleableUSDFilterPlugin):
                    filter_obj.filter_active = False
                    item.filter_active = False

                # Reset all field values and rebuild this item's UI
                for field_name, field_info in filter_obj.model_fields.items():
                    if field_name in {"display", "display_name", "tooltip", "enabled", "filter_active"}:
                        continue
                    # Skip private or excluded fields
                    if field_name.startswith("_") or field_info.exclude:
                        continue

                    default_value = field_info.default
                    # Handle default_factory if present
                    if default_value is None and field_info.default_factory:
                        default_value = field_info.default_factory()
                    elif isinstance(default_value, list):
                        # Copy to avoid mutating field_info.default in place (e.g. selected_tags uses default=[] so
                        # field_info.default is a shared object across all instances)
                        default_value = list(default_value)

                    setattr(filter_obj, field_name, default_value)

                # Rebuild item UI with reset values and refresh filter
                item.build_item()
                filter_obj.refresh_filter_items()

        if self._on_filter_changed_fn:
            self._on_filter_changed_fn()


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

    def _refresh_filter_active(self) -> None:
        self.filter_active = False

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
            if field_name in {"display", "display_name", "tooltip", "enabled"}:
                continue
            # Skip private fields
            if field_name.startswith("_"):
                continue

            current_value = getattr(filter_obj, field_name, None)
            default_value = field_info.default

            # Handle default_factory if present
            if default_value is None and field_info.default_factory:
                default_value = field_info.default_factory()

            if field_name == "filter_active":
                if current_value is True and (
                    isinstance(filter_obj, _ToggleableUSDFilterPlugin) or default_value is False
                ):
                    is_modified = True
                    break
                continue

            # Skip excluded fields after handling filter_active, which Additional Filters uses as runtime state.
            if field_info.exclude:
                continue

            if current_value != default_value:
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
            seen_names: set[str] = set()
            # Get additional filters from the active interaction plugin
            for filter_plugin in active_filters:
                if (
                    isinstance(filter_plugin, _StageManagerUSDFilterPlugin)
                    and filter_plugin.name not in EXCLUDE_FILTERS
                    and filter_plugin.name not in seen_names
                ):
                    # Get the filter's filter_active to correctly set checkbox state
                    value = {}
                    if isinstance(filter_plugin, _ToggleableUSDFilterPlugin):
                        value = {"filter_active": filter_plugin.filter_active}
                    additional_filters.append([filter_plugin, value])
                    seen_names.add(filter_plugin.name)
                elif not isinstance(filter_plugin, _StageManagerUSDFilterPlugin):
                    carb.log_error(
                        f"Filter plugin {filter_plugin.name} is not a valid filter plugin and will be ignored."
                    )
        except AttributeError as e:
            carb.log_error(f"Error getting active interaction plugin: {e}")

        # Sort by FilterCategory (OTHER, PRIMS, GROUP) then by display_name
        category_order = {c: i for i, c in enumerate(_FilterCategory)}
        additional_filters.sort(
            key=lambda x: (
                category_order.get(
                    getattr(x[0], "filter_category", _FilterCategory.OTHER),
                    len(category_order),
                ),
                x[0].display_name,
            )
        )
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
        if self._icon is None:
            menu = AdditionalFiltersPopupMenu(
                "Additional Filters",
                self._active_filters,
                self._on_filter_changed,
                body_height=_get_filter_popup_body_height(),
            )
            menu.show()
            return

        app_width = _get_app_window_width_points()
        popup_x = (
            _clamp_filter_popup_x(self._icon.screen_position_x, app_width)
            if app_width
            else self._icon.screen_position_x
        )
        popup_y = self._icon.screen_position_y + self._icon.computed_height
        menu = AdditionalFiltersPopupMenu(
            "Additional Filters",
            self._active_filters,
            self._on_filter_changed,
            body_height=_get_filter_popup_body_height(popup_y),
        )
        menu.show_at(popup_x, popup_y)

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
