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
import typing
from pathlib import Path

import carb
import carb.input
import omni.appwindow
import omni.ui as ui

from .core_detail_popup import AssetDetailCore
from .delegate_detail_poup import AssetDetailTagsDelegate
from .model_detail_popup import AssetDetailTagsModel

if typing.TYPE_CHECKING:
    from .core import ContentData


class AssetDetailWindow:

    WINDOW_NAME = "Asset details"
    WINDOW_IMAGE_BIGGER_NAME = "Image bigger"

    def __init__(self):
        self.__default_attr = {"_core": None, "_window": None, "_dockspace_window": None, "_window_bigger_image": None}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self.__style = {
            "Label::Search": {"color": 0x908A8777},
            "Image::Cross": {"color": 0xFF8A8777, "margin": 3},
            "Image::Search": {"color": 0xFF8A8777},
            "Rectangle::MainFrame": {"border_color": 0xFF23211F, "border_width": 4, "background_color": 0xFF343432},
            "Rectangle::Background": {"background_color": 0xFF23211F},
            "Rectangle::Search": {"background_color": 0xFF23211F},
            "TreeView": {
                "background_color": 0xFF23211F,
                "background_selected_color": 0x664F4D43,
                "secondary_color": 0xFF403B3B,
            },
            "TreeView.ScrollingFrame": {"background_color": 0xFF23211F},
            "TreeView.Header": {"background_color": 0xFF343432, "color": 0xFFCCCCCC, "font_size": 13},
            "TreeView.Item": {"color": 0xFF8A8777},
            "TreeView.Item:selected": {"color": 0xFF23211F},
            "TreeView:selected": {"background_color": 0xFF8A8777},
        }

        self._core = AssetDetailCore()

        self.__bigger_image = None
        self.__primary_thumnail = None
        self.__tree_view = None  # noqa PLW0238
        self.__string_field_custom_tags = None
        self.__string_field_name = None
        self.__string_field_file_path = None
        self.__action_search_attr = None
        self.__cross_image = None
        self.__label_search = None
        self.__show_window_task = None

        self.__cancel_mouse_hovered = False

        self._appwindow = omni.appwindow.get_default_app_window()
        self._mouse = self._appwindow.get_mouse()
        self._input = carb.input.acquire_input_interface()
        self._dpi_scale = ui.Workspace.get_dpi_scale()

        self.__model = AssetDetailTagsModel(self._core)
        self.__delegate = AssetDetailTagsDelegate(self._on_image_hovered)

        self.__create_ui()
        self.__create_bigger_image_ui()

    @property
    def current_extension_path(self):
        current_path = Path(__file__).parent
        for _ in range(4):
            current_path = current_path.parent
        return current_path

    @property
    def calling_extension_path(self):
        return self.current_extension_path

    def _get_icon_path(self, name: str, from_base_extension=True):
        """Get an icon path form his name"""
        if from_base_extension:
            path = self.current_extension_path.joinpath("icons", f"{name}.svg")
        else:
            path = self.calling_extension_path.joinpath("icons", f"{name}.svg")
        if path.exists():
            return path
        return None

    def __create_ui(self):
        self._window = ui.Window(
            self.WINDOW_NAME,
            width=404,
            height=600,
            visible=False,
            # flags=ui.WINDOW_FLAGS_POPUP | ui.WINDOW_FLAGS_NO_TITLE_BAR,  # can't use popup under a popup (bigger img)
            flags=ui.WINDOW_FLAGS_NO_TITLE_BAR,
        )
        with self._window.frame:
            with ui.VStack(spacing=8, style=self.__style):
                with ui.ZStack(height=ui.Percent(30)):
                    ui.Rectangle(name="MainFrame")
                    with ui.VStack():
                        ui.Spacer(height=10)
                        with ui.HStack():
                            ui.Spacer(width=10)
                            with ui.HStack(spacing=8):
                                with ui.VStack(width=ui.Percent(30)):
                                    ui.Spacer(height=2)
                                    with ui.Frame():
                                        self.__primary_thumnail = ui.Image("")
                                        self.__primary_thumnail.set_mouse_hovered_fn(
                                            functools.partial(self._on_image_hovered, self.__primary_thumnail)
                                        )
                                    ui.Spacer(height=2)
                                with ui.VStack(height=0, spacing=8, width=ui.Percent(70)):
                                    ui.Label("Name:")
                                    self.__string_field_name = ui.StringField(read_only=True)
                                    ui.Label("File Path:")
                                    self.__string_field_file_path = ui.StringField(read_only=True)
                                    ui.Label("Custom tags:")
                                    self.__string_field_custom_tags = ui.StringField(read_only=True)
                            ui.Spacer(width=10)
                        ui.Spacer(height=10)
                with ui.ZStack(height=ui.Percent(70)):
                    ui.Rectangle(name="MainFrame")
                    with ui.VStack():
                        ui.Spacer(height=10)
                        with ui.HStack():
                            ui.Spacer(width=10)
                            with ui.VStack(spacing=8):
                                with ui.HStack(height=ui.Pixel(22)):
                                    with ui.ZStack(width=20):
                                        ui.Rectangle(name="Search")
                                        ui.Image(str(self._get_icon_path("search")), name="Search")
                                    with ui.ZStack():
                                        self.__action_search_attr = ui.StringField()
                                        self.__action_search_attr.model.add_value_changed_fn(
                                            lambda m: self._filter_content()
                                        )
                                        with ui.HStack():
                                            ui.Spacer(width=8)
                                            self.__label_search = ui.Label("Search", name="Search")
                                    with ui.ZStack(width=20):
                                        ui.Rectangle(name="Search")
                                        self.__cross_image = ui.Image(
                                            str(self._get_icon_path("cross")),
                                            name="Cross",
                                            mouse_pressed_fn=lambda x, y, b, m: self._on_search_cross_clicked(),
                                            visible=False,
                                        )
                                with ui.ScrollingFrame(style_type_name_override="TreeView.ScrollingFrame"):
                                    self.__tree_view = ui.TreeView(  # noqa PLW0238
                                        self.__model,
                                        delegate=self.__delegate,
                                        root_visible=False,
                                        column_widths=[
                                            ui.Pixel(self.__model.SIZE_ADDITIONAL_THUMBNAIL + 10),
                                            ui.Fraction(3),
                                        ],
                                        header_visible=False,
                                        columns_resizable=True,
                                    )
                            ui.Spacer(width=10)
                        ui.Spacer(height=10)

        # build the ui from of the viewport for the drop
        self._dockspace_window = ui.Window("DockSpace")
        self._dockspace_window.detachable = False
        with self._dockspace_window.frame:
            with ui.VStack():
                frame = ui.Frame()
                frame.set_mouse_pressed_fn(self._on_mouse_clicked_fn)

    def _on_mouse_clicked_fn(self, x, y, b, m):
        """Hide everything"""
        self._window_bigger_image.visible = False
        self._window.visible = False

    def get_current_mouse_coords(self):
        """Get current mouse coords"""
        pos_x, pos_y = self._input.get_mouse_coords_pixel(self._mouse)
        return pos_x / self._dpi_scale, pos_y / self._dpi_scale

    def __create_bigger_image_ui(self):
        self._window_bigger_image = ui.Window(
            self.WINDOW_IMAGE_BIGGER_NAME,
            width=600,
            height=600,
            visible=False,
            flags=ui.WINDOW_FLAGS_POPUP | ui.WINDOW_FLAGS_NO_TITLE_BAR | ui.WINDOW_FLAGS_NO_RESIZE,
        )
        with self._window_bigger_image.frame:
            self.__bigger_image = ui.Image("")
            self.__bigger_image.set_mouse_hovered_fn(self.__on_bigger_image_hovered)

    def _on_image_hovered(self, image_widget, hovered):
        if not image_widget.source_url:
            return
        if (
            self.__cancel_mouse_hovered
            and self.__bigger_image.source_url == image_widget.source_url
            and hovered
            and self._window_bigger_image.visible
        ):
            return
        if hovered:
            self.__bigger_image.source_url = image_widget.source_url
            self._window_bigger_image.position_x = image_widget.screen_position_x + image_widget.computed_width + 10
            self._window_bigger_image.position_y = image_widget.screen_position_y
            self._window_bigger_image.visible = True
            self.__cancel_mouse_hovered = True
        else:
            self._window_bigger_image.visible = False
            self.__cancel_mouse_hovered = False

    def __on_bigger_image_hovered(self, hovered):
        self.__cancel_mouse_hovered = hovered
        if not hovered:
            self._window_bigger_image.visible = False

    def _filter_content(self):
        """Filter content by name"""
        filter_content_title_value = self.__action_search_attr.model.as_string
        self.__label_search.visible = not bool(filter_content_title_value)
        self.__cross_image.visible = bool(filter_content_title_value)
        self.__model.set_filter_str(filter_content_title_value)

    def _on_search_cross_clicked(self):
        """Called when the cross from the search box is clicked"""
        self.__action_search_attr.model.set_value("")
        self._filter_content()

    def _refresh(self, data: "ContentData"):
        self.__model.refresh_list()
        if data.image_primary_detail_fn is not None:
            primary_thumbnail = data.image_primary_detail_fn()
        else:
            primary_thumbnail = self._core.get_primary_thumbnails(data.path)
        if primary_thumbnail:
            self.__primary_thumnail.source_url = primary_thumbnail
        self.__string_field_custom_tags.model.set_value("To do, to do")  # TODO: add tags
        self.__string_field_file_path.model.set_value(data.path)
        self.__string_field_name.model.set_value(data.title)

    def show(self, data: "ContentData"):
        if self.__show_window_task:
            self.__show_window_task.cancel()
        self.__show_window_task = asyncio.ensure_future(self.__deferred_show(data))

    async def __deferred_show(self, data: "ContentData"):
        await omni.kit.app.get_app().next_update_async()  # wait 1 frame to appear after the dockspace mouse click
        self._refresh(data)
        self.__model.refresh_image_paths(data.path)
        x, y = self.get_current_mouse_coords()
        self._window.position_x = x
        self._window.position_y = y
        self._window.visible = True

    def hide(self):
        self._window.visible = False

    def destroy(self):
        self.__primary_thumnail = None
        self.__bigger_image = None
        self.__tree_view = None  # noqa PLW0238
        self.__string_field_custom_tags = None
        self.__string_field_file_path = None
        self.__string_field_name = None
        self.__action_search_attr = None
        self.__cross_image = None
        self.__label_search = None
        self.__show_window_task = None
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()  # noqa PLE1102
                del m_attr
                setattr(self, attr, value)
        self.__model = None
        self.__delegate = None
