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
import re
import typing
from typing import Any, Callable, List, Union

import carb
import omni.kit.app
import omni.kit.commands
import omni.kit.undo
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.asset_replacements.core.shared.usd_copier import copy_usd_asset as _copy_usd_asset
from lightspeed.trex.utils.common.file_utils import (
    is_usd_file_path_valid_for_filepicker as _is_usd_file_path_valid_for_filepicker,
)
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni.flux.light_creator.widget import LightCreatorWidget as _LightCreatorWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.widget.hover import hover_helper as _hover_helper

from .selection_tree.delegate import Delegate as _Delegate
from .selection_tree.model import ItemAddNewLiveLight as _ItemAddNewLiveLight
from .selection_tree.model import ItemAddNewReferenceFileMesh as _ItemAddNewReferenceFileMesh
from .selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
from .selection_tree.model import ItemInstancesMeshGroup as _ItemInstancesMeshGroup
from .selection_tree.model import ItemLiveLightGroup as _ItemLiveLightGroup
from .selection_tree.model import ItemMesh as _ItemMesh
from .selection_tree.model import ItemPrim as _ItemPrim
from .selection_tree.model import ItemReferenceFileMesh as _ItemReferenceFileMesh
from .selection_tree.model import ListModel as _ListModel

if typing.TYPE_CHECKING:
    from pxr import Sdf, Usd


class SetupUI:
    DEFAULT_TREE_FRAME_HEIGHT = 200
    SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(self, context_name):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_manipulator_frame": None,
            "_tree_scroll_frame": None,
            "_tree_view": None,
            "_manip_frame": None,
            "_frame_none": None,
            "_slide_placer": None,
            "_slider_manip": None,
            "_tree_model": None,
            "_core": None,
            "_tree_delegate": None,
            "_sub_tree_model_changed": None,
            "_sub_edit_path_reference": None,
            "_previous_tree_selection": None,
            "_instance_selection": None,
            "_previous_instance_selection": None,
            "_current_tree_pressed_input": None,
            "_sub_tree_delegate_delete_ref": None,
            "_sub_tree_delegate_duplicate_ref": None,
            "_sub_tree_delegate_reset_ref": None,
            "_sub_tree_delegate_delete_prim": None,
            "_light_creator_window": None,
            "_light_creator_widget": None,
            "_fake_frame_for_scroll": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._core = _AssetReplacementsCore(context_name)
        self._tree_model = _ListModel(context_name)
        self._tree_delegate = _Delegate()

        self.__on_deferred_tree_model_changed_tack = None

        self._ignore_tree_selection_changed = False
        self._ignore_select_instance_prim_from_selected_items = False
        self._previous_tree_selection = []
        self._instance_selection = []
        self._previous_instance_selection = []

        self._current_tree_pressed_input = None

        self._sub_tree_model_changed = self._tree_model.subscribe_item_changed_fn(self._on_tree_model_changed)
        self._sub_tree_delegate_delete_ref = self._tree_delegate.subscribe_delete_reference(self._on_delete_reference)
        self._sub_tree_delegate_delete_prim = self._tree_delegate.subscribe_delete_prim(self._on_delete_prim)
        self._sub_tree_delegate_duplicate_ref = self._tree_delegate.subscribe_duplicate_reference(
            self._on_duplicate_reference
        )
        self._sub_tree_delegate_duplicate_prim = self._tree_delegate.subscribe_duplicate_prim(self._on_duplicate_prim)
        self._sub_tree_delegate_reset_ref = self._tree_delegate.subscribe_reset_released(self._on_reset_asset)

        self.__on_tree_model_emptied = _Event()
        self.__create_ui()

        self.__on_tree_selection_changed = _Event()
        self.__on_go_to_ingest_tab = _Event()

    def _go_to_ingest_tab(self):
        """Call the event object that has the list of functions"""
        self.__on_go_to_ingest_tab()

    def subscribe_go_to_ingest_tab(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_go_to_ingest_tab, func)

    def _tree_selection_changed(
        self,
        items: List[
            Union[
                _ItemMesh,
                _ItemReferenceFileMesh,
                _ItemAddNewReferenceFileMesh,
                _ItemAddNewLiveLight,
                _ItemInstancesMeshGroup,
                _ItemInstanceMesh,
            ]
        ],
    ):
        """Call the event object that has the list of functions"""
        if self.__on_tree_selection_changed is not None:
            self.__on_tree_selection_changed(items)

    def subscribe_tree_selection_changed(
        self,
        function: Callable[
            [
                List[
                    Union[
                        _ItemMesh,
                        _ItemReferenceFileMesh,
                        _ItemAddNewReferenceFileMesh,
                        _ItemAddNewLiveLight,
                        _ItemInstancesMeshGroup,
                        _ItemInstanceMesh,
                    ]
                ]
            ],
            Any,
        ],
    ):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_tree_selection_changed, function)

    def subscribe_tree_model_emptied(self, function: Callable[[], Any] = None):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_tree_model_emptied, function)

    def subscribe_delete_reference(self, function: Callable[["Usd.Prim", str], None]):
        return self._tree_delegate.subscribe_delete_reference(function)

    def subscribe_frame_prim(self, function: Callable[["Usd.Prim"], None]):
        return self._tree_delegate.subscribe_frame_prim(function)

    def subscribe_reset_released(self, function: Callable[["Usd.Prim"], None]):
        return self._tree_delegate.subscribe_reset_released(function)

    def __create_ui(self):
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(8))
            self._manipulator_frame = ui.Frame(visible=True)
            with self._manipulator_frame:
                size_manipulator_height = 4
                with ui.ZStack():
                    self._frame_none = ui.Frame(visible=True, identifier="frame_none")
                    with self._frame_none:
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                                ui.Spacer(height=0)
                                with ui.VStack(width=0):
                                    ui.Spacer()
                                    ui.Label("None", name="PropertiesWidgetLabel")
                                    ui.Spacer()
                                ui.Spacer(height=0)
                    with ui.VStack():
                        self._tree_scroll_frame = ui.ScrollingFrame(
                            name="PropertiesPaneSection",
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,  # noqa E501
                            height=ui.Pixel(self.DEFAULT_TREE_FRAME_HEIGHT),
                            identifier="TreeSelectionScrollFrame",
                        )
                        with self._tree_scroll_frame:
                            with ui.ZStack():
                                self._tree_view = ui.TreeView(
                                    self._tree_model,
                                    delegate=self._tree_delegate,
                                    root_visible=False,
                                    header_visible=False,
                                    columns_resizable=False,
                                    style_type_name_override="TreeView.Selection",
                                    identifier="LiveSelectionTreeView",
                                )
                                self._tree_view.set_mouse_pressed_fn(self._obtain_tree_pressed_input)
                                self._tree_view.set_selection_changed_fn(self._on_tree_selection_changed)

                                self._fake_frame_for_scroll = ui.Frame()

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
                                identifier="placer_scroll",
                            )
                            # Body
                            with self._slide_placer:
                                self._slider_manip = ui.Rectangle(
                                    width=ui.Percent(self.SIZE_PERCENT_MANIPULATOR_WIDTH),
                                    name="PropertiesPaneSectionTreeManipulator",
                                )
                                _hover_helper(self._slider_manip)
        self.refresh()

    def _obtain_tree_pressed_input(self, x, y, b, m):
        self._current_tree_pressed_input = {"x_pos": x, "y_pos": y, "button": b, "modifier": m}

    def refresh(self):
        self._tree_model.refresh()

    def _on_reset_asset(self, prim_path: "Sdf.Path"):
        self._core.remove_prim_overrides(prim_path)

    def _on_duplicate_reference(self, item: _ItemReferenceFileMesh):
        abs_path = omni.client.normalize_url(item.layer.ComputeAbsolutePath(item.path))
        self._add_new_ref_mesh(item, abs_path)

    def _on_duplicate_prim(self, item: _ItemPrim):
        omni.kit.commands.execute(
            "CopyPrimCommand",
            path_from=item.path,
            usd_context_name=self._context_name,
        )

    def _on_delete_prim(self, item: _ItemPrim):
        def _get_parent_item_mesh(_item):
            if not hasattr(_item, "parent") or not _item.parent:
                return None
            if isinstance(_item.parent, (_ItemMesh, _ItemPrim)):
                return _item.parent
            if isinstance(_item.parent, _ItemLiveLightGroup):
                lights = _item.parent.lights
                if lights:
                    remaining_lights = [light for light in lights if light != item]
                    if remaining_lights:
                        return remaining_lights[0]
            return _get_parent_item_mesh(_item.parent)

        def _get_parent_root_item_mesh(_item):
            if not hasattr(_item, "parent") or not _item.parent:
                return None
            if isinstance(_item.parent, _ItemMesh):
                return _item.parent
            return _get_parent_root_item_mesh(_item.parent)

        # select the previous selection. If nothing was selected, select the parent of the item.
        previous_selected_item_prims = [
            _item for _item in self._previous_tree_selection if isinstance(_item, _ItemPrim) and _item.path != item.path
        ]
        if previous_selected_item_prims:
            item_meshes = previous_selected_item_prims
        else:
            item_meshes = [_get_parent_item_mesh(item)]

        to_select_path_str = []

        if item_meshes:
            # we select the instance, not the mesh
            previous_selected_item_instances = [
                _item for _item in self._previous_instance_selection if isinstance(_item, _ItemInstanceMesh)
            ]
            if previous_selected_item_instances:
                to_select_path_str = self._core.get_instance_from_mesh(
                    [item_mesh.path for item_mesh in item_meshes],
                    [
                        previous_selected_item_instance.path
                        for previous_selected_item_instance in previous_selected_item_instances
                    ],
                )
            else:  # no instance selected? We grab the first one
                instances = _get_parent_root_item_mesh(item).instance_group_item.instances
                if instances:
                    to_select_path_str = self._core.get_instance_from_mesh(
                        [item_mesh.path for item_mesh in item_meshes], [instances[0].path]
                    )

        with omni.kit.undo.group(), self._tree_model.refresh_only_at_the_end():
            self._core.delete_prim([item.path])

            stage = self._context.get_stage()
            to_select = []
            for path_str in to_select_path_str:
                prim = stage.GetPrimAtPath(path_str)
                if not prim.IsValid():
                    continue
                to_select.append(path_str)

            if self._core.get_selected_prim_paths() == to_select:
                # we force the refresh of the tree
                self.refresh()
            else:
                self._core.select_prim_paths(to_select)

    def _on_delete_reference(self, item: _ItemReferenceFileMesh):
        stage = self._context.get_stage()

        # save the current selection
        to_select = []
        previous_mesh_item = item.parent
        previous_selected_instance_items = [
            _item for _item in self._previous_instance_selection if isinstance(_item, _ItemInstanceMesh)
        ]
        previous_selected_prim_items = [
            _item
            for _item in self._previous_tree_selection
            if isinstance(_item, _ItemPrim)
            and (
                (
                    _item.reference_item is not None
                    and hasattr(_item.reference_item, "parent")
                    and _item.reference_item.parent == item.parent
                    and _item.reference_item != item
                )
                or (_item.from_live_light_group and _item.is_usd_light)
            )
        ]
        previous_selection = self._core.get_selected_prim_paths()

        # select the first prim of the previous mesh from the first ref
        if len(previous_selected_prim_items) < 1:
            parent = item.parent
            for mesh_item in parent.reference_items:
                if mesh_item == item:
                    continue
                if mesh_item.child_prim_items:
                    prims = self._core.get_prim_from_ref_items(
                        [mesh_item], previous_selected_instance_items, only_xformable=True, level=1, skip_remix_ref=True
                    )
                    if prims:
                        for prim in prims:
                            to_select.append(str(prim.GetPath()))
                        break

        # if we dont have any prims anymore, we select the previous instance
        if not to_select and previous_selected_instance_items:
            to_select = [previous_selected_instance_items[0].path]

        # if we dont have selected instance, we select the previous mesh
        if not to_select:
            to_select = [previous_mesh_item.path]

        with omni.kit.undo.group(), self._tree_model.refresh_only_at_the_end():
            current_selection = self._core.get_selected_prim_paths()

            to_select = [prim_path for prim_path in to_select if stage.GetPrimAtPath(prim_path).IsValid()]
            if to_select:
                # take only the first one
                to_select = [to_select[0]]

            for prim_path in previous_selection:
                prim = stage.GetPrimAtPath(prim_path)
                if not prim.IsValid():
                    continue
                to_select.append(prim_path)

            # if there is nothing to select, we select the instance itself
            if not to_select:
                if previous_selected_instance_items:
                    to_select.append(previous_selected_instance_items[0].path)
                else:
                    to_select.append(item.parent.path)
            self._core.select_prim_paths(to_select, current_selection=current_selection)
            self._core.remove_reference(stage, item.prim.GetPath(), item.ref, item.layer)

    def _on_tree_model_changed(self, model, __):
        self._tree_delegate.reset()
        if self.__on_deferred_tree_model_changed_tack:
            self.__on_deferred_tree_model_changed_tack.cancel()
        self.__on_deferred_tree_model_changed_tack = asyncio.ensure_future(self._on_deferred_tree_model_changed())

        self._frame_none.visible = False
        if not model.get_all_items() and self.__on_tree_model_emptied is not None:
            self._frame_none.visible = True
            self.__on_tree_model_emptied(model)

    @omni.usd.handle_exception
    async def _on_deferred_tree_model_changed(self):
        # set selection
        if not self._tree_model:
            return
        stage_selection = self._context.get_selection().get_selected_prim_paths()

        selection = []
        all_items_by_types = self._tree_model.get_all_items_by_type()

        # select the item prim
        prototypes_stage_selected_paths = self._core.get_corresponding_prototype_prims_from_path(stage_selection)
        item_prims = all_items_by_types.get(_ItemPrim, [])
        item_group_instances = all_items_by_types.get(_ItemInstancesMeshGroup, [])
        for item in item_prims:
            if item.path in prototypes_stage_selected_paths:
                selection.append(item)

        # we select the instance in the tree
        for item in all_items_by_types.get(_ItemInstanceMesh, []):
            if item in selection:
                continue
            for stage_selection_path in stage_selection:
                if stage_selection_path.startswith(item.path) and item not in selection:
                    selection.append(item)

        # if this is a light, there is no instance/prototype
        regex_sub_light_pattern = re.compile(constants.REGEX_SUB_LIGHT_PATH)
        regex_light_pattern = re.compile(constants.REGEX_LIGHT_PATH)
        for stage_selection_path in stage_selection:
            if regex_sub_light_pattern.match(stage_selection_path):
                for item in item_prims:
                    if item.path == stage_selection_path:
                        selection.append(item)
            # but if this is a light, we select the group instance because a light doesn't have instances
            if regex_light_pattern.match(stage_selection_path):
                selection.extend(item_group_instances)

        if self._previous_tree_selection:
            current_ref_mesh_file = all_items_by_types.get(_ItemReferenceFileMesh, [])
            # we remove instance because they are base on stage selection
            ref_file_mesh_items = []
            # if the last selection if a prim, we don't select the previous ref
            to_add = True
            if selection and isinstance(selection[-1], _ItemPrim):
                to_add = False
            if to_add:
                for item in self._previous_tree_selection:
                    # we grab all reference file mesh
                    if isinstance(item, _ItemReferenceFileMesh):
                        ref_file_mesh_items.append(item)
            # if the size of ref is the same, we select the previous ref
            if ref_file_mesh_items and current_ref_mesh_file:  # noqa SIM102
                # same len ref as before, so we grab the previous selected index
                if (
                    len(current_ref_mesh_file) == ref_file_mesh_items[0].size_ref_index
                    and current_ref_mesh_file[0].prim == ref_file_mesh_items[0].prim
                ):
                    for ref_file_mesh_item in ref_file_mesh_items:
                        selection.append(current_ref_mesh_file[ref_file_mesh_item.ref_index])

        # we select the corresponding prim instance
        self._ignore_select_instance_prim_from_selected_items = True
        # we remove duplicated but keep the order
        selection = list(dict.fromkeys(selection))

        all_visible_items = await self.__deferred_expand(selection)
        if self._tree_view is not None:
            self._tree_view.selection = selection
            first_item_prim = sorted([item for item in selection if isinstance(item, _ItemPrim)], key=lambda x: x.path)
            if first_item_prim:
                await self.scroll_to_item(first_item_prim[0], all_visible_items)
        self._previous_tree_selection = selection
        # no need to call it because we change the selection, _on_tree_selection_changed() will call it
        # self._tree_selection_changed(selection)
        self._ignore_select_instance_prim_from_selected_items = False
        # for _ in range(2):
        #     await omni.kit.app.get_app().next_update_async()
        self.__refresh_delegate_gradients()

    @omni.usd.handle_exception
    async def scroll_to_item(self, item, all_visible_items):
        idx_item = all_visible_items.index(item)
        self._fake_frame_for_scroll.clear()
        with self._fake_frame_for_scroll:
            with ui.VStack():
                ui.Spacer(height=idx_item * self._tree_delegate.DEFAULT_IMAGE_ICON_SIZE)
                ui.Spacer(height=1)  # or bug
                ui.Spacer(height=self._tree_delegate.DEFAULT_IMAGE_ICON_SIZE)
                fake_spacer_for_scroll = ui.Spacer(height=self._tree_delegate.DEFAULT_IMAGE_ICON_SIZE)
                ui.Spacer()

        fake_spacer_for_scroll.scroll_here_y(0.5)

    def __refresh_delegate_gradients(self):
        for item in self._tree_view.selection if self._tree_view is not None else []:
            if not self._tree_delegate:
                return
            self._tree_delegate.refresh_gradient_color(item)

    def get_selection(self):
        """Return the selection consisting of both the primary and secondary (instance) selections."""
        if self._tree_view is None:
            return []

        # if there is a primary selection, add the secondary selection; otherwise just use the secondary
        if self._tree_view.selection:
            # combine primary + secondary selections and exclude the instance group
            selection_without_instance_group = [
                item
                for item in self._tree_view.selection + self._instance_selection
                if not isinstance(item, _ItemInstancesMeshGroup)
            ]
            return selection_without_instance_group
        return self._instance_selection

    def get_instance_selection(self, include_instance_group: bool = False):
        """Return the instances from within the secondary selection. Do not include instance groups by default."""
        if self._tree_view is None or self._frame_none.visible:
            return []

        if include_instance_group:
            return self._instance_selection
        return [item for item in self._instance_selection if isinstance(item, _ItemInstanceMesh)]

    @_ignore_function_decorator(attrs=["_ignore_tree_selection_changed"])
    def _on_tree_selection_changed(self, items):
        # if the clicked item was an instance, we must handle selection differently for secondary selections
        clicked_instance_items = [item for item in items if isinstance(item, _ItemInstanceMesh)]
        item_meshes = self._tree_model.get_all_items_by_type().get(_ItemMesh, [])
        unrelated_instance_selections = []

        if clicked_instance_items and self._current_tree_pressed_input:
            # if there are multiple top-level item meshes, save the unrelated instance selections to re-select later
            if len(item_meshes) > 1:
                # find out which ItemMesh section was selected
                item_mesh_section_index = 0
                for index, item_mesh in enumerate(item_meshes):
                    if self._get_hash(clicked_instance_items[0]) == self._get_hash(item_mesh):
                        item_mesh_section_index = index
                        break

                # save the previous instance selections if they are not related to the selected ItemMesh section
                for previous_instance in self._previous_instance_selection:
                    if isinstance(previous_instance, _ItemInstanceMesh) and self._get_hash(
                        previous_instance
                    ) != self._get_hash(item_meshes[item_mesh_section_index]):
                        unrelated_instance_selections.append(previous_instance)

            # handle modifier selections
            if self._current_tree_pressed_input["modifier"] == 1:  # shift was pressed
                # if only one ItemMesh section, manually shift select, otherwise ignore
                if len(item_meshes) == 1:
                    # manually create a shift multi-selection between the start and end instance selections
                    all_instance_items = self._tree_model.get_all_items_by_type().get(_ItemInstanceMesh, [])
                    selection_start_index = all_instance_items.index(self._previous_instance_selection[0])
                    selection_end_index = all_instance_items.index(clicked_instance_items[-1])

                    if selection_start_index > selection_end_index:
                        selection_start_index, selection_end_index = selection_end_index, selection_start_index
                    items = all_instance_items[selection_start_index : selection_end_index + 1]  # noqa: E203
                else:
                    # TODO: Find a way to get shift selection to work when multiple ItemMesh sections are open
                    #       - `items` is invalid if multiple ItemMesh selections and shift is clicked
                    # ignore the shift selection since shift conceals clicked_instance_items; this is a limitation
                    items = self._previous_instance_selection
            elif self._current_tree_pressed_input["modifier"] == 2:  # ctrl pressed
                # manually add the previous instance selection item(s) to the current
                items += self._previous_instance_selection
        else:
            # if non-instance item selected, add the instance items back since they were excluded during last iteration
            items += self._previous_instance_selection

        # if there were multiple ItemMesh in the tree, add the unrelated previous instance selections back
        if unrelated_instance_selections:
            items += list(set(unrelated_instance_selections))

        # reset the tree pressed input; this prevents outdated input after selection change from viewport
        if self._current_tree_pressed_input is not None:
            self._current_tree_pressed_input = {"x_pos": 0.0, "y_pos": 0.0, "button": 0, "modifier": 0}

        # now move the instance items from the "items" list to the "_instance_selection" list
        # from now on, items will correlate with primary selections and _instance_selection with secondary selections
        self._instance_selection = []
        for item in items:
            if isinstance(item, _ItemInstancesMeshGroup):
                # if a group was selected, add the instances of the group and the group item itself
                for instance in item.instances:
                    self._instance_selection.append(instance)
                self._instance_selection.append(item)
            elif isinstance(item, _ItemInstanceMesh):
                # just add the individual instance item otherwise
                self._instance_selection.append(item)

        # remove any duplicate instances
        self._instance_selection = list(set(self._instance_selection))

        # remove all instance items/groups now that the separate instance list exists
        items = [item for item in items if not isinstance(item, (_ItemInstanceMesh, _ItemInstancesMeshGroup))]

        # we can't select the top mesh item, so also exclude this
        items = [item for item in items if not isinstance(item, _ItemMesh)]

        # grab the add mesh/add light item buttons if they were clicked
        add_item_selected = [item for item in items if isinstance(item, _ItemAddNewReferenceFileMesh)]
        add_light_selected = [item for item in items if isinstance(item, _ItemAddNewLiveLight)]

        # grab all current prims
        all_items_by_types = self._tree_model.get_all_items_by_type()
        prim_items = all_items_by_types.get(_ItemPrim, [])

        # if one of the add mesh/add light item buttons items were clicked
        if add_item_selected or add_light_selected:
            # clear the selection since we don't actually want the buttons to be selected
            items = []

            # add prims back if add item or light selected - they are needed to prevent empty tree upon return
            for item in self._previous_tree_selection:
                if isinstance(item, _ItemPrim):
                    for item_prim in prim_items:
                        if item_prim.prim == item.prim:
                            items.append(item_prim)
                            break

        # if the add light is clicked, we deselect all others things but not live light prims
        if add_light_selected:
            items.extend(
                list(
                    {
                        item
                        for item in self._previous_tree_selection
                        if isinstance(item, _ItemPrim) and item.from_live_light_group
                    }
                )
            )

        # if we select an instance, and a prim is selected, we keep the prim selected
        item_instance_meshes = [item for item in self._instance_selection if isinstance(item, _ItemInstanceMesh)]
        item_instance_mesh_lights = [item for item in item_instance_meshes if item.parent.parent.is_light()]
        if len(items) == 0 and len(item_instance_meshes) > 0 and len(item_instance_mesh_lights) == 0:
            for item in self._previous_tree_selection:
                if isinstance(item, _ItemPrim):
                    for item_prim in prim_items:
                        if item_prim.prim == item.prim:
                            items.append(item_prim)
                            break

        # only item instance and item prim can be multiple selected
        if len(items) > 1:
            # grab all type
            all_item_types = {type(item) for item in items}
            if _ItemInstanceMesh in all_item_types:
                all_item_types.remove(_ItemInstanceMesh)
            if _ItemPrim in all_item_types:
                all_item_types.remove(_ItemPrim)
            # if we have more than 1 type, only the last one can be taken
            if len(all_item_types) > 1:
                result = []
                last_other_item = None
                for item in items:
                    # we keep prim and instance items
                    if isinstance(item, _ItemPrim):
                        result.append(item)
                        continue
                    if isinstance(item, _ItemInstanceMesh):
                        self._instance_selection.append(item)
                        continue
                    last_other_item = item
                # now we add the other item
                if last_other_item:
                    result.append(last_other_item)
                items = result

        # if all instances are selected within an instance group, select the instance group item itself
        all_item_instance_groups = all_items_by_types.get(_ItemInstancesMeshGroup, [])
        for instance_group in all_item_instance_groups:
            if all(instance in self._instance_selection for instance in instance_group.instances):
                self._instance_selection.append(instance_group)

        # if no instances are selected, just select the first available
        all_instance_meshes = self._tree_model.get_all_items_by_type().get(_ItemInstanceMesh, [])
        if not self._instance_selection and all_instance_meshes:
            self._instance_selection.append(all_instance_meshes[0])

        # add the items to the tree
        if self._tree_view is not None:
            self._tree_view.selection = items
        if not self._ignore_select_instance_prim_from_selected_items:
            # select prims when item prims are clicked
            # we swap all the item prim path with the current selected item instances
            prim_paths = [str(item.prim.GetPath()) for item in items if isinstance(item, _ItemPrim)]
            to_select_paths = []
            for path in prim_paths:
                for instance_item in self._instance_selection:
                    if not isinstance(instance_item, _ItemInstancesMeshGroup):
                        to_select_path = re.sub(
                            constants.REGEX_MESH_TO_INSTANCE_SUB, str(instance_item.prim.GetPath()), path
                        )
                        to_select_paths.append(to_select_path)

            self._tree_model.select_prim_paths(list(set(to_select_paths)))
        self._previous_tree_selection = list(set(items))
        self._previous_instance_selection = list(set(self._instance_selection))
        self._tree_delegate.on_item_selected(items, self._instance_selection, self._tree_model.get_all_items())

        # if add item was clicked, we open the ref picker
        if add_item_selected:
            _open_file_picker(
                "Select a reference file",
                functools.partial(self._add_new_unique_ref_mesh, add_item_selected[0]),
                lambda *args: None,
                file_extension_options=constants.READ_USD_FILE_EXTENSIONS_OPTIONS,
                validate_selection=_is_usd_file_path_valid_for_filepicker,
                validation_failed_callback=self.__show_error_not_usd_file,
            )
        elif add_light_selected:  # if add light was clicked
            self.__show_light_creator_window(add_light_selected[0], items)

        self._tree_selection_changed(items + self._instance_selection)

    def __show_error_not_usd_file(self, dirname: str, filename: str):
        _TrexMessageDialog(
            message=f"{dirname}/{filename} is not a USD file",
            disable_cancel_button=True,
        )

    def __show_light_creator_window(
        self,
        add_item: _ItemAddNewLiveLight,
        selected_items: List[
            Union[
                _ItemMesh,
                _ItemReferenceFileMesh,
                _ItemAddNewReferenceFileMesh,
                _ItemAddNewLiveLight,
                _ItemInstancesMeshGroup,
                _ItemInstanceMesh,
            ]
        ],
    ):
        async def _deferred_hide():
            await omni.kit.app.get_app().next_update_async()
            if self._light_creator_window:
                self._light_creator_window.frame.clear()
                self._light_creator_window.visible = False

        def _hide(light_path: str):
            asyncio.ensure_future(_deferred_hide())
            # we select the light from the instance, not the mesh!
            instances = [item for item in self._instance_selection if isinstance(item, _ItemInstanceMesh)]
            if instances:
                self._core.select_prim_paths(self._core.get_instance_from_mesh([light_path], [instances[0].path]))
            else:  # no instance selected? We grab the first one
                instances = add_item.parent.instance_group_item.instances
                if instances:
                    self._core.select_prim_paths(self._core.get_instance_from_mesh([light_path], [instances[0].path]))

        self._light_creator_window = ui.Window(
            "Light creator",
            visible=True,
            width=400,
            height=100,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_SCROLLBAR
                | ui.WINDOW_FLAGS_MODAL
            ),
        )

        under_path = add_item.parent.path
        with self._light_creator_window.frame:
            self._light_creator_widget = _LightCreatorWidget(
                self._context_name, create_under_path=under_path, callback=_hide
            )

    def __ignore_warning_ingest_asset(
        self, add_reference_item: Union[_ItemAddNewReferenceFileMesh, _ItemReferenceFileMesh], asset_path: str
    ):
        self._add_new_ref_mesh(add_reference_item, asset_path)

    def _add_new_unique_ref_mesh(
        self, add_reference_item: Union[_ItemAddNewReferenceFileMesh, _ItemReferenceFileMesh], asset_path: str
    ):
        if not self._core.was_the_asset_ingested(asset_path):
            layer = self._context.get_stage().GetEditTarget().GetLayer()
            ingest_enabled = bool(
                omni.kit.app.get_app()
                .get_extension_manager()
                .get_enabled_extension_id("lightspeed.trex.control.ingestcraft")
            )
            _TrexMessageDialog(
                title=constants.ASSET_NEED_INGEST_WINDOW_TITLE,
                message=constants.ASSET_NEED_INGEST_MESSAGE,
                ok_handler=functools.partial(self.__ignore_warning_ingest_asset, add_reference_item, asset_path),
                ok_label=constants.ASSET_NEED_INGEST_WINDOW_OK_LABEL,
                disable_ok_button=not self._core.asset_is_in_project_dir(asset_path, layer),
                disable_cancel_button=False,
                disable_middle_button=not ingest_enabled,
                middle_handler=self._go_to_ingest_tab,
                middle_label=constants.ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL,
            )

            return
        self._add_new_ref_mesh(add_reference_item, asset_path)

    def _add_new_ref_mesh(
        self,
        add_reference_item: Union[_ItemAddNewReferenceFileMesh, _ItemReferenceFileMesh],
        asset_path: str,
    ):
        layer = self._context.get_stage().GetEditTarget().GetLayer()
        if not self._core.asset_is_in_project_dir(asset_path, layer):
            if self._core.was_the_asset_ingested(path=asset_path, ignore_invalid_paths=False):
                # Prompt the user copy the asset into the project folder or cancel
                _TrexMessageDialog(
                    title=constants.ASSET_OUTSIDE_OF_PROJ_DIR_TITLE,
                    message=constants.ASSET_OUTSIDE_OF_PROJ_DIR_MESSAGE,
                    disable_ok_button=False,
                    ok_label=constants.ASSET_OUTSIDE_OF_PROJ_DIR_OK_LABEL,
                    ok_handler=functools.partial(
                        _copy_usd_asset,
                        context=self._context,
                        asset_path=asset_path,
                        callback_func=lambda x: self._add_new_ref_mesh(
                            add_reference_item=add_reference_item,
                            asset_path=x,
                        ),
                    ),
                    disable_middle_button=True,
                    disable_cancel_button=False,
                )
            else:
                # Prompt the user to ingest the external asset into the project folder
                _TrexMessageDialog(
                    title=constants.ASSET_OUTSIDE_OF_PROJ_DIR_AND_NEED_INGEST_TITLE,
                    message=constants.ASSET_OUTSIDE_OF_PROJ_DIR_AND_NEED_INGEST_MESSAGE,
                    disable_ok_button=True,
                    disable_middle_button=False,
                    middle_handler=self._go_to_ingest_tab,
                    middle_label=constants.ASSET_NEED_INGEST_WINDOW_MIDDLE_LABEL,
                    disable_cancel_button=False,
                )
            return

        stage = self._context.get_stage()
        with omni.kit.undo.group(), self._tree_model.refresh_only_at_the_end():
            new_ref, prim_path = self._core.add_new_reference(
                stage,
                add_reference_item.prim.GetPath(),
                asset_path,
                self._core.get_ref_default_prim_tag(),
                stage.GetEditTarget().GetLayer(),
            )
            if new_ref:
                carb.log_info(
                    (
                        f"Set new ref {new_ref.assetPath} {new_ref.primPath}, "
                        f"layer {self._context.get_stage().GetEditTarget().GetLayer()}"
                    )
                )
                # select the new prim of the new added ref
                current_instance_items = [
                    item for item in self._previous_instance_selection if isinstance(item, _ItemInstanceMesh)
                ]
                self._core.select_child_from_instance_item_and_ref(
                    stage,
                    stage.GetPrimAtPath(prim_path),
                    new_ref.assetPath,
                    current_instance_items,
                    only_imageable=True,
                    filter_scope_prim_without_imageable=True,
                )
            else:
                carb.log_info("No reference set")

    @omni.usd.handle_exception
    async def __deferred_expand(self, selection):
        def get_items_to_expand(items):
            for sel in items:
                if hasattr(sel, "parent"):
                    yield sel.parent
                    yield from get_items_to_expand([sel.parent])

        items_to_expand = list(set(get_items_to_expand(selection)))
        all_visible_items = []

        def set_expanded(items):
            for item_ in items:
                # _ItemMesh is always expanded
                if item_ not in items_to_expand and not isinstance(item_, _ItemMesh):
                    continue
                self._tree_view.set_expanded(item_, True, False)
                all_visible_items.append(item_)
                children = self._tree_model.get_item_children(item_)
                all_visible_items.extend(children)
                set_expanded(children)

        if self._tree_view is None:
            return []
        if self._tree_model is None:
            return []
        await omni.kit.app.get_app().next_update_async()  # for tests...
        set_expanded(self._tree_model.get_item_children(None))

        result = [item for item in self._tree_model.get_all_items() if item in all_visible_items]
        return result

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

    def _get_hash(self, item):
        return re.match(constants.REGEX_HASH, str(item.prim.GetPath())).group(3)

    def show(self, value):
        self._tree_model.enable_listeners(value)
        if value:
            self.__refresh_delegate_gradients()

    def destroy(self):
        if self.__on_deferred_tree_model_changed_tack:
            self.__on_deferred_tree_model_changed_tack.cancel()
        self.__on_deferred_tree_model_changed_tack = None
        self.__on_tree_selection_changed = None
        self.__on_tree_model_emptied = None
        _reset_default_attrs(self)
