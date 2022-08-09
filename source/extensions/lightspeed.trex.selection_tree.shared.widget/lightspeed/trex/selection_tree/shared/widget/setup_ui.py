"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import functools
import typing

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .selection_tree.delegate import Delegate as _Delegate
from .selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
from .selection_tree.model import ListModel as _ListModel

if typing.TYPE_CHECKING:
    from pxr import Usd


class SetupUI:

    DEFAULT_TREE_FRAME_HEIGHT = 200
    SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(self, context):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_manipulator_frame": None,
            "_tree_scroll_frame": None,
            "_tree_view": None,
            "_manip_frame": None,
            "_slide_placer": None,
            "_slider_manip": None,
            "_tree_model": None,
            "_tree_delegate": None,
            "_sub_tree_model_changed": None,
            "_sub_edit_path_reference": None,
            "_sub_delete_reference": None,
            "_sub_toggle_visibility": None,
            "_sub_frame_prim": None,
            "_sub_toggle_nickname": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = context  # can get the name of the context?
        self._tree_model = _ListModel(self._context)
        self._tree_delegate = _Delegate()

        self._sub_tree_model_changed = self._tree_model.subscribe_item_changed_fn(self._on_tree_model_changed)
        self._sub_edit_path_reference = self._tree_delegate.subscribe_edit_path_reference(self._on_edit_path_reference)
        self._sub_delete_reference = self._tree_delegate.subscribe_delete_reference(self._on_delete_reference)
        self._sub_toggle_visibility = self._tree_delegate.subscribe_toggle_visibility(self._on_toggle_visibility)
        self._sub_frame_prim = self._tree_delegate.subscribe_frame_prim(self._on_frame_prim)
        self._sub_toggle_nickname = self._tree_delegate.subscribe_toggle_nickname(self._on_toggle_nickname)

        self.__create_ui()

    def _on_edit_path_reference(self, prim: "Usd.Prim", path: str):
        print((prim, path))

    def _on_delete_reference(self, prim: "Usd.Prim", path: str):
        print((prim, path))

    def _on_toggle_visibility(self, prim: "Usd.Prim"):
        print(prim)

    def _on_frame_prim(self, prim: "Usd.Prim"):
        print(prim)

    def _on_toggle_nickname(self, prim: "Usd.Prim"):
        print(prim)

    def __create_ui(self):
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(8))
            self._manipulator_frame = ui.Frame(visible=True)
            with self._manipulator_frame:
                size_manipulator_height = 4
                with ui.ZStack():
                    with ui.VStack():
                        self._tree_scroll_frame = ui.ScrollingFrame(
                            name="PropertiesPaneSection",
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,  # noqa E501
                            height=ui.Pixel(self.DEFAULT_TREE_FRAME_HEIGHT),
                        )
                        with self._tree_scroll_frame:
                            self._tree_view = ui.TreeView(
                                self._tree_model,
                                delegate=self._tree_delegate,
                                root_visible=False,
                                header_visible=False,
                                columns_resizable=False,
                            )
                            self._tree_view.set_selection_changed_fn(self._on_tree_selection_changed)
                        self._tree_scroll_frame.set_build_fn(
                            functools.partial(
                                self._resize_tree_columns,
                                self._tree_view,
                                self._tree_scroll_frame,
                            )
                        )
                        self._tree_scroll_frame.set_computed_content_size_changed_fn(  # noqa E501
                            functools.partial(
                                self._resize_tree_columns,
                                self._tree_view,
                                self._tree_scroll_frame,
                            )
                        )
                        ui.Spacer(height=ui.Pixel(8))
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
                                    width=ui.Percent(self.SIZE_PERCENT_MANIPULATOR_WIDTH),
                                    name="PropertiesPaneSectionTreeManipulator",
                                )
        self._tree_model.refresh()

    def _on_tree_model_changed(self, _, __):
        self._tree_delegate.reset()
        asyncio.ensure_future(self._on_deferred_tree_model_changed())

    @omni.usd.handle_exception
    async def _on_deferred_tree_model_changed(self):
        await self.__deferred_expand()
        # set selection
        if not self._tree_model:
            return
        selection = [item for item in self._tree_model.get_item_children_type(_ItemInstanceMesh) if item.selected]
        self._tree_view.selection = selection
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()
        for item in selection:
            self._tree_delegate.refresh_gradient_color(item)

    def _on_tree_selection_changed(self, items):
        self._tree_delegate.on_item_selected(items, self._tree_model.get_all_items())

    @omni.usd.handle_exception
    async def __deferred_expand(self):
        def set_expanded(items):
            for item_ in items:
                self._tree_view.set_expanded(item_, True, True)

        if self._tree_view is None:
            return
        await omni.kit.app.get_app().next_update_async()
        if self._tree_model is None:
            return
        set_expanded(self._tree_model.get_item_children(None))
        return

    def _resize_tree_columns(self, tree_view, frame):
        tree_view.column_widths = [ui.Pixel(self._tree_scroll_frame.computed_width - 12)]

    def _on_slide_x_changed(self, x):
        size_manip = self._manip_frame.computed_width / 100 * self.SIZE_PERCENT_MANIPULATOR_WIDTH
        if x.value < 0:
            self._slide_placer.offset_x = 0
        elif x.value > self._manip_frame.computed_width - size_manip:
            self._slide_placer.offset_x = self._manip_frame.computed_width - size_manip

        item_path_scroll_frames = self._tree_delegate.get_path_scroll_frames()
        if item_path_scroll_frames:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / (self._manip_frame.computed_width - size_manip)) * x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value

    def _on_slide_y_changed(self, size_manip, y):
        if y.value < 0:
            self._slide_placer.offset_y = 0
        self._tree_scroll_frame.height = ui.Pixel(self.DEFAULT_TREE_FRAME_HEIGHT + y.value)

    def destroy(self):
        _reset_default_attrs(self)
