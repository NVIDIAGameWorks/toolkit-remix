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

import omni.ui as ui
from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase


class Delegate(_TreeDelegateBase):
    """Render scan results and coordinate their checkbox selection state."""

    _WIDGET_PADDING = 8
    _ROW_HEIGHT = 24
    _LABEL_HEIGHT = 16
    _CHECKBOX_WIDTH = 24
    _ROW_PADDING = 4

    def __init__(self):
        """Initialize result widgets and selection state."""
        super().__init__()
        self._context_menu = None
        self._checkboxes = {}
        self.scroll_frames = {}
        self.selection_button = None
        self._clicked_checkbox_item = None

    def refresh(self):
        """Discard widget references and selection state from the previous result view."""
        self._context_menu = None
        self._checkboxes = {}
        self.scroll_frames = {}
        self._clicked_checkbox_item = None

    def build_branch(self, model, item, column_id, level, expanded):
        """Leave branch rendering empty because scan results are flat.

        Args:
            model: Tree model requesting the branch widget.
            item: Tree item associated with the branch.
            column_id: Column requesting the branch widget.
            level: Tree depth of the item.
            expanded: Whether the branch is expanded.
        """
        pass

    def _set_value(self, item, model):
        """Apply a clicked checkbox value to the selected result rows.

        Args:
            item: Result item whose checkbox changed.
            model: Result model that owns the selected rows.
        """
        # To avoid a loop, we don't want to run this for every selection when we're setting value via multi-select.
        # So, only run this value once via the user-selected checkbox.
        if self._clicked_checkbox_item is not item:
            return

        if item.value:
            item.value = False
        else:
            item.value = True

        # Apply the clicked value to every selected row, then derive the button state
        # from the complete model rather than only the rows changed here.
        children = model.get_item_children(None)
        change_value = item.value

        if self._clicked_checkbox_item.selected:
            for child in children:
                if not child.selected or child == item:
                    continue
                child.value = change_value
                self._checkboxes[child.path.name].model.set_value(change_value)

        self.selection_button.enabled = any(child.value for child in children)

    def _change_selection(self, val, model):
        """Set the checked state for every selected result row.

        Args:
            val: Checked state to assign to selected rows.
            model: Result model that owns the selected rows.
        """
        children = model.get_item_children(None)
        for child in children:
            if child.selected:
                child.value = val
                self._checkboxes[str(child.path.name)].model.set_value(val)
        self.selection_button.enabled = any(child.value for child in children)

    def _on_checkbox_clicked(self, item, checkbox):
        """Record the result item associated with the clicked checkbox.

        Args:
            item: Result item associated with the checkbox.
            checkbox: Checkbox that emitted the mouse event.
        """
        self._clicked_checkbox_item = item

    def _show_context_menu(self, button, model):
        """Show bulk check actions after a right-click.

        Args:
            button: Mouse button code that requested the menu.
            model: Result model updated by the menu actions.
        """
        if button != 1:
            return
        if self._context_menu is not None:
            self._context_menu = None
        self._context_menu = ui.Menu("Context Menu")

        with self._context_menu:
            ui.MenuItem(
                "Check selected paths",
                identifier="check_paths",
                triggered_fn=lambda: self._change_selection(True, model),
            )
            ui.MenuItem(
                "Uncheck selected paths",
                identifier="uncheck_paths",
                triggered_fn=lambda: self._change_selection(False, model),
            )
        self._context_menu.show()

    def build_widget(self, model, item, column_id, level, expanded):
        """Build a checkbox and scrollable path label for one result.

        Args:
            model: Tree model that owns the result item.
            item: Result item to render, or None for an empty row.
            column_id: Column requesting a widget.
            level: Tree depth of the result item.
            expanded: Whether the result item is expanded.
        """
        if item is None:
            return
        if column_id == 0:
            with ui.ZStack():
                with ui.HStack(
                    mouse_pressed_fn=lambda x, y, b, m: self._show_context_menu(b, model),
                    height=ui.Pixel(self._LABEL_HEIGHT),
                ):
                    ui.Spacer(width=ui.Pixel(self._ROW_PADDING))
                    with ui.VStack(width=ui.Pixel(self._CHECKBOX_WIDTH)):
                        ui.Spacer(height=ui.Pixel(self._ROW_PADDING))
                        checkbox = ui.CheckBox(
                            width=ui.Pixel(self._CHECKBOX_WIDTH),
                            mouse_pressed_fn=lambda x, y, b, m: self._on_checkbox_clicked(item, checkbox),
                        )

                        checkbox.name = item.path.name
                        checkbox.model.set_value(item.value)
                        checkbox.model.add_value_changed_fn(
                            lambda value_model, item=item, model=model: self._set_value(item, model)
                        )

                        self._checkboxes[checkbox.name] = checkbox

                    with ui.Frame(
                        height=0,
                        separate_window=True,
                        tooltip=str(item.path),
                        identifier="found_item",
                    ):
                        with ui.ZStack():
                            self.scroll_frames[id(item)] = ui.ScrollingFrame(
                                height=ui.Pixel(self._ROW_HEIGHT),
                                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                scroll_y_max=0,
                            )

                            with self.scroll_frames[id(item)]:
                                with ui.HStack():
                                    ui.Label(str(item.path))
