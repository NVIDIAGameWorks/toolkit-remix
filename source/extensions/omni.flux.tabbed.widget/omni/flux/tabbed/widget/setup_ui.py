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

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import omni.ui as ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.text_to_image import Rotation as _Rotation

from .tab_tree.delegate import Delegate as _Delegate
from .tab_tree.model import Model as _Model
from .tab_tree.tree import Tree as _Tree

if TYPE_CHECKING:
    from .tab_tree.model import Item as _Item


class SetupUI:
    def __init__(
        self,
        rotation: _Rotation = None,
        model: _Model = None,
        delegate: _Delegate = None,
        horizontal: bool = True,
        size_tab_label: Tuple[ui.Length, ui.Length] = None,
        disable_tab_toggle: bool = False,
        hidden_by_default: bool = False,
        width: ui.Length = None,
    ):
        """
        Create some tabs easily using this widget. Under, a treeview is used.

        Args:
            rotation: rotation of the label inside the tab
            model: the model of the tree view to use
            delegate: the delegate of the tree view to use
            horizontal: create the tabs horizontally or not
            size_tab_label: size of the label inside the tabs
            disable_tab_toggle: clicking on a tab will close the frame. Enable or disable this feature
            hidden_by_default: should the main frame be hidden by default or not
        """

        self._default_attr = {
            "_all_frames": None,
            "_model": None,
            "_tree": None,
            "_delegate": None,
            "_work_frame": None,
            "_previous_selection": None,
            "_zstack": None,
            "_background_scroll": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._size_tab_label = size_tab_label
        self._horizontal = horizontal
        self._disable_tab_toggle = disable_tab_toggle
        self._hidden_by_default = hidden_by_default
        self._model = _Model() if model is None else model
        if not horizontal and rotation is None:  # rotate by default in horizontal
            rotation = _Rotation.RIGHT_90
        self._delegate = _Delegate(rotation=rotation, horizontal=horizontal) if delegate is None else delegate

        self._all_frames = {}
        self._root_frame = ui.Frame()
        if width is not None:
            self._root_frame.width = width
        self.__create_ui()
        self.__on_tab_toggled = _Event()
        self.__on_selection_changed = _Event()

    def _selection_changed(self, item: "_Item"):
        """Call the event object that has the list of functions"""
        self.__on_selection_changed(item)

    def subscribe_selection_changed(self, function: Callable[["_Item"], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the selection of the tree change
        """
        return _EventSubscription(self.__on_selection_changed, function)

    def _tab_toggled(self, item: "_Item", visible: bool):
        """Call the event object that has the list of functions"""
        # fraction will let the widget to not oversize to the right
        if self._horizontal:
            self._root_frame.height = ui.Fraction(1) if visible else ui.Percent(0)
        else:
            self._root_frame.width = ui.Fraction(1) if visible else ui.Percent(0)
        self._tree.set_toggled_value([item], visible)
        self.__on_tab_toggled(item, visible)

    def subscribe_tab_toggled(self, function: Callable[["_Item", bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the selection of the tree change
        """
        return _EventSubscription(self.__on_tab_toggled, function)

    @property
    def root_frame(self):
        """Get the root frame of this widget"""
        return self._root_frame

    def get_frame(self, name: str) -> Optional[ui.Frame]:
        """
        Get the frame of a specific tab

        Args:
            name: the name of the tab

        Returns:
            The frame of the tab
        """
        return self._all_frames.get(name)

    def get_frames(self) -> Dict[str, ui.Frame]:
        """Get all the frames of all tabs"""
        return self._all_frames

    def add(self, datas: List[str]):
        """
        Add a tab

        Args:
            datas: list of string name that will be the title of each tab
        """
        with self._zstack:
            for data in datas:
                self._all_frames[data] = ui.Frame(visible=False)
        self._model.add(datas)
        if datas and not self.selection:
            self.selection = [self._model.get_item_children(None)[0].title]
        if datas and not any(self._delegate.get_toggled_values().values()):
            self._delegate.set_toggled_value([self._model.get_item_children(None)[0]], True)

    @property
    def model(self):
        return self._model

    def remove(self, datas: List[str]):
        """
        Remove tabs

        Args:
            datas: list of name of tab to remove
        """
        self._model.remove(datas)
        if datas and not any(self._delegate.get_toggled_values().values()):
            self._delegate.set_toggled_value([self._model.get_item_children(None)[0]], True)

    @property
    def selection(self):
        """Return the selected tab(s)"""
        return self._tree.selection

    @selection.setter
    def selection(self, values: List[str]):
        """Select tabs"""
        to_select = []
        for item in self._model.get_item_children(None):
            for value in values:
                if item.title == value and item not in to_select:
                    to_select.append(item)
        self._tree.selection = to_select

    def __create_ui(self):
        with self._root_frame:
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground")
                with ui.ScrollingFrame(
                    name="TreePanelBackground",
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    scroll_y_max=0,
                ):
                    with ui.VStack():
                        for _ in range(10):
                            with ui.HStack():
                                for _ in range(10):
                                    ui.Image(
                                        "",
                                        name="TreePanelLinesBackground",
                                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                        height=ui.Pixel(256),
                                        width=ui.Pixel(256),
                                    )
                with ui.Frame(separate_window=True):  # to keep the Z depth order
                    if self._horizontal:
                        stack = ui.VStack(content_clipping=True)
                    else:
                        stack = ui.HStack(content_clipping=True)
                    with stack:
                        if self._horizontal:
                            height = ui.Pixel(44)
                            width = ui.Percent(100)
                        else:
                            height = ui.Percent(100)
                            width = ui.Pixel(44)
                        with ui.ZStack(height=height, width=width):
                            # background of the scroll bar
                            if self._horizontal:
                                stack = ui.VStack()
                                height = ui.Pixel(12)
                                width = ui.Percent(100)
                            else:
                                stack = ui.HStack()
                                height = ui.Percent(100)
                                width = ui.Pixel(12)
                            with stack:
                                ui.Spacer()
                                with ui.Frame(
                                    separate_window=True, height=height, width=width
                                ):  # to keep the Z depth order
                                    self._background_scroll = ui.Rectangle(name="WorkspaceBackground")
                            if self._horizontal:
                                stack = ui.HStack()
                                height = 0
                                width = ui.Pixel(20)
                            else:
                                stack = ui.VStack()
                                height = ui.Pixel(20)
                                width = 0
                            with stack:
                                ui.Spacer(height=height, width=width)
                                scrollbar = ui.ScrollingFrame(
                                    name="PropertiesPaneSection",
                                    vertical_scrollbar_policy=(
                                        ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF
                                        if self._horizontal
                                        else ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                                    ),
                                    horizontal_scrollbar_policy=(
                                        ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF
                                        if not self._horizontal
                                        else ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                                    ),
                                )
                                with scrollbar:
                                    self._tree = _Tree(
                                        self._model,
                                        self._delegate,
                                        root_frame_name="TreePanel",
                                        selection_changed_fn=self.__do_selection_changed,
                                        horizontal=self._horizontal,
                                        size_tab_label=self._size_tab_label,
                                    )
                                if self._size_tab_label:
                                    if self._horizontal:
                                        scrollbar.height = self._size_tab_label[1]
                                    else:
                                        scrollbar.width = self._size_tab_label[0]
                        self._work_frame = ui.Frame(visible=not self._hidden_by_default, identifier="WorkFrame")
                        with self._work_frame:
                            with ui.ZStack():
                                ui.Rectangle(name="WorkspaceBackground")
                                if self._horizontal:
                                    stack = ui.HStack()
                                    height = 0
                                    width = ui.Pixel(12)
                                else:
                                    stack = ui.VStack()
                                    height = ui.Pixel(12)
                                    width = 0
                                with stack:
                                    self._zstack = ui.ZStack()
                                    ui.Spacer(width=width, height=height)

    def _set_work_frame_visibility(self, value):
        self._work_frame.visible = value
        self._background_scroll.visible = value

    def force_toggle(self, item: "_Item", value: bool):
        """
        Toggle or not a tab

        Args:
            item: the tab to toggle or not
            value: toggle or not
        """
        self.__do_selection_changed([item], force_value=value)

    def __do_selection_changed(self, selection: List["_Item"], force_value: Optional[bool] = None):
        if not selection:
            self._set_work_frame_visibility(False)
            self._previous_selection = self._tree.selection
            return
        if force_value is not None:
            self._set_work_frame_visibility(force_value)
            self._previous_selection = selection
            self._tab_toggled(selection[0], force_value)
            return
        if len(selection) > 1:
            self._tree.selection = [selection[0]]
        elif self._tree.selection == self._previous_selection and not self._disable_tab_toggle:
            self._set_work_frame_visibility(not self._work_frame.visible)
            self._tab_toggled(self._tree.selection[0], self._work_frame.visible)
        self._previous_selection = self._tree.selection
        self._selection_changed(self._tree.selection[0])

        for title, frame in self._all_frames.items():
            frame.visible = frame.enabled = title == self._tree.selection[0].title

    def destroy(self):
        for frame in self._all_frames.values():
            frame.destroy()
        _reset_default_attrs(self)
