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
from typing import Callable

import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.utils.common.dialog_utils import add_dialog as _add_dialog
from pxr import Sdf, Usd

from .categories_tree.delegate import Delegate as _Delegate
from .categories_tree.model import Model as _Model


class RemixCategoriesDialog:

    _VERTICAL_WIDGET_PADDING = 8
    _HORIZON_WIDGET_PADDING = 8
    _CATEGORIES_WIDGET_WIDTH = 420
    _SCROLLING_FRAME_BUFFER = 152
    _RECTANGLE_WIDGET_WIDTH = 356
    _RECTANGLE_BUFFER = 4
    _TITLE_HEIGHT = 68
    _WIDGET_WIDTH = 352
    _WIDGET_PADDING = 8
    _WINDOW_WIDTH = 364
    _WINDOW_HEIGHT = 588
    _BUTTON_PADDING = 12
    _BUTTON_WIDTH = 84
    _BUTTON_HEIGHT = 24
    _ICON_DIMENSIONS = 16
    _BACKGROUND_HEIGHT = 556
    _BACKGROUND_WIDTH = 356

    def __init__(self, context_name: str = None, refresh_func: Callable[["Usd.Prim"], None] = None):
        self._expanded_items = {}
        self._context = omni.usd.get_context(context_name)
        self._stage = self._context.get_stage()
        self._core = _AssetReplacementsCore(context_name)
        self._categories_model = _Model()
        self._categories_delegate = _Delegate()
        for name, attr_details in constants.REMIX_CATEGORIES.items():
            self._categories_model.add_item(
                name,
                description=attr_details["full_description"],
                tooltip=attr_details["tooltip"],
                attribute=attr_details["attr"],
            )
        self._refresh_func = refresh_func

        self._build_ui()

    def close(self):
        self._window.visible = False

    def show(self):
        self._window.visible = True

    def _build_ui(self):
        window_height = ui.Workspace.get_main_window_height()
        dialog_height = window_height / 1.5
        # To make the window a little more dynamic, make sure that the size is less than
        # the main window's height.
        final_height = int(dialog_height if dialog_height < 500 else self._WINDOW_HEIGHT)
        self._window = ui.Window(
            "Add Remix Categories to Prim",
            visible=True,
            width=self._WINDOW_WIDTH,
            height=final_height,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_SCROLLBAR
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE
                | ui.WINDOW_FLAGS_NO_COLLAPSE
            ),
        )
        _add_dialog(self._window)

        # Grab any previously set category values
        prim_paths = self._core.get_selected_prim_paths()
        mesh_prims = self._core.get_corresponding_prototype_prims(
            [self._stage.GetPrimAtPath(path) for path in prim_paths]
        )
        values = {}
        for prim_path in mesh_prims:
            prim = self._stage.GetPrimAtPath(prim_path)
            for attr in prim.GetAttributes():
                attr_name = attr.GetName()
                check = [
                    attr_details["attr"]
                    for _, attr_details in constants.REMIX_CATEGORIES.items()
                    if attr_details["attr"] == attr_name
                ]
                if check:
                    values[check[0]] = attr.Get()

        for item in self._categories_model.get_item_children(None):
            item.value = values.get(item.attribute, "") or False

        # Build dialog. Not all categories are visible in the viewport, so give the users a warning
        with self._window.frame:
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground", width=self._BACKGROUND_WIDTH, height=self._BACKGROUND_HEIGHT)
                with ui.VStack(spacing=ui.Pixel(self._VERTICAL_WIDGET_PADDING), height=ui.Pixel(final_height)):
                    with ui.VStack(
                        height=ui.Pixel(self._TITLE_HEIGHT),
                        spacing=ui.Pixel(self._VERTICAL_WIDGET_PADDING),
                        width=ui.Pixel(self._WIDGET_WIDTH),
                    ):
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(self._RECTANGLE_BUFFER))
                            categories_desc = (
                                "Remix Categories describe how the RTX Renderer treats "
                                "the geometry or its associated texture during runtime."
                            )
                            ui.Label(categories_desc, word_wrap=True)

                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(self._RECTANGLE_BUFFER))
                            ui.Label(
                                "Note that some effects only appear in game and not the Toolkit Viewport!",
                                name="PropertiesPaneSectionTitle",
                                word_wrap=True,
                            )
                    with ui.ZStack():
                        with ui.HStack(width=ui.Pixel(self._RECTANGLE_WIDGET_WIDTH)):
                            ui.Spacer(width=ui.Pixel(self._RECTANGLE_BUFFER))
                            ui.Rectangle(name="TreePanelBackground")
                            ui.Spacer(width=ui.Pixel(self._RECTANGLE_BUFFER))
                        with ui.ScrollingFrame(
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                            height=final_height - self._SCROLLING_FRAME_BUFFER,
                            width=ui.Pixel(self._CATEGORIES_WIDGET_WIDTH),
                            style_type_name_override="TreeView",
                            scroll_x_max=0,
                        ):
                            self._categories_tree = ui.TreeView(
                                self._categories_model,
                                delegate=self._categories_delegate,
                                root_visible=False,
                                drop_between_items=True,
                            )
                            self._categories_tree.set_selection_changed_fn(self._categories_model.set_items_selected)
                    with ui.HStack(spacing=ui.Pixel(self._WIDGET_PADDING), width=self._WIDGET_WIDTH):
                        ui.Spacer()
                        ui.Button(
                            text="Assign",
                            clicked_fn=functools.partial(self._assign_remix_category, values),
                            height=ui.Pixel(self._BUTTON_HEIGHT),
                            width=ui.Pixel(self._BUTTON_WIDTH),
                            identifier="AssignCategoryButton",
                        )
                        ui.Button(
                            "Cancel",
                            clicked_fn=self.close,
                            height=ui.Pixel(self._BUTTON_HEIGHT),
                            width=ui.Pixel(self._BUTTON_WIDTH),
                            identifier="CancelButton",
                        )
                        ui.Spacer()

    def _assign_remix_category(self, prev_values: dict) -> None:
        """Assigning the remix category value."""
        paths = self._core.get_selected_prim_paths()
        meshes = self._core.get_corresponding_prototype_prims([self._stage.GetPrimAtPath(path) for path in paths])
        checkboxes = self._categories_delegate.get_all_checkboxes()
        with omni.kit.undo.group():
            for name, box in checkboxes.items():
                category = box.model.get_value_as_bool()
                prev_value = prev_values.get(name, False)
                if category and not prev_value:
                    self._core.add_attribute(meshes, name, 1, prev_value, Sdf.ValueTypeNames.Bool)
                elif not category and prev_value:
                    self._core.add_attribute(meshes, name, 0, prev_value, Sdf.ValueTypeNames.Bool)

        self.close()
        self._refresh_func([self._stage.GetPrimAtPath(meshes[0])])
