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
from .selection_tree.model import AnyItemType as _AnyItemType
from .selection_tree.model import ItemAddNewLiveLight as _ItemAddNewLiveLight
from .selection_tree.model import ItemAddNewReferenceFile as _ItemAddNewReferenceFileMesh
from .selection_tree.model import ItemAsset as _ItemAsset
from .selection_tree.model import ItemInstance as _ItemInstance
from .selection_tree.model import ItemInstancesGroup as _ItemInstancesGroup
from .selection_tree.model import ItemLiveLightGroup as _ItemLiveLightGroup
from .selection_tree.model import ItemPrim as _ItemPrim
from .selection_tree.model import ItemReferenceFile as _ItemReferenceFile
from .selection_tree.model import ListModel as _ListModel

if typing.TYPE_CHECKING:
    from pxr import Sdf, Usd


class SetupUI:
    DEFAULT_TREE_FRAME_HEIGHT = 200
    SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(self, context_name):
        """Selection Tree Widget"""

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

        self.__on_deferred_tree_model_changed_task = None

        self._ignore_tree_selection_changed = False
        self._ignore_select_prototype = False
        self._previous_tree_selection: list[_AnyItemType] = []
        self._instance_selection: list[_ItemInstance | _ItemInstancesGroup] = []
        self._previous_instance_selection: list[_ItemInstance | _ItemInstancesGroup] = []

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
        items: List[_AnyItemType],
    ):
        """Call the event object that has the list of functions"""
        if self.__on_tree_selection_changed is not None:
            self.__on_tree_selection_changed(items)

    def subscribe_tree_selection_changed(
        self,
        function: Callable[
            [List[_AnyItemType]],
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
                                    column_widths=[ui.Fraction(1)],
                                    style_type_name_override="TreeView.Selection",
                                    identifier="LiveSelectionTreeView",
                                )
                                self._tree_view.set_mouse_pressed_fn(self._obtain_tree_pressed_input)
                                self._tree_view.set_selection_changed_fn(self._on_tree_selection_changed)

                                self._fake_frame_for_scroll = ui.Frame()
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

    def _on_duplicate_reference(self, item: _ItemReferenceFile):
        abs_path = omni.client.normalize_url(item.layer.ComputeAbsolutePath(item.path))
        self._add_new_ref_mesh(item, abs_path)

    def _on_duplicate_prim(self, item: _ItemPrim):
        # need to save the current instance selection before calling usd command
        instances = [item for item in self._instance_selection if isinstance(item, _ItemInstance)]
        with omni.kit.undo.group(), self._tree_model.refresh_only_at_the_end():
            omni.kit.commands.execute(
                "CopyPrimCommand",
                path_from=item.path,
                usd_context_name=self._context_name,
            )
            if not instances:
                instances = self._tree_model.get_root_asset_item(item).instance_group_item.instances
            if instances:
                # newly duplicated prim paths will be selected after copy command
                duplicated_prim_paths = self._core.get_selected_prim_paths()
                self._core.select_prim_paths(
                    self._core.get_instance_from_mesh(duplicated_prim_paths, [instances[0].path])
                )

    def _on_delete_prim(self, item: _ItemPrim):
        # select the previous selection. If nothing was selected, select the parent of the item.
        previous_selected_item_prims = [
            _item for _item in self._previous_tree_selection if isinstance(_item, _ItemPrim) and _item.path != item.path
        ]
        if previous_selected_item_prims:
            item_prims = previous_selected_item_prims
        else:
            item_prims = [self._tree_model.get_parent_item(item)]

        to_select_path_str = []
        if item_prims:
            # Get the path relative to the selected instance or first instance
            instance_paths = [
                item.path for item in self._previous_instance_selection if isinstance(item, _ItemInstance)
            ]
            if not instance_paths:
                instances = self._tree_model.get_root_asset_item(item).instance_group_item.instances
                if instances:
                    instance_paths = [instances[0].path]

            if instance_paths:
                to_select_path_str = self._core.get_instance_from_mesh(
                    [item_prim.path for item_prim in item_prims], instance_paths
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

    def _on_delete_reference(self, item: _ItemReferenceFile):
        stage = self._context.get_stage()

        # save the current selection
        to_select = []
        previous_selected_instance_items = [
            _item for _item in self._previous_instance_selection if isinstance(_item, _ItemInstance)
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

        if not previous_selected_prim_items:
            # select the first prim of the previous mesh from the first ref
            parent = item.parent
            for ref_item in parent.reference_items:
                if ref_item == item:
                    continue
                if ref_item.child_prim_items:
                    prims = self._core.get_prim_from_ref_items(
                        ref_items=[ref_item],
                        parent_items=previous_selected_instance_items,
                        only_xformable=True,
                        level=1,
                        skip_remix_ref=True,
                    )
                    if prims:
                        to_select = [str(prim.GetPath()) for prim in prims]
                        break
        else:
            # select the first previously prim item from the tree selection
            to_select = [previous_selected_prim_items[0].path]

        if not to_select:
            # if we don't have any prims anymore, we select the previous instance
            if previous_selected_instance_items:
                to_select = [previous_selected_instance_items[0].path]
            else:
                # if we don't have a selected instance, we select the mesh
                to_select = [item.parent.path]

        # keep the currently selected prims
        current_selection = self._core.get_selected_prim_paths()
        to_select.extend(current_selection)

        # filter out any invalid prim path
        to_select = [prim_path for prim_path in to_select if stage.GetPrimAtPath(prim_path).IsValid()]

        with omni.kit.undo.group(), self._tree_model.refresh_only_at_the_end():
            self._core.select_prim_paths(to_select, current_selection=current_selection)
            self._core.remove_reference(stage, item.prim.GetPath(), item.ref, item.layer)

    def _on_tree_model_changed(self, model, __):
        # Clear all the internal tracking if the model changes...
        self._previous_tree_selection = []
        self._instance_selection = []
        self._previous_instance_selection = []
        self._tree_delegate.reset()

        if self.__on_deferred_tree_model_changed_task:
            self.__on_deferred_tree_model_changed_task.cancel()
        self.__on_deferred_tree_model_changed_task = asyncio.ensure_future(self._on_deferred_tree_model_changed())

        self._frame_none.visible = False
        if not model.get_all_items() and self.__on_tree_model_emptied is not None:
            self._frame_none.visible = True
            # warning: secondary selection may not yet be updated
            self.__on_tree_model_emptied(model)

    @omni.usd.handle_exception
    async def _on_deferred_tree_model_changed(self):
        # set selection
        if not self._tree_model:
            return
        stage_selection = self._context.get_selection().get_selected_prim_paths()

        selection: list[_AnyItemType] = []
        all_items_by_types = self._tree_model.get_all_items_by_type()

        # select the item prim
        prototypes_stage_selected_paths = self._core.get_corresponding_prototype_prims_from_path(stage_selection)
        item_prims = all_items_by_types.get(_ItemPrim, [])
        item_group_instances = all_items_by_types.get(_ItemInstancesGroup, [])
        for item in item_prims:
            if item.path in prototypes_stage_selected_paths:
                selection.append(item)

        # we select the instance in the tree
        for item in all_items_by_types.get(_ItemInstance, []):
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

        if selection and self._previous_tree_selection:
            current_ref_mesh_file = all_items_by_types.get(_ItemReferenceFile, [])
            # we remove instance because they are base on stage selection
            ref_file_items = []
            # if the last selection if a prim, we don't select the previous ref
            to_add = True
            if isinstance(selection[-1], _ItemPrim):
                to_add = False
            if to_add:
                for item in self._previous_tree_selection:
                    # we grab all reference file mesh
                    if isinstance(item, _ItemReferenceFile):
                        ref_file_items.append(item)
            # if the size of ref is the same, we select the previous ref
            if ref_file_items and current_ref_mesh_file:  # noqa SIM102
                # same len ref as before, so we grab the previous selected index
                if (
                    len(current_ref_mesh_file) == ref_file_items[0].size_ref_index
                    and current_ref_mesh_file[0].prim == ref_file_items[0].prim
                ):
                    for ref_file_item in ref_file_items:
                        selection.append(current_ref_mesh_file[ref_file_item.ref_index])

        # we select the corresponding prim instance
        self._ignore_select_prototype = True
        # we remove duplicated but keep the order
        selection = list(dict.fromkeys(selection))

        all_visible_items = await self.__deferred_expand(selection)
        if self._tree_view is not None:
            if self._tree_view.selection != selection:
                # this will trigger _on_tree_selection_changed()
                self._tree_view.selection = selection
            else:
                # If tree model changed, we want to trigger an update even if selection is the same. This can happen
                # when model is emptied and selection is also emptied but we haven't updated "previous selection"
                self._on_tree_selection_changed(selection)
            first_item_prim = sorted([item for item in selection if isinstance(item, _ItemPrim)], key=lambda x: x.path)
            if first_item_prim:
                await self.scroll_to_item(first_item_prim[0], all_visible_items)
        self._ignore_select_prototype = False
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

    def get_selection(self, get_instances: bool = True):
        """Return the selection consisting of both the primary and secondary (instance) selections."""
        if self._tree_view is None:
            return []

        # Use USD selection instead of the tree selection to work when the widget is collapsed
        selected_paths = self._context.get_selection().get_selected_prim_paths()
        selected_prototypes = set(self._core.get_corresponding_prototype_prims_from_path(selected_paths))

        item_types = self._tree_model.get_all_items_by_type()

        assets = [i for i in item_types.get(_ItemAsset, []) if i.path in selected_prototypes]
        prims = [i for i in item_types.get(_ItemPrim, []) if i.path in selected_prototypes]
        # since reference items are not "prims" we need to use previous tree selection
        references = [
            i
            for i in item_types.get(_ItemReferenceFile, [])
            if str(i.prim.GetPath()) in selected_prototypes and i in self._previous_tree_selection
        ]

        selection = {*assets, *prims, *references}

        if get_instances:
            instance_selection = self.get_instance_selection(include_instance_group=False)
            selection = selection.union(instance_selection)

        return list(selection)

    def get_instance_selection(self, include_instance_group: bool = False):
        """Return the instances from within the secondary selection. Do not include instance groups by default."""
        if self._tree_view is None or self._frame_none.visible:
            return []

        if include_instance_group:
            return self._instance_selection
        return [item for item in self._instance_selection if isinstance(item, _ItemInstance)]

    @_ignore_function_decorator(attrs=["_ignore_tree_selection_changed"])
    def _on_tree_selection_changed(self, selection: list[_AnyItemType]):
        """
        React to a new tree selection by extending other items or restoring any items that should remain selected.

        Here is how the selection behavior works for each type of item:
        - `_ItemAsset` [cannot be selected]
         - `_ItemReferenceFile` [1 can be selected at a time]
          - `_ItemPrim` [multiple can be selected, and changes are forwarded to stage]
           - `_ItemPrim`
         - `ItemAddNewReferenceFile` [button]
         - `_ItemLiveLightGroup` [group, if selected: select children]
          - `_ItemPrim` [multiple can be selected, and changes are forwarded to stage]
          - `_ItemAddNewLiveLight` [button]
         - `_ItemInstancesGroup` [group, if selected: select children]
          - `_ItemInstance` [minimum one selected, but multiple can be selected]
        """
        # determine whether this was a click or a multi select operation that happened to pick up a button item
        item_was_clicked = len(selection) == 1

        # grab all current prims
        all_items_by_types = self._tree_model.get_all_items_by_type()
        asset_items: list[_ItemAsset] = all_items_by_types.get(_ItemAsset, [])
        prim_items: list[_ItemPrim] = all_items_by_types.get(_ItemPrim, [])
        ref_items: list[_ItemReferenceFile] = all_items_by_types.get(_ItemReferenceFile, [])

        # Expand selection to include the correct instance selection
        unrelated_instance_selections = []
        selected_instance_items = [item for item in selection if isinstance(item, _ItemInstance)]
        if selected_instance_items and self._current_tree_pressed_input:
            # if there are multiple top-level item meshes, save the unrelated instance selections to re-select later
            if len(asset_items) > 1:
                # find out which ItemMesh section was selected
                selected_instance_item_hash = self._get_hash(selected_instance_items[0])
                asset_item_hashes = {self._get_hash(asset_item) for asset_item in asset_items}

                # save the previous instance selections if they are not related to the selected ItemMesh section
                for previous_instance in self._previous_instance_selection:
                    if not isinstance(previous_instance, _ItemInstance):
                        continue
                    previous_instance_hash = self._get_hash(previous_instance)
                    if (
                        previous_instance_hash != selected_instance_item_hash
                        and previous_instance_hash in asset_item_hashes
                    ):
                        unrelated_instance_selections.append(previous_instance)

            # handle modifier selections
            if self._current_tree_pressed_input["modifier"] == 1:  # shift was pressed
                # if only one ItemMesh section, manually shift select, otherwise ignore
                if len(asset_items) == 1:
                    # manually create a shift multi-selection between the start and end instance selections
                    all_instance_items = self._tree_model.get_all_items_by_type().get(_ItemInstance, [])
                    selection_start_index = all_instance_items.index(self._previous_instance_selection[0])
                    selection_end_index = all_instance_items.index(selected_instance_items[-1])

                    if selection_start_index > selection_end_index:
                        selection_start_index, selection_end_index = selection_end_index, selection_start_index
                    selection = all_instance_items[selection_start_index : selection_end_index + 1]  # noqa: E203
                else:
                    # TODO: Find a way to get shift selection to work when multiple ItemMesh sections are open
                    #       - `selection` is invalid if multiple ItemMesh selections and shift is clicked
                    # ignore the shift selection since shift conceals clicked_instance_items; this is a limitation
                    selection = self._previous_instance_selection
            elif self._current_tree_pressed_input["modifier"] == 2:  # ctrl pressed
                # manually add the previous instance selection item(s) to the current
                selection += self._previous_instance_selection
        elif selection:
            # if non-instance item selected, add the instance selection back
            selection += self._previous_instance_selection

        # if there were multiple ItemMesh in the tree, add the unrelated previous instance selections back
        if unrelated_instance_selections:
            selection += list(set(unrelated_instance_selections))

        # reset the tree pressed input; this prevents outdated input after selection change from viewport
        self._current_tree_pressed_input = None

        # Filter selection down to the various different types...
        selected_prim_items: list[_ItemPrim | _ItemLiveLightGroup] = []
        selected_ref_file_items: list[_ItemReferenceFile] = []
        selected_instance_groups: list[_ItemInstancesGroup] = []
        selected_instances: list[_ItemInstance] = []
        # grab the add mesh/add light item buttons if they were clicked
        add_item_clicked = None
        add_light_clicked = None
        asset_item_clicked = False
        for item in selection:
            if isinstance(item, _ItemInstancesGroup):
                # if a group was selected, add the instances of the group and the group item itself
                # skip if group is not directly clicked, as it may be one of its members being deselected
                if item_was_clicked:
                    selected_instances.extend(item.instances)
                    selected_instance_groups.append(item)
            elif isinstance(item, _ItemInstance):
                # just add the individual instance item otherwise
                selected_instances.append(item)
            elif isinstance(item, _ItemAddNewReferenceFileMesh):
                if item_was_clicked:
                    add_item_clicked = item
            elif isinstance(item, _ItemAddNewLiveLight):
                if item_was_clicked:
                    add_light_clicked = item
            elif isinstance(item, _ItemAsset):
                # we can't select the top mesh item, so exclude this from selection
                if item_was_clicked:
                    # if just the top mesh item was clicked, ignore new selection
                    asset_item_clicked = True
            elif isinstance(item, _ItemLiveLightGroup):
                if item_was_clicked:
                    selected_prim_items.extend(item.lights)
                    selected_prim_items.append(item)
            elif isinstance(item, _ItemPrim):
                # these we can select
                selected_prim_items.append(item)
            elif isinstance(item, _ItemReferenceFile):
                # only allow one:
                selected_ref_file_items = [item]
            else:
                raise ValueError(f"Unexpected item type: {type(item)}, {item}")

        # `items` will correlate with primary selections and `self._instance_selection` with secondary selections
        items: list[_ItemPrim | _ItemLiveLightGroup | _ItemReferenceFile] = list(
            dict.fromkeys(selected_prim_items + selected_ref_file_items)
        )
        self._instance_selection: list[_ItemInstancesGroup | _ItemInstance] = list(
            dict.fromkeys(selected_instance_groups + selected_instances)
        )

        # Only a prim or light selection (inside a master) can deselect the current prim
        # if we select an instance, and a prim/ref is selected, we keep the prim/ref selected
        # if the selected instance is a light we don't want to do this because there is no corresponding prim
        selected_instance_lights = [item for item in selected_instances if item.parent.parent.is_light()]
        prim_item_selected = selected_prim_items or selected_ref_file_items or selected_instance_lights
        if not prim_item_selected:
            for previous_item in self._previous_tree_selection:
                # restore prim selection
                if isinstance(previous_item, _ItemPrim):
                    for item_prim in prim_items:
                        if item_prim.prim == previous_item.prim:
                            items.append(item_prim)
                            break
                # if no prim was selected, keep the last selected reference file unless a new ref was selected.
                elif isinstance(previous_item, _ItemReferenceFile):
                    for item_ref in ref_items:
                        if item_ref.path == previous_item.path:
                            items.append(item_ref)
                            break
        if selected_instance_lights and asset_item_clicked:
            # if the asset item is clicked but this is a light, then we treat it differently because we don't always
            # restore the previous selection and an item_prim may have just been de-selected.
            asset_item_clicked = False

        # if all lights are selected within light group, select the light group item itself
        all_light_groups: list[_ItemLiveLightGroup] = all_items_by_types.get(_ItemLiveLightGroup, [])
        for light_group in all_light_groups:
            if all(light_prim_item in items for light_prim_item in light_group.lights):
                items.append(light_group)

        all_item_instance_groups: list[_ItemInstancesGroup] = all_items_by_types.get(_ItemInstancesGroup, [])
        for instance_group in all_item_instance_groups:
            # if all instances are selected within an instance group, select the instance group item itself
            if all(instance in self._instance_selection for instance in instance_group.instances):
                self._instance_selection.append(instance_group)
            # if no instances are selected, just select the first available
            elif not any(instance in self._instance_selection for instance in instance_group.instances):
                self._instance_selection.append(instance_group.instances[0])

        # select items in the tree
        if self._tree_view is not None:
            self._tree_view.selection = items
        if not self._ignore_select_prototype:
            # select prims when item prims are clicked
            prim_paths = [str(item.prim.GetPath()) for item in items if isinstance(item, _ItemPrim)]
            # if this is a light and there is no item prim selected, add the path of the light
            if not prim_paths and selected_instance_lights:
                prim_paths = [str(item.prim.GetPath()) for item in selected_instance_lights]

            # we swap all the item prim path with the current selected item instances
            to_select_paths = []
            for path in prim_paths:
                for instance_item in self._instance_selection:
                    if isinstance(instance_item, _ItemInstance):
                        to_select_path = re.sub(
                            constants.REGEX_MESH_TO_INSTANCE_SUB, str(instance_item.prim.GetPath()), path
                        )
                        to_select_paths.append(to_select_path)

            # If we have a ref selected, add the path of the ref
            to_select_paths.extend([str(selected_ref.prim.GetPath()) for selected_ref in selected_ref_file_items])

            # Select the instance prims in the stage
            self._tree_model.select_prim_paths(list(set(to_select_paths)))

        self._previous_tree_selection = list(set(items))
        self._previous_instance_selection = list(set(self._instance_selection))
        self._tree_delegate.on_item_selected(items, self._instance_selection, self._tree_model.get_all_items())

        # if add item was clicked, we open the ref picker
        if add_item_clicked:
            _open_file_picker(
                "Select a reference file",
                functools.partial(self._add_new_unique_ref_mesh, add_item_clicked),
                lambda *args: None,
                file_extension_options=constants.READ_USD_FILE_EXTENSIONS_OPTIONS,
                validate_selection=_is_usd_file_path_valid_for_filepicker,
                validation_failed_callback=self.__show_error_not_usd_file,
            )
        elif add_light_clicked:  # if add light was clicked
            self.__show_light_creator_window(add_light_clicked)

        if add_item_clicked or add_light_clicked or asset_item_clicked:
            return  # skip selection changed call... nothing should have changed!

        self._tree_selection_changed(items + self._instance_selection)

    def __show_error_not_usd_file(self, dirname: str, filename: str):
        _TrexMessageDialog(
            message=f"{dirname}/{filename} is not a USD file",
            disable_cancel_button=True,
        )

    def __show_light_creator_window(
        self,
        add_item: _ItemAddNewLiveLight,
    ):
        async def _deferred_hide():
            await omni.kit.app.get_app().next_update_async()
            if self._light_creator_window:
                self._light_creator_window.frame.clear()
                self._light_creator_window.visible = False

        def _hide(light_path: str):
            asyncio.ensure_future(_deferred_hide())
            # Select the new light path relative to the selected instance or the first instance
            instances = [item for item in self._instance_selection if isinstance(item, _ItemInstance)]
            if not instances:
                instances = add_item.parent.instance_group_item.instances
            if instances:
                instance_path = instances[0].path
                self._core.select_prim_paths(self._core.get_instance_from_mesh([light_path], [instance_path]))

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
        self, add_reference_item: Union[_ItemAddNewReferenceFileMesh, _ItemReferenceFile], asset_path: str
    ):
        self._add_new_ref_mesh(add_reference_item, asset_path)

    def _add_new_unique_ref_mesh(
        self, add_reference_item: Union[_ItemAddNewReferenceFileMesh, _ItemReferenceFile], asset_path: str
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
        add_reference_item: Union[_ItemAddNewReferenceFileMesh, _ItemReferenceFile],
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
                    item for item in self._previous_instance_selection if isinstance(item, _ItemInstance)
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
    async def __deferred_expand(self, selection: list[_AnyItemType]):
        if self._tree_view is None:
            return []
        if self._tree_model is None:
            return []

        def get_items_to_expand(items):
            for sel in items:
                if hasattr(sel, "parent"):
                    yield sel.parent
                    yield from get_items_to_expand([sel.parent])

        items_to_expand = list(set(get_items_to_expand(selection)))
        all_visible_items = set()

        def set_expanded(items):
            for item_ in items:
                # _ItemAsset is always expanded
                if item_ not in items_to_expand and not isinstance(item_, _ItemAsset):
                    continue
                self._tree_view.set_expanded(item_, True, False)
                all_visible_items.add(item_)
                children = self._tree_model.get_item_children(item_)
                all_visible_items.update(children)
                set_expanded(children)

        await omni.kit.app.get_app().next_update_async()  # for tests...
        set_expanded(self._tree_model.get_item_children(None))

        result = [item for item in self._tree_model.get_all_items() if item in all_visible_items]
        return result

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
        if self.__on_deferred_tree_model_changed_task:
            self.__on_deferred_tree_model_changed_task.cancel()
        self.__on_deferred_tree_model_changed_task = None
        self.__on_tree_selection_changed = None
        self.__on_tree_model_emptied = None
        _reset_default_attrs(self)
