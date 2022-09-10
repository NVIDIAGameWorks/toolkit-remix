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
from typing import Callable, List, Union

import carb
import omni.ui as ui
import omni.usd
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from lightspeed.trex.utils.widget.file_pickers.mesh_ref_file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .selection_tree.delegate import Delegate as _Delegate
from .selection_tree.model import ItemAddNewReferenceFileMesh as _ItemAddNewReferenceFileMesh
from .selection_tree.model import ItemInstanceMesh as _ItemInstanceMesh
from .selection_tree.model import ItemInstancesMeshGroup as _ItemInstancesMeshGroup
from .selection_tree.model import ItemMesh as _ItemMesh
from .selection_tree.model import ItemReferenceFileMesh as _ItemReferenceFileMesh
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
            "_core": None,
            "_tree_delegate": None,
            "_sub_tree_model_changed": None,
            "_sub_edit_path_reference": None,
            "_previous_tree_selection": None,
            "_sub_tree_delegate_delete_ref": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = context  # can get the name of the context?
        self._core = _AssetReplacementsCore(self._context)
        self._tree_model = _ListModel(self._context)
        self._tree_delegate = _Delegate()

        self._ignore_tree_selection_changed = False
        self._ignore_select_instance_prim_from_selected_items = False
        self._previous_tree_selection = []

        self._sub_tree_model_changed = self._tree_model.subscribe_item_changed_fn(self._on_tree_model_changed)
        self._sub_tree_delegate_delete_ref = self._tree_delegate.subscribe_delete_reference(self._on_delete_reference)

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
            None,
        ],
    ):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_tree_selection_changed, function)

    def subscribe_delete_reference(self, function: Callable[["Usd.Prim", str], None]):
        return self._tree_delegate.subscribe_delete_reference(function)

    def subscribe_toggle_visibility(self, function: Callable[["Usd.Prim"], None]):
        return self._tree_delegate.subscribe_toggle_visibility(function)

    def subscribe_frame_prim(self, function: Callable[["Usd.Prim"], None]):
        return self._tree_delegate.subscribe_frame_prim(function)

    def subscribe_toggle_nickname(self, function: Callable[["Usd.Prim"], None]):
        return self._tree_delegate.subscribe_toggle_nickname(function)

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

    def _on_delete_reference(self, item: _ItemReferenceFileMesh):
        stage = self._context.get_stage()
        self._core.remove_reference(stage, item.prim.GetPath(), item.ref, item.layer)

    def _on_tree_model_changed(self, _, __):
        self._tree_delegate.reset()
        asyncio.ensure_future(self._on_deferred_tree_model_changed())

    @omni.usd.handle_exception
    async def _on_deferred_tree_model_changed(self):
        await self.__deferred_expand()
        # set selection
        if not self._tree_model:
            return
        stage_selection = self._context.get_selection().get_selected_prim_paths()
        selection = [
            item for item in self._tree_model.get_item_children_type(_ItemInstanceMesh) if item.path in stage_selection
        ]
        if self._previous_tree_selection:
            current_ref_mesh_file = self._tree_model.get_item_children_type(_ItemReferenceFileMesh)
            # we remove instance because they are base on stage selection
            ref_file_mesh_items = []
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
        self._tree_view.selection = selection
        self._previous_tree_selection = selection
        self._ignore_select_instance_prim_from_selected_items = False
        # for _ in range(2):
        #     await omni.kit.app.get_app().next_update_async()
        self.__refresh_delegate_gradients()

    def __refresh_delegate_gradients(self):
        for item in self._tree_view.selection:
            if not self._tree_delegate:
                return
            self._tree_delegate.refresh_gradient_color(item)

    def get_selection(self):
        return self._tree_view.selection

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

        # if we select 1 mesh ref, we keep the instance selected
        if len(items) == 1 and isinstance(items[0], _ItemReferenceFileMesh):
            # grab all current instance
            instance_items = self._tree_model.get_item_children_type(_ItemInstanceMesh)
            # find links between old and new instances
            for item in self._previous_tree_selection:
                if isinstance(item, _ItemInstanceMesh):
                    for instance_item in instance_items:
                        if instance_item.prim == item.prim:
                            items.append(instance_item)
                            break
        # only instance can be multiple selected
        instance_items = self._tree_model.get_item_children_type(_ItemInstanceMesh)
        if len(items) > 1:
            # grab all type
            all_item_types = {type(item) for item in items}
            if _ItemInstanceMesh in all_item_types:
                all_item_types.remove(_ItemInstanceMesh)
            # if we have more than 1 type, only the last one can be taken
            if len(all_item_types) > 1:
                result = []
                last_other_item = None
                for item in items:
                    # we keep instance items
                    if isinstance(item, (_ItemInstanceMesh, _ItemInstancesMeshGroup)):
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

        self._tree_view.selection = items
        if not self._ignore_select_instance_prim_from_selected_items:
            self._tree_model.select_instance_prim_from_selected_items(items)
        self._previous_tree_selection = items
        self._tree_delegate.on_item_selected(items, self._tree_model.get_all_items())

        # if add item was clicked, we open the ref picker
        if add_item_selected:
            _open_file_picker(functools.partial(self._add_new_ref_mesh, add_item_selected[0]), lambda *args: None)

        self._tree_selection_changed(items)

    def _add_new_ref_mesh(self, add_reference_item: _ItemAddNewReferenceFileMesh, asset_path: str):
        stage = self._context.get_stage()
        new_ref = self._core.add_new_reference(
            stage, add_reference_item.prim.GetPath(), asset_path, stage.GetEditTarget().GetLayer()
        )
        if new_ref:
            carb.log_info(
                (
                    f"Set new ref {new_ref.assetPath} {new_ref.primPath}, "
                    f"layer {self._context.get_stage().GetEditTarget().GetLayer()}"
                )
            )
        else:
            carb.log_info("No reference set")

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

    def show(self, value):
        self._tree_model.enable_listeners(value)
        if value:
            self.__refresh_delegate_gradients()

    def destroy(self):
        _reset_default_attrs(self)