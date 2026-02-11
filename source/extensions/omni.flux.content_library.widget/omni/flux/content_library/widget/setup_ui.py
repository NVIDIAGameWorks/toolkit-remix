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

import functools
from typing import TYPE_CHECKING
from collections.abc import Callable

import omni.ui as ui
from omni.flux.content_library.property.widget import ContentLibraryPropertyWidget as _ContentLibraryPropertyWidget
from omni.flux.content_viewer.widget import ContentViewerWidget as _ContentViewerWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.button import create_button_with_custom_font as _create_button_with_custom_font
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font
from omni.flux.utils.widget.search import create_search_widget as _create_search_widget

from .tree.delegate import Delegate as _DelegateMenu
from .tree.model import Model as _ModelMenu

if TYPE_CHECKING:
    from omni.flux.content_viewer.widget.core import ContentData, ContentViewerCore


class ContentLibraryWidget:
    def __init__(
        self,
        content_viewer_cores: dict[str, list["ContentViewerCore"]],
        viewer_type=type[_ContentViewerWidget] | None,
        tree_model_menu: _ModelMenu | None = None,
        tree_delegate_menu: _DelegateMenu | None = None,
        tree_metadata_widget: _ContentLibraryPropertyWidget | None = None,
        title: str = "Title",
        load_button_display: str = "Load",
        cancel_button_display: str = "Cancel",
        search_widget_callback: Callable[[str], None] = None,
    ):
        """
        Content library widget

        Args:
            content_viewer_cores: list of viewer core to use. For each core, a viewer will be created inside a
                collapsable frame. The title of the collapsable frame is `core.name`
            viewer_type: the viewer type to use for each core
            tree_model_menu: the model of the tree menu on the left
            tree_delegate_menu: the delegate of the tree menu of the left
            title: the title of the widget (top left)
            load_button_display: the name that will be display of the load button
            cancel_button_display: the name that will be display of the cancel button
            search_widget_callback: the function that will be called to create the search widget
        """

        self._default_attr = {
            "_label_choose": None,
            "_menu_burger_widget": None,
            "_tree_model_menu": None,
            "_tree_delegate_menu": None,
            "_tree_view_menu": None,
            "_tree_metadata_widget": None,
            "_image_provider_header_collap_frame": None,
            "_image_provider_choose_metadata": None,
            "_subscription_tree_model_menu_items_selected_changed": None,
            "_block_on_tree_view_menu_selection_changed": False,
            "_content_viewer_cores": None,
            "_content_viewer_frame": None,
            "_selection_subscriptions": None,
            "_content_viewers": None,
            "_data_frame": None,
            "_load_button_tuple": None,
            "_cancel_button_tuple": None,
            "_label_error": None,
            "_menu_arrangement_grid_widget": None,
            "_menu_arrangement_list_widget": None,
            "_filter_widget": None,
            "_search_widget": None,
            "_search_widget_callback": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__block_selection_event = False
        self._image_provider_header_collap_frame = None
        self.__title = title
        self.__load_button_display = load_button_display
        self.__cancel_button_display = cancel_button_display

        self._tree_model_menu = _ModelMenu([]) if tree_model_menu is None else tree_model_menu
        self._tree_delegate_menu = _DelegateMenu() if tree_delegate_menu is None else tree_delegate_menu

        self._tree_metadata_widget = (
            _ContentLibraryPropertyWidget() if tree_metadata_widget is None else tree_metadata_widget
        )

        self._content_viewer_cores = content_viewer_cores
        self._content_viewer_type = _ContentViewerWidget if viewer_type is None else viewer_type

        self._search_widget_callback = (
            _create_search_widget if search_widget_callback is None else search_widget_callback
        )

        self._selection_subscriptions = []
        self._content_viewers = []

        self.__create_ui()

        for _menu_title, content_viewer_cores_list in self._content_viewer_cores.items():
            if not content_viewer_cores_list:
                continue
            for content_viewer_core in content_viewer_cores_list:
                self._selection_subscriptions.append(
                    content_viewer_core.subscribe_selection_changed(
                        functools.partial(self._on_content_viewer_selection_changed, content_viewer_core)
                    )
                )

        self._subscription_tree_model_menu_items_selected_changed = (
            self._tree_model_menu.subscribe_items_selected_changed(self._on_tree_model_menu_items_selected_changed)
        )
        self._on_tree_model_menu_items_selected_changed()

        self.__on_load = _Event()
        self.__on_cancel = _Event()

    def _load(self):
        """Call the event object that has the list of functions"""
        result = []
        for _menu_title, content_viewer_cores in self._content_viewer_cores.items():
            if not content_viewer_cores:
                continue
            for content_viewer_core in content_viewer_cores:
                result.extend(content_viewer_core.get_selection())
        self.__on_load(result)

    def subscribe_load(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on the load button
        """
        return _EventSubscription(self.__on_load, function)

    def _cancel(self):
        """Call the event object that has the list of functions"""
        self.__on_cancel()

    def subscribe_cancel(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on the cancel button
        """
        return _EventSubscription(self.__on_cancel, function)

    def _get_current_content_viewer_cores(self) -> list["ContentViewerCore"]:
        result = []
        current_selected_titles = [
            item.title for item in self._tree_model_menu.get_item_children(None) if item.selected
        ]
        if not current_selected_titles:
            return result
        for menu_title, content_viewer_cores in self._content_viewer_cores.items():
            if menu_title in current_selected_titles:
                result.extend(content_viewer_cores)
        return result

    def _refresh_content_stack(self):
        if self._content_viewers:
            for content_viewer in self._content_viewers:
                content_viewer.destroy()
        self._content_viewers = []
        self._tree_metadata_widget.model.set_items_from_data([])
        self._content_viewer_frame.clear()
        content_viewer_cores = self._get_current_content_viewer_cores()
        if content_viewer_cores:
            self._data_frame.visible = True
            with self._content_viewer_frame:
                with ui.VStack():
                    for i, content_viewer_core in enumerate(content_viewer_cores):
                        with ui.CollapsableFrame(
                            collapsed=False,
                            title=content_viewer_core.name,
                            name="ContentLibraryChoose",
                            build_header_fn=self.__build_collapsable_frame_header,
                            height=0,
                        ):
                            with ui.Frame(height=ui.Pixel(300)):
                                viewer = self._content_viewer_type(content_viewer_core)
                                viewer.set_filter_content_title_value(self._search_widget.get_current_text())
                                self._content_viewers.append(viewer)
                        if i != len(content_viewer_cores) - 1:
                            ui.Spacer(height=ui.Pixel(8))
                    self.refresh_content()
        else:
            self._data_frame.visible = False

    def refresh_content(self):
        """Refresh the content"""
        value = self._menu_arrangement_list_widget.selected
        for viewer in self._content_viewers:
            viewer.set_list_view_mode(value)
        for core in self._get_current_content_viewer_cores():
            core.refresh_content()

    def __create_ui(self):
        def _on_mouse_pressed(button, widgets, other_widgets, callback=None):
            if button != 0:
                return
            value = True
            for widget in widgets:
                value = not widget.selected
                widget.selected = value
            for widget in other_widgets:
                widget.selected = not value
            if callback is not None:
                callback()

        style = ui.Style.get_instance()
        current_dict = style.default

        with ui.ZStack():
            ui.Rectangle(name="ContentViewerRootWidgetBackground")
            with ui.HStack():
                ui.Spacer(width=ui.Pixel(24))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(24))
                    self._label_choose = ui.Label(
                        self.__title, name="ContentLibraryChoose", alignment=ui.Alignment.LEFT, height=0
                    )
                    ui.Spacer(height=ui.Pixel(24))
                    with ui.HStack(height=0):
                        # menu burger
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(4))
                            self._menu_burger_widget = ui.Image(
                                "", name="MenuBurger", height=ui.Pixel(16), width=ui.Pixel(16)
                            )
                            ui.Spacer(height=ui.Pixel(4))
                        ui.Spacer()

                        # arrangement grid filter
                        with ui.VStack(width=0):
                            ui.Spacer(height=ui.Pixel(4))
                            zstack_grid = ui.ZStack(height=ui.Pixel(16), width=ui.Pixel(16))
                            with zstack_grid:
                                rec_grid = ui.Rectangle(name="ContentLibraryBackgroundIcon")
                                self._menu_arrangement_grid_widget = ui.Image("", name="ArrangementGrid")
                            ui.Spacer(height=ui.Pixel(4))
                        ui.Spacer(width=ui.Pixel(8))

                        # arrangement list filter
                        with ui.VStack(width=0):
                            ui.Spacer(height=ui.Pixel(4))
                            zstack_list = ui.ZStack(height=ui.Pixel(16), width=ui.Pixel(16))
                            with zstack_list:
                                rec_list = ui.Rectangle(name="ContentLibraryBackgroundIcon")
                                self._menu_arrangement_list_widget = ui.Image("", name="ArrangementList")
                            ui.Spacer(height=ui.Pixel(4))

                        # icons values
                        zstack_grid.set_mouse_pressed_fn(
                            lambda x, y, b, m: _on_mouse_pressed(
                                b,
                                [rec_grid, self._menu_arrangement_grid_widget],
                                [rec_list, self._menu_arrangement_list_widget],
                                callback=self.refresh_content,
                            )
                        )
                        zstack_list.set_mouse_pressed_fn(
                            lambda x, y, b, m: _on_mouse_pressed(
                                b,
                                [rec_list, self._menu_arrangement_list_widget],
                                [rec_grid, self._menu_arrangement_grid_widget],
                                callback=self.refresh_content,
                            )
                        )
                        # default value
                        _on_mouse_pressed(
                            0,
                            [rec_grid, self._menu_arrangement_grid_widget],
                            [rec_list, self._menu_arrangement_list_widget],
                        )
                        ui.Spacer(width=ui.Pixel(16))
                        with ui.HStack(width=ui.Pixel(16)):
                            with ui.VStack():
                                ui.Spacer(height=ui.Pixel(3))
                                rect1 = ui.Rectangle(width=0, height=0)
                                ui.Spacer(height=ui.Pixel(18))
                                rect2 = ui.Rectangle(width=0, height=0)
                                ui.FreeBezierCurve(
                                    rect1,
                                    rect2,
                                    start_tangent_width=ui.Percent(1),
                                    end_tangent_width=ui.Percent(1),
                                    name="ContentLibraryChooseLine",
                                )
                                ui.Spacer(height=ui.Pixel(3))
                            ui.Spacer()
                        # filter
                        with ui.VStack(width=0):
                            ui.Spacer(height=ui.Pixel(4))
                            zstack_filter = ui.ZStack(height=ui.Pixel(16), width=ui.Pixel(16))
                            with zstack_filter:
                                rec_filter = ui.Rectangle(name="ContentLibraryBackgroundIconFilter")
                                self._filter_widget = ui.Image("", name="Filter")
                            zstack_filter.set_mouse_pressed_fn(
                                lambda x, y, b, m: _on_mouse_pressed(b, [rec_filter, self._filter_widget], [])
                            )
                            ui.Spacer(height=ui.Pixel(4))
                        ui.Spacer(width=ui.Pixel(16))

                        # search widget
                        self._search_widget = self._search_widget_callback(self._search)
                    ui.Spacer(height=ui.Pixel(24 - 8))

                    with ui.HStack():
                        # left menu
                        with ui.VStack(width=ui.Pixel(136)):
                            ui.Spacer(height=ui.Pixel(8))
                            self._tree_view_menu = ui.TreeView(
                                self._tree_model_menu,
                                delegate=self._tree_delegate_menu,
                                root_visible=False,
                                header_visible=False,
                                name="ContentLibraryChoose",
                            )
                            self._tree_view_menu.set_selection_changed_fn(self._on_tree_view_menu_selection_changed)
                        self._data_frame = ui.Frame()
                        with self._data_frame:
                            with ui.VStack():
                                ui.Spacer(height=ui.Pixel(8))
                                with ui.ScrollingFrame(name="ContentLibraryChoose"):
                                    self._content_viewer_frame = ui.Frame()

                                with ui.VStack(height=ui.Pixel(288)):
                                    ui.Spacer(height=ui.Pixel(16))
                                    if "ImageWithProvider::ContentLibraryChooseMetadata" not in current_dict:
                                        # use regular labels
                                        ui.Label("Metadata")
                                    else:
                                        # use custom styled font
                                        self._image_provider_choose_metadata, _, _ = _create_label_with_font(
                                            "Metadata", "ContentLibraryChooseMetadata", remove_offset=False
                                        )

                                    with ui.VStack(height=ui.Pixel(8)):
                                        ui.Spacer()
                                        ui.Line(name="ContentLibraryChooseLine")
                                    ui.Spacer(height=ui.Pixel(8))
                                    with ui.Frame(height=ui.Pixel(152)):
                                        self._tree_metadata_widget.create_ui()
                                    ui.Spacer(height=ui.Pixel(32))
                                    with ui.HStack(height=ui.Pixel(24)):
                                        ui.Spacer()
                                        with ui.Frame():  # add a frame to be able to have a stable "hiding"
                                            self._label_error = ui.Label(
                                                "", name="ContentLibraryError", height=0, visible=False
                                            )
                                        with ui.Frame(width=ui.Pixel(132)):
                                            if "ImageWithProvider::ContentLibraryLoad" not in current_dict:
                                                # use regular labels
                                                ui.Button(self.__load_button_display, clicked_fn=self.__on_load_pressed)
                                            else:
                                                # use custom styled font
                                                self._load_button_tuple = _create_button_with_custom_font(
                                                    self.__load_button_display,
                                                    "ContentLibraryLoad",
                                                    "ContentLibraryLoadRectangle",
                                                    ui.Pixel(16),
                                                    ui.Pixel(4),
                                                    pressed_fn=self.__on_load_pressed,
                                                )
                                        ui.Spacer(width=ui.Pixel(32))
                                        with ui.Frame(width=ui.Pixel(84)):
                                            if "ImageWithProvider::ContentLibraryLoad" not in current_dict:
                                                # use regular labels
                                                ui.Button(
                                                    self.__cancel_button_display, clicked_fn=self.__on_cancel_pressed
                                                )
                                            else:
                                                # use custom styled font
                                                self._cancel_button_tuple = _create_button_with_custom_font(
                                                    self.__cancel_button_display,
                                                    "ContentLibraryLoad",
                                                    "ContentLibraryLoadRectangle",
                                                    ui.Pixel(16),
                                                    ui.Pixel(4),
                                                    pressed_fn=self.__on_cancel_pressed,
                                                )
                                    ui.Spacer(height=ui.Pixel(32))
                ui.Spacer(width=ui.Pixel(24))

    def __on_load_pressed(self):
        self._label_error.visible = False
        self._load()

    def __on_cancel_pressed(self):
        self._label_error.visible = False
        self._cancel()

    def show_message(self, message: str):
        """
        Show a message at the bottom on the widget

        Args:
            message: the message to show
        """
        self._label_error.text = message
        self._label_error.visible = True

    def _search(self, text):
        for content_viewer in self._content_viewers:
            content_viewer.filter_content(text)

    def _on_content_viewer_selection_changed(self, core: "ContentViewerCore", items: list["ContentData"]):
        # un-select the other viewers
        if not self.__block_selection_event:
            self.__block_selection_event = True
            for content_viewer_core in self._get_current_content_viewer_cores():
                if content_viewer_core != core:
                    content_viewer_core.set_selection(None)

            # set metadata
            all_selection = list(
                filter(
                    None,
                    [
                        content_viewer_core.get_selection()
                        for content_viewer_core in self._get_current_content_viewer_cores()
                    ],
                )
            )
            if not items and not all_selection:
                self._tree_metadata_widget.model.set_items_from_data([])
            elif items:
                self._tree_metadata_widget.model.set_items_from_data(items)
                self._label_error.text = ""
                self._label_error.visible = False

            self.__block_selection_event = False

    def _on_tree_view_menu_selection_changed(self, items):
        if not items or self._block_on_tree_view_menu_selection_changed:
            return
        self._tree_model_menu.set_items_selected(items)

    def _on_tree_model_menu_items_selected_changed(self):
        self._block_on_tree_view_menu_selection_changed = True
        self._tree_view_menu.selection = [
            item for item in self._tree_model_menu.get_item_children(None) if item.selected
        ]
        self._refresh_content_stack()
        self._block_on_tree_view_menu_selection_changed = False

    def __build_collapsable_frame_header(self, collapsed, text):
        with ui.VStack():
            # ui.Spacer(height=ui.Pixel(4))  # we don't spacing because by default there is one
            with ui.HStack(height=ui.Pixel(16)):
                # ui.Spacer(width=ui.Pixel(4))  # we don't spacing because by default there is one
                ui.Image(
                    name="TreeViewBranchCollapsed" if collapsed else "TreeViewBranchExpanded",
                    width=ui.Pixel(16),
                    height=ui.Pixel(16),
                )
                ui.Spacer(width=ui.Pixel(8))
                style = ui.Style.get_instance()
                current_dict = style.default
                if "ImageWithProvider::ContentLibraryChooseHeader" not in current_dict:
                    # use regular labels
                    ui.Label(text)
                else:
                    # use custom styled font
                    if self._image_provider_header_collap_frame is None:
                        self._image_provider_header_collap_frame = []
                    image_provider, _, _ = _create_label_with_font(
                        text, "ContentLibraryChooseHeader", remove_offset=True, offset_divider=2
                    )
                self._image_provider_header_collap_frame.append(image_provider)
                ui.Spacer()
            # ui.Spacer(height=ui.Pixel(4))  # we don't spacing because by default there is one

    def destroy(self):
        _reset_default_attrs(self)
