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
import re
import typing
from typing import Any, Callable, List, Union

import carb
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker

from .selection_tree.delegate import Delegate as _Delegate
from .selection_tree.model import ItemAddNewReferenceFileMesh as _ItemAddNewReferenceFileMesh
from .selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
from .selection_tree.model import ItemInstancesMeshGroup as _ItemInstancesMeshGroup
from .selection_tree.model import ItemMesh as _ItemMesh
from .selection_tree.model import ItemPrim as _ItemPrim
from .selection_tree.model import ItemReferenceFileMesh as _ItemReferenceFileMesh
from .selection_tree.model import ListModel as _ListModel

if typing.TYPE_CHECKING:
    from pxr import Usd


class SetupUI:
    FILE_EXTENSIONS = [
        ("*.usd*", "USD Files"),
        ("*.usd", "Binary or Ascii USD File"),
        ("*.usda", "Human-readable USD File"),
        ("*.usdc", "Binary USD File"),
    ]

    DEFAULT_TREE_FRAME_HEIGHT = 200
    SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(self, context_name):
        """Nvidia StageCraft Viewport UI"""

        self._default_attr = {
            "_manipulator_frame": None,
            "_tree_scroll_frame": None,
            "_tree_view": None,
            "_manip_frame": None,
            "_slide_placer": None,
            "_slider_manip": None,
            "_tree_model": None,
            "_core": None,
            "_tree_delegate": None,
            "_sub_tree_model_changed": None,
            "_sub_edit_path_reference": None,
            "_previous_tree_selection": None,
            "_sub_tree_delegate_delete_ref": None,
            "_sub_tree_delegate_duplicate_ref": None,
            "_sub_tree_delegate_reset_ref": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = omni.usd.get_context(context_name)
        self._core = _AssetReplacementsCore(context_name)
        self._tree_model = _ListModel(context_name)
        self._tree_delegate = _Delegate()

        self.__on_deferred_tree_model_changed_tack = None

        self._ignore_tree_selection_changed = False
        self._ignore_select_instance_prim_from_selected_items = False
        self._previous_tree_selection = []

        self._sub_tree_model_changed = self._tree_model.subscribe_item_changed_fn(self._on_tree_model_changed)
        self._sub_tree_delegate_delete_ref = self._tree_delegate.subscribe_delete_reference(self._on_delete_reference)
        self._sub_tree_delegate_duplicate_ref = self._tree_delegate.subscribe_duplicate_reference(
            self._on_duplicate_reference
        )
        self._sub_tree_delegate_reset_ref = self._tree_delegate.subscribe_reset_released(self._on_reset_asset)

        self.__create_ui()

        self.__on_tree_selection_changed = _Event()

    def _tree_selection_changed(
        self,
        items: List[
            Union[
                _ItemMesh,
                _ItemReferenceFileMesh,
                _ItemAddNewReferenceFileMesh,
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
                                style_type_name_override="TreeView.Selection",
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
        self.refresh()

    def refresh(self):
        self._tree_model.refresh()

    def _on_reset_asset(self, prim: "Usd.Prim"):
        self._core.reset_asset(prim)

    def _on_duplicate_reference(self, item: _ItemReferenceFileMesh):
        self._add_new_ref_mesh(item, item.path)

    def _on_delete_reference(self, item: _ItemReferenceFileMesh):
        stage = self._context.get_stage()

        # save the current selection
        to_select = []
        previous_selected_instance_items = [
            _item for _item in self._previous_tree_selection if isinstance(_item, _ItemInstanceMesh)
        ]
        previous_selected_prim_items = [
            _item
            for _item in self._previous_tree_selection
            if isinstance(_item, _ItemPrim)
            and _item.reference_item.parent == item.parent
            and _item.reference_item != item
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

        self._core.remove_reference(stage, item.prim.GetPath(), item.ref, item.layer)

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
        self._core.select_prim_paths(to_select)

    def _on_tree_model_changed(self, _, __):
        self._tree_delegate.reset()
        if self.__on_deferred_tree_model_changed_tack:
            self.__on_deferred_tree_model_changed_tack.cancel()
        self.__on_deferred_tree_model_changed_tack = asyncio.ensure_future(self._on_deferred_tree_model_changed())

    @omni.usd.handle_exception
    async def _on_deferred_tree_model_changed(self):
        # set selection
        if not self._tree_model:
            return
        stage_selection = self._context.get_selection().get_selected_prim_paths()

        selection = []
        # we select the instance in the tree
        for item in self._tree_model.get_item_children_type(_ItemInstanceMesh):
            if item in selection:
                continue
            for stage_selection_path in stage_selection:
                if stage_selection_path.startswith(item.path) and item not in selection:
                    selection.append(item)

        # select the item prim
        prototypes_stage_selected_paths = self._core.get_corresponding_prototype_prims_from_path(stage_selection)
        item_prims = self._tree_model.get_item_children_type(_ItemPrim)
        item_group_instances = self._tree_model.get_item_children_type(_ItemInstancesMeshGroup)
        for item in item_prims:
            if item.path in prototypes_stage_selected_paths:
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
            current_ref_mesh_file = self._tree_model.get_item_children_type(_ItemReferenceFileMesh)
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
        await self.__deferred_expand(selection)
        if self._tree_view is not None:
            self._tree_view.selection = selection
        self._previous_tree_selection = selection
        self._tree_selection_changed(selection)
        self._ignore_select_instance_prim_from_selected_items = False
        # for _ in range(2):
        #     await omni.kit.app.get_app().next_update_async()
        self.__refresh_delegate_gradients()

    def __refresh_delegate_gradients(self):
        for item in self._tree_view.selection if self._tree_view is not None else []:
            if not self._tree_delegate:
                return
            self._tree_delegate.refresh_gradient_color(item)

    def get_selection(self):
        return self._tree_view.selection if self._tree_view is not None else []

    @_ignore_function_decorator(attrs=["_ignore_tree_selection_changed"])
    def _on_tree_selection_changed(self, items):
        # we can't select the top mesh item
        items = [item for item in items if not isinstance(item, _ItemMesh)]
        if not items:
            items = self._previous_tree_selection

        # if the add mesh is clicked, we deselect all others things but not instances and instance group
        add_item_selected = [item for item in items if isinstance(item, _ItemAddNewReferenceFileMesh)]
        if add_item_selected:
            items = [
                item
                for item in self._previous_tree_selection
                if isinstance(item, (_ItemInstanceMesh, _ItemInstancesMeshGroup))
            ]

        # grab all current instance
        instance_items = self._tree_model.get_item_children_type(_ItemInstanceMesh)

        # if we select a mesh ref or prim item, we keep the instance
        if len(items) == 1 and isinstance(items[0], (_ItemReferenceFileMesh, _ItemPrim)):
            # find links between old and new instances
            for item in self._previous_tree_selection:
                if isinstance(item, (_ItemInstanceMesh, _ItemPrim)):
                    for instance_item in instance_items:
                        if instance_item.prim == item.prim:
                            items.append(instance_item)
                            break

        # grab all current prims
        prim_items = self._tree_model.get_item_children_type(_ItemPrim)
        # but if we select an instance, and a prim is selected, we keep the prim selected
        if len(items) == 1 and isinstance(items[0], _ItemInstanceMesh):
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
                    if isinstance(item, (_ItemInstanceMesh, _ItemInstancesMeshGroup, _ItemPrim)):
                        result.append(item)
                        continue
                    last_other_item = item
                # now we add the other item
                if last_other_item:
                    result.append(last_other_item)
                items = result

        # if all instances are selected, select the instance group
        if set(instance_items).issubset(items):
            group_instances = self._tree_model.get_item_children_type(_ItemInstancesMeshGroup)
            if group_instances:
                items.append(group_instances[0])

        # but if we select the instance group, we select all instances
        group_instances = self._tree_model.get_item_children_type(_ItemInstancesMeshGroup)
        if set(group_instances).issubset(items) and not set(instance_items).issubset(items):
            instance_items = self._tree_model.get_item_children_type(_ItemInstanceMesh)
            for instance_item in instance_items:
                if instance_item not in items:
                    items.append(instance_item)

        if self._tree_view is not None:
            self._tree_view.selection = items
        if not self._ignore_select_instance_prim_from_selected_items:
            # select prims when item prims are clicked
            # we swap all the item prim path with the current selected item instances
            prim_paths = [str(item.prim.GetPath()) for item in items if isinstance(item, _ItemPrim)]
            instance_paths = [str(item.prim.GetPath()) for item in items if isinstance(item, _ItemInstanceMesh)]
            to_select_paths = []
            for path in prim_paths:
                for instance_path in instance_paths:
                    to_select_path = re.sub(constants.REGEX_MESH_TO_INSTANCE_SUB, instance_path, path)
                    to_select_paths.append(to_select_path)
            self._tree_model.select_prim_paths(list(set(to_select_paths)))
        self._previous_tree_selection = items
        self._tree_delegate.on_item_selected(items, self._tree_model.get_all_items())

        # if add item was clicked, we open the ref picker
        if add_item_selected:
            _open_file_picker(
                "USD Reference File picker",
                functools.partial(self._add_new_ref_mesh, add_item_selected[0]),
                lambda *args: None,
                file_extension_options=self.FILE_EXTENSIONS,
            )

        self._tree_selection_changed(items)

    def _add_new_ref_mesh(
        self, add_reference_item: Union[_ItemAddNewReferenceFileMesh, _ItemReferenceFileMesh], asset_path: str
    ):
        stage = self._context.get_stage()
        new_ref, prim_path = self._core.add_new_reference(
            stage,
            add_reference_item.prim.GetPath(),
            asset_path,
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
                item for item in self._previous_tree_selection if isinstance(item, _ItemInstanceMesh)
            ]
            self._core.select_child_from_instance_item_and_ref(
                stage, stage.GetPrimAtPath(prim_path), new_ref.assetPath, current_instance_items
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

        def set_expanded(items):
            for item_ in items:
                # _ItemMesh is always expanded
                if item_ not in items_to_expand and not isinstance(item_, _ItemMesh):
                    continue
                self._tree_view.set_expanded(item_, True, False)
                set_expanded(self._tree_model.get_item_children(item_))

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

    def show(self, value):
        self._tree_model.enable_listeners(value)
        if value:
            self.__refresh_delegate_gradients()

    def destroy(self):
        if self.__on_deferred_tree_model_changed_tack:
            self.__on_deferred_tree_model_changed_tack.cancel()
        self.__on_deferred_tree_model_changed_tack = None
        self.__on_tree_selection_changed = None
        _reset_default_attrs(self)
