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

import carb
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .tree.delegate import Delegate
from .tree.model import Model


class PanelOutlinerWidget:
    def __init__(
        self,
        tree_model: Model | None = None,
        tree_delegate: Delegate | None = None,
        show_menu_burger: bool = True,
        show_title: bool = True,
    ):
        """
        Panel outliner widget

        Args:
            tree_model: model that will feed the outliner (that is already initialized)
            tree_delegate: custom delegate (that should not be initialized)
            show_menu_burger: show the burger menu or not
            show_title: show the title or not
        """

        self._default_attr = {
            "_menu_burger_widget": None,
            "_title_label": None,
            "_title_field": None,
            "_tree_model": None,
            "_tree_delegate": None,
            "_title_stack": None,
            "_arrow_back_title": None,
            "_tree_view_last_selection": None,
            "_tree_view": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._tree_model = Model() if tree_model is None else tree_model
        self._tree_delegate = Delegate() if tree_delegate is None else tree_delegate
        self.__default_title = "Default title"
        self.__show_menu_burger = show_menu_burger
        self.__show_title = show_title
        self.title_clicked_fn = None

        self._ignore_selection_event = False
        self._tree_view_last_selection = []

        self.__on_title_updated = _Event()
        self.__on_tree_selection_changed = _Event()

        self.__create_ui()

    def _title_updated(self):
        """Call the event object that has the list of functions"""
        self.__on_title_updated(self.__default_title)

    def subscribe_title_updated(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_title_updated, function)

    def _tree_selection_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_tree_selection_changed(self._tree_view.selection)

    def subscribe_tree_selection_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_tree_selection_changed, function)

    def subscribe_to_title_pressed_fn(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return self._title_stack.mouse_pressed_fn(function)

    def set_selection(self, item):
        if item.enabled:
            self._tree_view.selection = [item]
            self._tree_view_last_selection = [item]

    def get_selection(self):
        """Get the tree selection"""
        return self._tree_view.selection

    def set_title(self, value: str, deferred=False):
        """
        Set the title of the outliner panel

        Args:
            value: the title
            deferred: wait 1 frame or not
        """
        self.__default_title = value
        if deferred:
            asyncio.ensure_future(self._deferred_set_title(value))
        else:
            self.__update_title()

    def set_title_clicked_fn(self, title_clicked_fn):
        carb.log_warn("set_title_clicked_fn is deprecated. Please use subscribe_to_title_pressed_fn")
        self.title_clicked_fn = title_clicked_fn

    @omni.usd.handle_exception
    async def _deferred_set_title(self, value: str):
        await omni.kit.app.get_app_interface().next_update_async()
        self.__update_title()

    @property
    def menu_burger_widget(self):
        """Get the menu burger widget"""
        return self._menu_burger_widget

    @property
    def arrow_back_title_widget(self):
        """Get the arrow back widget"""
        return self._arrow_back_title

    @property
    def title_widget(self):
        """Get the title widget"""
        return self._title_label

    @property
    def title_field_widget(self):
        return self._title_field

    def __update_title(self):
        self._title_stack.clear()
        with self._title_stack:
            # content_clipping to get interaction on separate_window
            # Set a field behind the title, to be able to edit it when we double click on
            # the (rasterized) title
            self._title_field = ui.StringField(visible=False)
            self._title_field.model.set_value(self.__default_title)
            self._title_field.model.add_end_edit_fn(self._on_end_edit_title)
            self._title_label = ui.Label(
                self.__default_title, name="TreePanelTitle", elided_text=True, tooltip=self.__default_title
            )

        self._title_updated()

    def _on_end_edit_title(self, model):
        value = model.get_value_as_string()
        if not value.strip():
            carb.log_error("Please set a valid name")
            return
        self.set_title(value.strip(), deferred=True)

    def _on_title_double_clicked(self):
        self._title_label.visible = False
        self._title_field.visible = True
        self._title_field.focus_keyboard(True)

    def _on_title_single_clicked(self):
        if self.title_clicked_fn is not None:
            self.title_clicked_fn()

    def __create_ui(self):
        with ui.ZStack():
            ui.Rectangle(name="WorkspaceBackground")
            with ui.ScrollingFrame(
                name="TreePanelBackground",
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                scroll_y_max=0,
            ):
                with ui.VStack():
                    for _ in range(5):
                        ui.Image(
                            "",
                            name="TreePanelLinesBackground",
                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                            height=ui.Pixel(256),
                            width=ui.Pixel(256),
                        )
            with ui.Frame(separate_window=True):  # to keep the Z depth order
                with ui.ZStack():
                    ui.Rectangle(name="TreePanelBackground")
                    with ui.VStack(content_clipping=True):
                        ui.Spacer(height=ui.Pixel(24))
                        # menu
                        if self.__show_menu_burger:
                            with ui.HStack(height=ui.Pixel(24)):
                                ui.Spacer(width=ui.Pixel(16 + 4))
                                with ui.VStack(width=ui.Pixel(16)):
                                    ui.Spacer(height=ui.Pixel(4))
                                    with ui.ZStack(width=ui.Pixel(16), height=ui.Pixel(16)):
                                        ui.Rectangle(name="MenuBurgerBackground")
                                        self._menu_burger_widget = ui.Image("", name="MenuBurger")
                                    ui.Spacer(height=ui.Pixel(4))
                            ui.Spacer(height=ui.Pixel(8))
                        # back + title
                        if self.__show_title:
                            with ui.HStack(height=ui.Pixel(24)):
                                ui.Spacer(width=ui.Pixel(16 + 4))
                                with ui.VStack(width=ui.Pixel(16)):
                                    ui.Spacer(height=ui.Pixel(4))
                                    self._arrow_back_title = ui.Image(
                                        "", name="GoBack", width=ui.Pixel(16), height=ui.Pixel(16)
                                    )
                                    ui.Spacer(height=ui.Pixel(4))
                                ui.Spacer(width=ui.Pixel(8))

                                # label
                                self._title_stack = ui.ZStack(
                                    content_clipping=True,
                                    mouse_pressed_fn=lambda x, y, b, m: self._on_title_single_clicked(),
                                    mouse_double_clicked_fn=lambda x, y, b, m: self._on_title_double_clicked(),
                                )
                                self.__update_title()
                            ui.Spacer(height=ui.Pixel(8))
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(36))
                            self._tree_view = ui.TreeView(
                                self._tree_model,
                                delegate=self._tree_delegate,
                                root_visible=False,
                                header_visible=False,
                                name="TreePanel",
                            )
                            self._tree_view.set_selection_changed_fn(self._on_tree_selection_changed)

    def _expand_tree_items(self, items, value):
        for item in items:
            self._tree_view.set_expanded(item, value, True)

    def _is_tree_item_expanded(self, item) -> bool:
        return self._tree_view.is_expanded(item)

    def _on_tree_selection_changed(self, items):
        def select_parent(item, value, deferred=False):
            if deferred:
                asyncio.ensure_future(_deferred_select_parent(item, value))
            else:
                _select_parent(item, value)

        @omni.usd.handle_exception
        async def _deferred_select_parent(item, value):
            await omni.kit.app.get_app().next_update_async()
            _select_parent(item, value)

        def _select_parent(item, value):
            item.selected = value
            widget = self._tree_delegate.get_item_widget(item)
            if widget:
                widget.selected = value
            widget = self._tree_delegate.get_icon_item_widget(item)
            if widget:
                widget.selected = value
            if item.parent is not None:
                _select_parent(item.parent, value)

        def select_children(item, value):
            item.selected = value
            widget = self._tree_delegate.get_item_widget(item)
            if widget:
                widget.selected = value
            widget = self._tree_delegate.get_icon_item_widget(item)
            if widget:
                widget.selected = value
            for children_item in item.children_items:
                select_children(children_item, value)

        if self._ignore_selection_event:
            return

        self._ignore_selection_event = True

        # filter disabled items
        size = len(items)
        items = [item for item in items if item.enabled]
        disabled_in_list = size != len(items)

        # first, reset all states
        root_items = self._tree_model.get_item_children(None)
        root_items = [item for item in root_items if item.enabled]
        for root_item in root_items:
            select_children(root_item, False)

        if not items:
            if disabled_in_list:
                self._tree_view.selection = self._tree_view_last_selection
            self._tree_selection_changed()
            self._ignore_selection_event = False
            return

        # if the item has children, we can't select it, we select the first child
        if items[0].children_items:
            if not self._is_tree_item_expanded(items[0]):
                self._expand_tree_items([items[0]], True)
            self._tree_view.selection = [items[0].children_items[0]]
            self._tree_view_last_selection = [items[0].children_items[0]]
            select_parent(items[0].children_items[0], True, deferred=True)
            self._tree_selection_changed()
            self._ignore_selection_event = False
            return

        for selected_item in items:
            select_parent(selected_item, True)
        self._tree_view.selection = [items[0]]  # no multi selection
        self._tree_view_last_selection = [items[0]]

        self._tree_selection_changed()
        self._ignore_selection_event = False

    def destroy(self):
        self.__on_title_updated = None
        self.__on_tree_selection_changed = None
        _reset_default_attrs(self)
