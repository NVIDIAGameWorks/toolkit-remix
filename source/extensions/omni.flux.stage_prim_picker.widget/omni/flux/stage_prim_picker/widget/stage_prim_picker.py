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

from __future__ import annotations

__all__ = ("StagePrimPickerField",)

import asyncio
import typing
from typing import Callable

import carb.input
import omni.appwindow
import omni.kit.app
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.base import AbstractField
from omni.flux.utils.widget.hover import hover_helper
from omni.flux.utils.widget.tree_widget import AlternatingRowWidget
from pxr import Usd

from .prim_collection import PrimCollection
from .prim_list_delegate import PrimListDelegate
from .prim_list_model import PrimListModel

if typing.TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import ItemModelBase

# Layout constants
_SPACING_XS = 2
_SPACING_SM = 4
_SPACING_MD = 8
_SPACING_LG = 12
_ICON_SIZE_SM = 10
_ICON_SIZE_MD = 16
_ICON_CONTAINER_SIZE = 20
_ROW_HEIGHT = 24
_SEARCH_FIELD_HEIGHT = 20
_BUTTON_HEIGHT_SM = 20
_BUTTON_WIDTH_SM = 100
_LABEL_WIDTH_MD = 120
_BORDER_RADIUS = 4
_GREY_50 = 0xFF303030


class _SinglePrimPicker:
    """
    Single prim picker instance with dropdown, search, and pagination.

    Args:
        value_model: The value model to bind the selected prim path to.
        context_name: USD context name.
        prim_filter: Optional filter function for prims.
        prim_types: List of prim type names to filter by.
        path_patterns: List of glob patterns to filter prim paths.
        initial_items: Initial prims to load.
        page_size: Prims per "Show more" click.
        max_items: Maximum prims to load.
        style_name: UI style name.
        identifier: Widget identifier.
        element_idx: Index of this picker in multi-element fields.
        header_text: Optional header content - either a string or a callable that builds the header UI.
        header_tooltip: Optional tooltip shown on info icon on the right side of the header.
        row_build_fn: Optional custom row builder function. Signature:
                      (prim_path: str, prim_type: str, clicked_fn: Callable | None, row_height: int) -> None
    """

    DEBOUNCE_DELAY_SECONDS = 0.3
    DROPDOWN_WIDTH = 400
    DROPDOWN_HEIGHT = 200
    HEADER_HEIGHT = 0  # No header in TreeView
    ROW_HEIGHT = _ROW_HEIGHT

    def __init__(
        self,
        value_model: ItemModelBase,
        context_name: str,
        prim_filter: Callable[[Usd.Prim], bool] | None,
        prim_types: list[str] | None,
        path_patterns: list[str] | None,
        initial_items: int,
        page_size: int,
        max_items: int,
        style_name: str,
        identifier: str,
        element_idx: int,
        header_text: str | Callable[[], None] | None = None,
        header_tooltip: str | None = None,
        row_build_fn: Callable[[str, str, Callable | None, int], None] | None = None,
    ):
        self._value_model = value_model
        self._prim_collection = PrimCollection(
            context_name,
            prim_filter,
            prim_types,
            path_patterns,
            initial_items,
            page_size,
            max_items,
        )
        self._style_name = style_name
        self._identifier = identifier
        self._element_idx = element_idx
        self._header_text = header_text
        self._header_tooltip = header_tooltip
        self._row_build_fn = row_build_fn

        # UI elements (created in build_ui / _create_dropdown_window)
        self._dropdown_window: ui.Window | None = None
        self._dropdown_button_label: ui.StringField | None = None
        self._clear_button: ui.Image | None = None
        self._clear_container: ui.ZStack | None = None
        self._prim_model: PrimListModel | None = None
        self._prim_delegate: PrimListDelegate | None = None
        self._prim_tree: ui.TreeView | None = None
        self._tree_container: ui.Frame | None = None
        self._no_prims_container: ui.Frame | None = None
        self._alternating_row_widget: AlternatingRowWidget | None = None
        self._show_more_container: ui.VStack | None = None
        self._show_more_button: ui.Button | None = None
        self._search_model: ui.SimpleStringModel | None = None
        self._search_placeholder: ui.Label | None = None
        self._debounce_task: asyncio.Task | None = None
        self._has_more: bool = False

    def build_ui(self) -> ui.Widget:
        selected_value = self._value_model.get_value_as_string()

        with ui.Frame():
            with ui.ZStack(content_clipping=True):
                # Use read-only StringField
                self._dropdown_button_label = ui.StringField(
                    model=ui.SimpleStringModel(selected_value or "Select a prim..."),
                    read_only=True,
                    name="StagePrimPickerField",
                    identifier=f"{self._identifier}_button",
                    tooltip=selected_value if selected_value else "",
                )

                # Icons overlay layer
                with ui.HStack():
                    ui.Spacer()

                    with ui.Frame(width=ui.Pixel(60)):
                        with ui.ZStack():
                            # Gradient
                            ui.Image(
                                "",
                                name="FadeoutBG",
                                style={
                                    "color": _GREY_50,
                                    "border_radius": _BORDER_RADIUS,
                                    "margin": 1,
                                },
                                fill_policy=ui.FillPolicy.STRETCH,
                            )

                            # Icons
                            with ui.HStack():
                                ui.Spacer()

                                # Clear button
                                with ui.VStack(width=ui.Pixel(_ICON_CONTAINER_SIZE)):
                                    ui.Spacer()
                                    self._clear_container = ui.ZStack(
                                        width=ui.Pixel(_ICON_SIZE_MD),
                                        height=ui.Pixel(_ICON_SIZE_MD),
                                        visible=bool(selected_value),
                                    )
                                    with self._clear_container:
                                        ui.Rectangle(name="StagePrimPickerClearBackground")
                                        with ui.VStack():
                                            ui.Spacer(height=3)
                                            with ui.HStack():
                                                ui.Spacer(width=3)
                                                self._clear_button = ui.Image(
                                                    "",
                                                    width=_ICON_SIZE_SM,
                                                    height=_ICON_SIZE_SM,
                                                    name="StagePrimPickerClear",
                                                )
                                                ui.Spacer(width=3)
                                            ui.Spacer(height=3)
                                    ui.Spacer()

                                # Arrow button
                                with ui.VStack(width=ui.Pixel(_ICON_CONTAINER_SIZE)):
                                    ui.Spacer()
                                    with ui.ZStack(width=ui.Pixel(_ICON_SIZE_MD), height=ui.Pixel(_ICON_SIZE_MD)):
                                        ui.Rectangle(name="StagePrimPickerArrowBackground")
                                        with ui.VStack():
                                            ui.Spacer(height=3)
                                            with ui.HStack():
                                                ui.Spacer(width=3)
                                                ui.Image(
                                                    "",
                                                    width=_ICON_SIZE_SM,
                                                    height=_ICON_SIZE_SM,
                                                    name="AngledArrowDown",
                                                )
                                                ui.Spacer(width=3)
                                            ui.Spacer(height=3)
                                    ui.Spacer()

                                ui.Spacer(width=_SPACING_SM)

        # Make the StringField clickable to open dropdown
        self._dropdown_button_label.set_mouse_pressed_fn(lambda x, y, b, m: self._toggle_dropdown() if b == 0 else None)

        # Change cursor to pointer on hover
        hover_helper(self._dropdown_button_label)

        self._clear_button.set_mouse_released_fn(lambda x, y, b, m: self._clear_selection() if b == 0 else None)

        self._value_model.add_value_changed_fn(self._update_button_text)

        return self._dropdown_button_label

    def _update_button_text(self, model):
        value = model.get_value_as_string()

        if self._dropdown_button_label:
            self._dropdown_button_label.model.set_value(value or "Select a prim...")

            # Update tooltip with prim type and full path
            if value:
                prim_type = self._prim_collection.get_prim_type(value)
                tooltip = f"({prim_type}) {value}" if prim_type else value
                self._dropdown_button_label.tooltip = tooltip
            else:
                self._dropdown_button_label.tooltip = ""

        if self._clear_container:
            self._clear_container.visible = bool(value)

    def _clear_selection(self):
        self._value_model.set_value("")

    def _toggle_dropdown(self):
        if self._dropdown_window and self._dropdown_window.visible:
            self._dropdown_window.visible = False
            return

        self._prim_collection.reset_limit()
        self._create_dropdown_window()

    def _create_dropdown_window(self):
        window_id = f"StagePrimPickerDropdown_{self._identifier}_{self._element_idx}"

        self._dropdown_window = ui.Window(
            window_id,
            width=self.DROPDOWN_WIDTH,
            height=self.DROPDOWN_HEIGHT,
            flags=ui.WINDOW_FLAGS_NO_TITLE_BAR | ui.WINDOW_FLAGS_POPUP | ui.WINDOW_FLAGS_NO_RESIZE,
            name="StagePrimPickerDropdown",
            padding_x=0,
            padding_y=0,
            exclusive_keyboard=True,
        )
        self._dropdown_window.set_key_pressed_fn(self._on_key_pressed)

        # Position dropdown - open upwards if it would clip below screen bottom
        button_x = self._dropdown_button_label.screen_position_x
        button_y = self._dropdown_button_label.screen_position_y
        button_height = _ROW_HEIGHT

        app_window = omni.appwindow.get_default_app_window()
        dpi_scale = ui.Workspace.get_dpi_scale()
        app_height = app_window.get_size().y / dpi_scale

        dropdown_bottom = button_y + button_height + self.DROPDOWN_HEIGHT
        if dropdown_bottom > app_height:
            # Open upwards (above the button)
            self._dropdown_window.position_y = button_y - self.DROPDOWN_HEIGHT
        else:
            # Open downwards (below the button)
            self._dropdown_window.position_y = button_y + button_height

        self._dropdown_window.position_x = button_x

        self._search_model = ui.SimpleStringModel("")

        # Create model and delegate for TreeView
        self._prim_model = PrimListModel()
        self._prim_delegate = PrimListDelegate(self._select_prim, self._row_build_fn)

        with self._dropdown_window.frame:
            with ui.ZStack():
                # Background for entire dropdown content
                ui.Rectangle(name="StagePrimPickerDropdownBackground")

                with ui.VStack(spacing=0):
                    ui.Spacer(height=_SPACING_MD)
                    with ui.HStack(height=0):
                        ui.Spacer(width=_SPACING_MD)
                        ui.Label("Search:", width=_LABEL_WIDTH_MD)
                        with ui.ZStack(height=ui.Pixel(_SEARCH_FIELD_HEIGHT)):
                            ui.StringField(
                                model=self._search_model,
                                name="StagePrimPickerSearch",
                            )
                            self._search_placeholder = ui.Label(
                                "Filter available prims...",
                                name="StagePrimPickerSearchPlaceholder",
                                alignment=ui.Alignment.LEFT_CENTER,
                            )
                        if self._header_tooltip:
                            ui.Spacer(width=_SPACING_SM)
                            with ui.VStack(width=ui.Pixel(_ICON_SIZE_MD)):
                                ui.Spacer()
                                ui.Image(
                                    name="PropertiesPaneSectionInfo",
                                    width=ui.Pixel(_ICON_SIZE_MD),
                                    height=ui.Pixel(_ICON_SIZE_MD),
                                    tooltip=self._header_tooltip,
                                )
                                ui.Spacer()
                        ui.Spacer(width=_SPACING_MD)
                    ui.Spacer(height=_SPACING_MD)

                    # Header with optional text/build_fn (fully consumer-driven)
                    if self._header_text:
                        ui.Spacer(height=_SPACING_SM)
                        with ui.HStack(height=0):
                            ui.Spacer(width=_SPACING_MD)
                            if callable(self._header_text):
                                # Custom build function for header
                                self._header_text()
                            else:
                                # Simple string label
                                ui.Label(
                                    self._header_text,
                                    name="StagePrimPickerHeaderText",
                                    word_wrap=True,
                                    width=0,
                                )
                            ui.Spacer(width=_SPACING_MD)
                        ui.Spacer(height=_SPACING_MD)

                    # TreeView with AlternatingRowWidget background
                    with ui.ZStack(height=ui.Fraction(1)):
                        # Background alternating rows
                        self._alternating_row_widget = AlternatingRowWidget(
                            header_height=self.HEADER_HEIGHT,
                            row_height=self.ROW_HEIGHT,
                            scrollbar_spacing=True,
                        )

                        # Foreground TreeView in ScrollingFrame
                        self._tree_container = ui.Frame(visible=True)
                        with self._tree_container:
                            tree_scroll_frame = ui.ScrollingFrame(
                                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                                scroll_y_changed_fn=self._alternating_row_widget.sync_scrolling_frame,
                            )
                            with tree_scroll_frame:
                                # ZStack with content_clipping ensures horizontal content is clipped properly
                                with ui.ZStack(
                                    content_clipping=True,
                                    computed_content_size_changed_fn=self._on_content_size_changed,
                                ):
                                    self._prim_tree = ui.TreeView(
                                        self._prim_model,
                                        delegate=self._prim_delegate,
                                        root_visible=False,
                                        header_visible=False,
                                    )

                        # "No prims found" message
                        self._no_prims_container = ui.Frame(visible=False)
                        with self._no_prims_container:
                            with ui.VStack():
                                ui.Spacer(height=_SPACING_LG)
                                ui.Label("No prims found", alignment=ui.Alignment.CENTER)
                                ui.Spacer()

                    # "Show more" button - fixed at bottom, hidden when no more items
                    self._show_more_container = ui.VStack(
                        height=0, visible=False, name="StagePrimPickerShowMoreContainer"
                    )
                    with self._show_more_container:
                        ui.Spacer(height=_SPACING_SM)
                        with ui.HStack(height=0):
                            ui.Spacer()
                            self._show_more_button = ui.Button(
                                "Show more...",
                                height=ui.Pixel(_BUTTON_HEIGHT_SM),
                                width=ui.Pixel(_BUTTON_WIDTH_SM),
                                name="StagePrimPickerFieldShowMore",
                                clicked_fn=self._load_more_prims,
                                alignment=ui.Alignment.CENTER,
                            )
                            ui.Spacer()
                        ui.Spacer(height=_SPACING_SM)

        self._search_model.add_value_changed_fn(self._handle_search_input)
        self._populate_prim_list("")

    def _on_key_pressed(self, key: int, modifiers: int, is_down: bool):
        """Handle key press events. Close dropdown on Escape."""
        if key == int(carb.input.KeyboardInput.ESCAPE) and is_down:
            self._dropdown_window.visible = False

    def _on_content_size_changed(self):
        """Sync alternating row widget with TreeView content size."""
        if self._alternating_row_widget and self._prim_tree:
            self._alternating_row_widget.sync_frame_height(self._prim_tree.computed_height)

    def _handle_search_input(self, model: ui.SimpleStringModel):
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        search_text = model.get_value_as_string()

        # Show/hide placeholder based on whether there's text
        if self._search_placeholder:
            self._search_placeholder.visible = not search_text

        async def execute_search_after_delay():
            await asyncio.sleep(self.DEBOUNCE_DELAY_SECONDS)

            self._prim_collection.reset_limit()

            if self._dropdown_window and self._dropdown_window.visible:
                self._populate_prim_list(search_text)

        self._debounce_task = asyncio.ensure_future(execute_search_after_delay())

    def _populate_prim_list(self, search_text: str):
        prim_items, self._has_more = self._prim_collection.get_prim_paths(search_text)

        # Update model with new items
        self._prim_model.set_items(prim_items)

        has_items = len(prim_items) > 0

        # Toggle tree/empty message visibility
        if self._tree_container:
            self._tree_container.visible = has_items
        if self._no_prims_container:
            self._no_prims_container.visible = not has_items

        # Refresh alternating row widget
        if self._alternating_row_widget:
            self._alternating_row_widget.refresh(self._prim_model.item_count)

        # Show/hide "Show more" button based on whether there are more items
        if self._show_more_container:
            self._show_more_container.visible = self._has_more

    def _load_more_prims(self):
        async def load_more_async():
            await omni.kit.app.get_app().next_update_async()
            self._prim_collection.load_more()
            search_text = self._search_model.get_value_as_string() if self._search_model else ""
            self._populate_prim_list(search_text)

        asyncio.ensure_future(load_more_async())

    def _select_prim(self, prim_path: str):
        self._value_model.set_value(prim_path)
        if self._dropdown_window:
            self._dropdown_window.visible = False

    def destroy(self):
        """Clean up all resources."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        if self._dropdown_window:
            self._dropdown_window.visible = False
            self._dropdown_window.destroy()

        if self._prim_model:
            self._prim_model.destroy()

        if self._prim_delegate:
            self._prim_delegate.destroy()

        if self._alternating_row_widget:
            self._alternating_row_widget.destroy()

        self._dropdown_window = None
        self._dropdown_button_label = None
        self._clear_button = None
        self._clear_container = None
        self._prim_model = None
        self._prim_delegate = None
        self._prim_tree = None
        self._tree_container = None
        self._no_prims_container = None
        self._alternating_row_widget = None
        self._show_more_container = None
        self._show_more_button = None
        self._search_model = None
        self._search_placeholder = None
        self._debounce_task = None


# ============================================================================
# Public Field Class
# ============================================================================


class StagePrimPickerField(AbstractField):
    """
    Searchable dropdown field for picking USD stage prims with debounced search and pagination.

    Uses TreeView with AlternatingRowWidget for consistent styling with Stage Manager.

    Args:
        context_name: USD context name. Empty string uses default context.
        prim_filter: Optional custom filter function. Return True for prims to include.
        prim_types: Optional list of prim type names to include (e.g., ["Mesh", "Xform"]).
        path_patterns: Optional list of glob patterns (e.g., ["/World/Geometry/*", "**/Light*"]).
                      Patterns are OR'd. Optimizes stage traversal by skipping non-matching subtrees.
        initial_items: Initial prims to load (default: 20).
        page_size: Prims to load per "Show more" click (default: 20).
        max_items: Maximum prims to load (default: 10000).
        identifier: Optional widget identifier.
        header_text: Optional header content - either a string or a callable that builds the header UI.
        header_tooltip: Optional tooltip shown on info icon on right of header.
        row_build_fn: Optional custom row builder function. Signature:
                      (prim_path: str, prim_type: str, clicked_fn: Callable | None, row_height: int) -> None
                      If not provided, a default row layout is used.
    """

    def __init__(
        self,
        context_name: str = "",
        prim_filter: Callable[[Usd.Prim], bool] | None = None,
        prim_types: list[str] | None = None,
        path_patterns: list[str] | None = None,
        initial_items: int = 20,
        page_size: int = 20,
        max_items: int = 10000,
        identifier: str | None = None,
        header_text: str | Callable[[], None] | None = None,
        header_tooltip: str | None = None,
        row_build_fn: Callable[[str, str, Callable | None, int], None] | None = None,
    ):
        super().__init__(style_name="StagePrimPickerField", identifier=identifier)
        self._context_name = context_name
        self._prim_filter = prim_filter
        self._prim_types = prim_types
        self._path_patterns = path_patterns
        self._initial_items = initial_items
        self._page_size = page_size
        self._max_items = max_items
        self._header_text = header_text
        self._header_tooltip = header_tooltip
        self._row_build_fn = row_build_fn
        self._pickers = []

    def build_ui(self, item) -> list[ui.Widget]:
        widgets = []

        with ui.HStack(height=ui.Pixel(_ROW_HEIGHT)):
            for i in range(item.element_count):
                ui.Spacer(width=ui.Pixel(_SPACING_MD))

                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(_SPACING_XS))

                    picker = _SinglePrimPicker(
                        value_model=item.value_models[i],
                        context_name=self._context_name,
                        prim_filter=self._prim_filter,
                        prim_types=self._prim_types,
                        path_patterns=self._path_patterns,
                        initial_items=self._initial_items,
                        page_size=self._page_size,
                        max_items=self._max_items,
                        style_name=self.style_name,
                        identifier=self.identifier or "prim_picker",
                        element_idx=i,
                        header_text=self._header_text,
                        header_tooltip=self._header_tooltip,
                        row_build_fn=self._row_build_fn,
                    )

                    widget = picker.build_ui()
                    self._pickers.append(picker)
                    widgets.append(widget)

                    ui.Spacer(height=ui.Pixel(_SPACING_XS))

        return widgets

    def destroy(self):
        for picker in self._pickers:
            if picker:
                picker.destroy()

        self._pickers = []
