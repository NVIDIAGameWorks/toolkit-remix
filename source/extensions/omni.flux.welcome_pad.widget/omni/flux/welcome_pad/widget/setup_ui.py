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

from __future__ import annotations

import asyncio
import typing
from collections.abc import Callable

import omni.usd
from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.label import create_label_with_font

from .delegate import Delegate
from .model import Model

if typing.TYPE_CHECKING:
    from .model import Item as _Item


class WelcomePadWidget:
    def __init__(
        self,
        model: Model = None,
        show_footer: bool = True,
        footer: str = None,
        footer_callback: Callable[[float, float, int, int], None] = None,
        title: str = None,
        auto_resize_list: bool = True,
        word_wrap_description: bool = True,
        create_demo_items: bool = True,
    ):
        """
        Create a pad

        Args:
            model: model that will feed the pad and show what we want
            show_footer: show the footer or not
            footer: text of the footer
            footer_callback: function called when the user release the mouse from the footer text
            title: title of your pad
            auto_resize_list: if the list of items is bigger than the frame they are in, resize the list automatically
            word_wrap_description: word wrap the description
            create_demo_items: create default demo items

        Returns:
            The created pad object
        """
        self._default_attr = {
            "_on_resize_tree_content_task": None,
            "_tree_view_scroll_frame": None,
            "_spacer_tree_view": None,
            "_image_provider_title": None,
            "_label_footer": None,
            "_tree_view": None,
            "_model": None,
            "_delegate": None,
            "_subscription_items_enabled": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._title = title or "Title"
        self._footer = footer or "Footer..."
        self.__auto_resize_list = auto_resize_list
        self._footer_callback = footer_callback
        self._show_footer = show_footer
        self._on_resize_tree_content_task = None

        self._delegate = Delegate(word_wrap_description=word_wrap_description)
        self._model = Model(create_demo_items=create_demo_items) if model is None else model

        self._subscription_items_enabled = self._model.subscribe_items_enabled(self._on_items_enabled)
        self.__create_ui()

    @property
    def model(self):
        """Model of the treeview"""
        return self._model

    def __create_ui(self):
        with ui.VStack():
            style = ui.Style.get_instance()
            current_dict = style.default
            if "ImageWithProvider::WelcomePadTitle" not in current_dict:
                # use regular labels
                ui.Label(self._title)
            else:
                # use custom styled font
                self._image_provider_title, _, _ = create_label_with_font(
                    self._title, "WelcomePadTitle", remove_offset=True, offset_divider=2
                )

            ui.Spacer(height=ui.Pixel(16))
            ui.Line(height=0, name="WelcomePadTop")
            ui.Spacer(height=ui.Pixel(52))

            with ui.ZStack():
                self._spacer_tree_view = ui.Spacer()
                if self.__auto_resize_list:
                    self._spacer_tree_view.set_computed_content_size_changed_fn(self._spacer_tree_view_size_changed)
                self._tree_view_scroll_frame = ui.ScrollingFrame(
                    name="WelcomePad",
                    vertical_scrollbar_policy=(
                        ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF
                        if self.__auto_resize_list
                        else ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                    ),
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                )
                with self._tree_view_scroll_frame:
                    self._tree_view = ui.TreeView(
                        self._model, delegate=self._delegate, header_visible=False, name="WelcomePad"
                    )

            ui.Spacer(height=ui.Pixel(4))  # 4 pixels and not 20, because the last item has a space of 16

            if self._show_footer:
                ui.Line(height=0, name="WelcomePadTop")

                with ui.HStack(height=0):
                    ui.Spacer(height=0)
                    with ui.VStack(width=0):
                        ui.Spacer(height=ui.Pixel(32 - 18))

                        self._label_footer = ui.Label(
                            self._footer,
                            name="WelcomePadFooter",
                            alignment=ui.Alignment.LEFT,
                            height=0,
                            mouse_released_fn=self._on_footer_released,
                        )

            ui.Spacer(height=ui.Pixel(24))
        self.resize_tree_content()

    def get_item_background_widgets(self) -> dict[str, ui.Widget]:
        """
        Get the background rectangle of all items

        Returns:
            A list of rectangle
        """
        return self._delegate.get_background_widgets()

    @property
    def delegate(self):
        """Delegate of the tree"""
        return self._delegate

    def _on_items_enabled(self, _, __):
        self._tree_view.dirty_widgets()

    def get_current_selection(self) -> list[_Item]:
        """Get selected item from the tree view"""
        return self._tree_view.selection

    def set_current_selection(self, item: _Item | None):
        """
        Set the selection on the tree view

        Args:
            item: the item to select
        """
        if item is None:
            self._tree_view.selection = []
            return
        self._tree_view.selection = [item]

    def subscribe_selection_changed(self, callback):
        """Subscribe when the selection of the treeview change"""
        return self._tree_view.set_selection_changed_fn(callback)

    def _on_footer_released(self, x, y, b, m):
        if self._footer_callback is not None:
            self._footer_callback(x, y, b, m)

    def _spacer_tree_view_size_changed(self):
        self.resize_tree_content()

    def resize_tree_content(self):
        """
        If the list of items is bigger than the frame they are in, resize the list automatically
        """
        if self._on_resize_tree_content_task:
            self._on_resize_tree_content_task.cancel()
        self._on_resize_tree_content_task = asyncio.ensure_future(self._deferred_resize_tree_content())

    @omni.usd.handle_exception
    async def _deferred_resize_tree_content(self):
        if self._tree_view_scroll_frame is None:
            return
        self._tree_view_scroll_frame.height = ui.Pixel(1)
        for _ in range(3):  # wait 3 frame to calculate the content height
            await omni.kit.app.get_app().next_update_async()
        size_one_content = 152 + 16
        if self._model is None:
            return
        content_size = self._model.get_size_data() * size_one_content
        spacer_tree_view_height = self._spacer_tree_view.computed_height
        self._tree_view_scroll_frame.height = ui.Pixel(int(spacer_tree_view_height))
        if not self.__auto_resize_list:
            return
        if spacer_tree_view_height < content_size:
            value = int(spacer_tree_view_height // size_one_content)
            current_value = self._model.get_list_limit()
            if current_value != value:
                self._delegate.reset_delegate()
                self._model.set_list_limit(value)
                self._tree_view.dirty_widgets()
        elif self._model.get_list_limit() is not None:
            self._delegate.reset_delegate()
            self._model.set_list_limit(None)
            self._tree_view.dirty_widgets()

    def destroy(self):
        """Destroy."""
        _reset_default_attrs(self)
