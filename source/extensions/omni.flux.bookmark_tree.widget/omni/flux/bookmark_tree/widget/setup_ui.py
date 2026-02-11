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

import asyncio
import functools
from typing import Any

import carb
import omni.kit.undo
from omni import kit, ui, usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.dialog import show_popup as _show_popup
from omni.flux.utils.widget.hover import hover_helper as _hover_helper

from .bookmark_tree.delegate import BookmarkDelegate
from .bookmark_tree.item_model import BookmarkCollectionItem, ComponentTypes, ItemBase, TemporaryBookmarkModel
from .bookmark_tree.model import BookmarkCollectionModel


class BookmarkTreeWidget:
    _DEFAULT_TREE_FRAME_HEIGHT = 100
    _SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(self, model: BookmarkCollectionModel | None = None, delegate: BookmarkDelegate | None = None):
        self._default_attr = {
            "_tree_expanded": None,
            "_tree_selection": None,
            "_model": None,
            "_delegate": None,
            "_manipulator_frame": None,
            "_tree_scroll_frame": None,
            "_manip_frame": None,
            "_slide_placer": None,
            "_slider_manip": None,
            "_bookmark_tree_widget": None,
            "_sub_on_item_changed": None,
            "_sub_on_active_items_changed": None,
            "_sub_on_bookmark_collection_double_clicked": None,
            "_sub_on_create_item_clicked": None,
            "_sub_on_item_expanded": None,
            "_sub_on_add_item_clicked": None,
            "_sub_on_remove_item_clicked": None,
            "_sub_on_delete_item_clicked": None,
            "_sub_popup_value_changed": None,
            "_is_editing": None,
            "_refresh_task": None,
            "_popup_window": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._tree_expanded = {}
        self._tree_selection = []
        self._tree_selection_secondary = []

        self._is_editing = False
        self._refresh_task = None

        self._model = BookmarkCollectionModel() if model is None else model
        self._delegate = BookmarkDelegate() if delegate is None else delegate

        # Model events
        self._sub_on_item_changed = self._model.subscribe_item_changed_fn(self._on_item_changed)
        self._sub_on_active_items_changed = self._model.subscribe_on_active_items_changed(self._on_active_items_changed)
        self._sub_on_create_item_clicked = self._model.subscribe_on_create_item_clicked(self._on_create_item_clicked)
        self._sub_on_bookmark_collection_double_clicked = self._model.subscribe_on_bookmark_collection_double_clicked(
            self._on_bookmark_collection_double_clicked
        )
        # Delegate events
        self._sub_on_item_expanded = self._delegate.subscribe_on_item_expanded(self._on_item_expanded)
        self._sub_on_add_item_clicked = self._delegate.subscribe_on_add_clicked(self._on_add_item_clicked)
        self._sub_on_remove_item_clicked = self._delegate.subscribe_on_remove_clicked(self._on_remove_item_clicked)
        self._sub_on_delete_item_clicked = self._delegate.subscribe_on_delete_clicked(self._on_delete_item_clicked)

        self.__create_ui()

    def show(self, value: bool):
        """
        Let the widget know if it's visible or not. This will internally enable/disabled the USD listener to reduce the
        amount of resources used by the widget with it's not visible.
        """
        self._model.enable_listeners(value)
        if value:
            for item in self._tree_selection + self._tree_selection_secondary:
                self._delegate.refresh_gradient_color(item)

    def __create_ui(self):
        with ui.VStack():
            self._manipulator_frame = ui.Frame(visible=True)
            with self._manipulator_frame:
                size_manipulator_height = 4
                with ui.ZStack():
                    with ui.VStack():
                        self._tree_scroll_frame = ui.ScrollingFrame(
                            name="PropertiesPaneSection",
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            height=ui.Pixel(self._DEFAULT_TREE_FRAME_HEIGHT),
                        )
                        with self._tree_scroll_frame:
                            self._bookmark_tree_widget = ui.TreeView(
                                self._model,
                                delegate=self._delegate,
                                header_visible=False,
                                drop_between_items=True,
                                columns_resizable=False,
                                style_type_name_override="TreeView.Selection",
                                key_pressed_fn=self._on_delete_pressed,
                            )
                            self._bookmark_tree_widget.set_selection_changed_fn(self._on_selection_changed)
                        self._tree_scroll_frame.set_build_fn(
                            functools.partial(
                                self._resize_tree_columns,
                                self._bookmark_tree_widget,
                                self._tree_scroll_frame,
                            )
                        )
                        self._tree_scroll_frame.set_computed_content_size_changed_fn(
                            functools.partial(
                                self._resize_tree_columns,
                                self._bookmark_tree_widget,
                                self._tree_scroll_frame,
                            )
                        )
                        ui.Spacer(height=ui.Pixel(6))
                        ui.Line(name="PropertiesPaneSectionTitle")
                        ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(height=size_manipulator_height)

                    with ui.VStack():
                        ui.Spacer()
                        self._manip_frame = ui.Frame(height=size_manipulator_height)
                        with self._manip_frame:
                            self._slide_placer = ui.Placer(
                                draggable=True,
                                height=size_manipulator_height,
                                offset_x_changed_fn=self._on_slide_x_changed,
                                offset_y_changed_fn=functools.partial(
                                    self._on_slide_y_changed,
                                    size_manipulator_height,
                                ),
                            )
                            # Body
                            with self._slide_placer:
                                self._slider_manip = ui.Rectangle(
                                    width=ui.Percent(self._SIZE_PERCENT_MANIPULATOR_WIDTH),
                                    name="PropertiesPaneSectionTreeManipulator",
                                )
                                _hover_helper(self._slider_manip)

    def _resize_tree_columns(self, tree_view, frame):
        tree_view.column_widths = [ui.Pixel(self._tree_scroll_frame.computed_width - 12)]

    def _on_slide_x_changed(self, x):
        size_manip = self._manip_frame.computed_width / 100 * self._SIZE_PERCENT_MANIPULATOR_WIDTH
        if x.value < 0:
            self._slide_placer.offset_x = 0
        elif x.value > self._manip_frame.computed_width - size_manip:
            self._slide_placer.offset_x = self._manip_frame.computed_width - size_manip

        item_path_scroll_frames = self._delegate.get_scroll_frames()
        if item_path_scroll_frames:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / (self._manip_frame.computed_width - size_manip)) * x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value

    def _on_slide_y_changed(self, size_manip, y):
        if y.value < 0:
            self._slide_placer.offset_y = 0
        self._tree_scroll_frame.height = ui.Pixel(self._DEFAULT_TREE_FRAME_HEIGHT + y.value)

    def __set_root_item_expansion(self, item: ItemBase, value: bool):
        if not item:
            return
        while item.parent is not None:
            self._tree_expanded[item.title] = True
            item = item.parent
        self._bookmark_tree_widget.set_expanded(item, value, True)

    def __show_temp_item_popup(self, is_renaming: bool, item: ItemBase | None = None):
        if is_renaming and item is None:
            return

        self._is_editing = True
        model = TemporaryBookmarkModel(item.title if is_renaming else "NewBookmark")

        def on_value_changed(string_field, valid):
            string_field.style_type_name_override = "Field" if valid else "FieldError"

        def build_content():
            with ui.VStack():
                with ui.HStack():
                    ui.Spacer(height=0)
                    ui.Label("Enter the bookmark collection name:", width=0)
                    ui.Spacer(height=0)
                ui.Spacer(height=ui.Pixel(8))
                string_field = ui.StringField(model, height=ui.Pixel(24), style_type_name_override="Field")
            self._sub_popup_value_changed = model.subscribe_on_value_changed_callback(
                functools.partial(on_value_changed, string_field)
            )
            string_field.focus_keyboard()

        def on_positive():
            if not model.is_valid:
                return False
            self._is_editing = False
            self._sub_popup_value_changed = None
            new_title = model.get_value_as_string()
            # Create a collection if one does not already exist, otherwise rename the existing collection
            if is_renaming and item.data:
                if new_title == item.title:
                    self._model.refresh()
                    return True
                self._model.rename_collection(item.data, new_title, item.parent)
            else:
                with omni.kit.undo.group():
                    collection_path = self._model.create_collection(
                        new_title, item.parent if item is not None else None, use_undo_group=False
                    )
                    active_items = self._model.get_active_items()
                    if collection_path and active_items:
                        for path in active_items:
                            self._model.add_item_to_collection(str(path), collection_path, use_undo_group=False)
            return True

        def on_negative():
            self._is_editing = False
            self._sub_popup_value_changed = None
            return True

        _show_popup(
            f"{'Rename the' if is_renaming else 'Create a new'} bookmark collection",
            "Rename" if is_renaming else "Create",
            "Cancel",
            build_content,
            on_positive,
            on_negative,
            width=400,
            height=150,
        )

    @usd.handle_exception
    async def __refresh_async(self):
        # Refresh the collections expansion states
        await kit.app.get_app().next_update_async()
        for key, value in self._tree_expanded.items():
            tree_item = self._model.find_item(key, lambda i, title: i.title == title)
            if tree_item is not None:
                self._bookmark_tree_widget.set_expanded(tree_item, value, False)
        # Refresh the viewport selection
        await kit.app.get_app().next_update_async()
        self._on_active_items_changed(self._model.get_active_items())

    def _on_selection_changed(self, items: list[ItemBase], update_active_items: bool = True):
        # If an item is getting dragged, don't change the selection
        if self._delegate.dragged_item is not None:
            return
        # If create selected, don't do anything
        if next((x for x in items if x.component_type == ComponentTypes.create_collection.value), None):
            return
        selection_parents = []
        self._tree_selection = items
        for item in items:
            # If a collection is selection, select all its children
            if item.component_type == ComponentTypes.bookmark_collection.value and not all(
                elem in self._tree_selection for elem in item.children
            ):
                self._tree_selection.extend(item.children)
            # Make sure every parent of the selection is in the secondary selection
            parent = item.parent
            while parent is not None and parent not in self._tree_selection:
                selection_parents.append(parent)
                parent = parent.parent
        # If every item of a collection is selected it should not be secondary
        self._tree_selection_secondary = []
        for parent in selection_parents:
            if all(child in self._tree_selection for child in parent.children):
                self._tree_selection.append(parent)
            else:
                self._tree_selection_secondary.append(parent)
        # Update the delegate gradients & secondary selection
        self._delegate.on_item_selected(
            self._tree_selection, self._tree_selection_secondary, self._model.get_item_children(recursive=True)
        )
        if self._tree_selection and update_active_items:
            self._model.set_active_items(self._tree_selection)

    def _on_item_changed(self, model, item):
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.ensure_future(self.__refresh_async())

    def _on_active_items_changed(self, active_items: list[Any]):
        if not active_items:
            return
        selection_items = []
        bookmark_items = self._model.get_item_children(recursive=True)
        for active_item in active_items:
            for item in bookmark_items:
                if item.data != active_item:
                    continue
                selection_items.append(item)
                self.__set_root_item_expansion(item, True)
        self._on_selection_changed(selection_items, update_active_items=False)

    def _on_create_item_clicked(self):
        parent = None
        for selection in self._tree_selection:
            if selection.component_type == ComponentTypes.bookmark_collection.value:
                parent = selection
                break
        self.__show_temp_item_popup(False, parent)

    def _on_bookmark_collection_double_clicked(self, item: BookmarkCollectionItem):
        self.__show_temp_item_popup(True, item)

    def _on_delete_pressed(self, key, _, pressed):
        # Delete or Numpad Delete keys
        if key not in [int(carb.input.KeyboardInput.DEL), int(carb.input.KeyboardInput.NUMPAD_DEL)] or pressed:
            return
        # If currently editing a temporary item, delete should only edit the string field
        if self._is_editing:
            return
        self._remove_items()

    def _on_item_expanded(self, item: BookmarkCollectionItem, expanded: bool):
        self._tree_expanded[item.title] = expanded

    def _on_add_item_clicked(self, item: BookmarkCollectionItem):
        viewport_selection = self._model.get_active_items()
        for path in viewport_selection:
            self._model.add_item_to_collection(str(path), item.data)

    def _on_remove_item_clicked(self, item: ItemBase):
        if item.component_type == ComponentTypes.bookmark_collection.value:
            self._model.clear_collection(item.data)
        if item.component_type == ComponentTypes.bookmark_item.value:
            self._model.remove_item_from_collection(item.data, item.parent.data)

    def _on_delete_item_clicked(self, item: ItemBase):
        self._model.delete_collection(item.data, item.parent)

    def _remove_items(self):
        for item in self._tree_selection:
            parent = item.parent
            if item.component_type == ComponentTypes.bookmark_collection.value:
                if parent is not None:
                    self._model.remove_item_from_collection(item.data, parent.data)
                self._model.delete_collection(item.data, item.parent)
                continue
            if item.component_type == ComponentTypes.bookmark_item.value:
                self._model.remove_item_from_collection(item.data, parent.data)
                continue

    def destroy(self):
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        _reset_default_attrs(self)
