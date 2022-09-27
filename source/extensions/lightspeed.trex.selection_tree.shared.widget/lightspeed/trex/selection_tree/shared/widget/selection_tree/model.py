"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import re
import typing
from typing import Dict, List, Optional, Tuple, Type, Union

import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .listener import USDListener as _USDListener

if typing.TYPE_CHECKING:
    from pxr import Sdf, Usd

HEADER_DICT = {0: "Path"}


class ItemInstanceMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim"):
        super().__init__()
        self.prim = prim
        self.path = str(prim.GetPath())
        self.value_model = ui.SimpleStringModel(self.path)

    def __repr__(self):
        return f'"{self.path}"'


class ItemInstancesMeshGroup(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, instance_prims: List["Usd.Prim"]):
        super().__init__()
        self.display = "Instances"
        self.instances = [ItemInstanceMesh(instance_prim) for instance_prim in instance_prims]
        self.value_model = ui.SimpleStringModel(self.display)

    def __repr__(self):
        return f'"{self.display}"'


class ItemAddNewReferenceFileMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim"):
        super().__init__()
        self.prim = prim
        self.display = "Add new reference..."
        self.value_model = ui.SimpleStringModel(self.display)

    def __repr__(self):
        return f'"{self.display}"'


class ItemReferenceFileMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", ref: "Sdf.Reference", layer: "Sdf.Layer", ref_index: int, size_ref_index: int):
        super().__init__()
        self.prim = prim
        self.ref = ref
        self.path = str(ref.assetPath)
        self.layer = layer
        self.ref_index = ref_index
        self.size_ref_index = size_ref_index
        self.value_model = ui.SimpleStringModel(self.path)

    def __repr__(self):
        return f'"{self.path}"'


class ItemMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", instance_prims: List["Usd.Prim"]):
        super().__init__()
        self.prim = prim
        self.path = str(prim.GetPath())
        self.value_model = ui.SimpleStringModel(self.path)

        self.add_new_reference_item = ItemAddNewReferenceFileMesh(self.prim)
        self.instance_group_item = ItemInstancesMeshGroup(instance_prims)
        prim_paths, total_ref = self.__reference_file_paths(self.prim)
        self.reference_items = [
            ItemReferenceFileMesh(self.prim, ref, layer, i, total_ref) for ref, layer, i in prim_paths
        ]

    @staticmethod
    def __reference_file_paths(prim) -> Tuple[List[Tuple["Sdf.Reference", "Sdf.Layer", int]], int]:
        prim_paths = []
        ref_and_layers = omni.usd.get_composed_references_from_prim(prim, False)
        i = 0
        for (ref, layer) in ref_and_layers:
            if not ref.assetPath:
                continue
            prim_paths.append((ref, layer, i))
            i += 1

        return prim_paths, i

    def __repr__(self):
        return f'"{self.path}"'


class ListModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self, context_name):
        super().__init__()
        self.default_attr = {"_stage_event": None, "_usd_listener": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.__children = []
        self._stage = None
        self._ignore_refresh = False
        self._context = omni.usd.get_context(context_name)
        self._stage_event = None
        self._usd_listener = _USDListener()

    @property
    def stage(self):
        return self._context.get_stage()

    def enable_listeners(self, value):
        if value:
            self._usd_listener.add_model(self)
            self._stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_event, name="StageEvent"
            )
        else:
            self._usd_listener.remove_model(self)
            self._stage_event = None

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self.refresh()
            if self._ignore_refresh:
                self._ignore_refresh = False

    def __get_mesh_from_path(self, path) -> Optional[str]:
        if path.startswith(constants.MESH_PATH):
            return path
        prim = self.stage.GetPrimAtPath(path)
        if not prim.IsValid():
            return None
        refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
        for (ref, _) in refs_and_layers:
            if not ref.assetPath and str(ref.primPath).startswith(constants.MESH_PATH):
                return str(ref.primPath)
        return None

    @staticmethod
    def __get_reference_prims(prim) -> List["Sdf.Path"]:
        prim_paths = []
        for prim_spec in prim.GetPrimStack():
            items = prim_spec.referenceList.prependedItems
            for item in items:
                if item.primPath:
                    prim_paths.append(item.primPath)

        return prim_paths

    def __get_instances_by_mesh(self) -> Dict["Sdf.Path", List["Usd.Prim"]]:
        result = {}
        if not self.stage:
            return result
        iterator = iter(self.stage.TraverseAll())
        for prim in iterator:
            ref = self.__get_reference_prims(prim)
            if ref and ref[0] == prim.GetPath():
                continue
            if ref and ref[0] in result and prim not in result[ref[0]]:
                result[ref[0]].append(prim)
            elif ref and ref[0] not in result:
                result[ref[0]] = [prim]
        return result

    def select_instance_prim_from_selected_items(self, items):
        result = [str(item.prim.GetPath()) for item in items if isinstance(item, ItemInstanceMesh)]
        current_selection = self._context.get_selection().get_selected_prim_paths()
        if sorted(result) != sorted(current_selection):
            self._ignore_refresh = True
            self._context.get_selection().set_selected_prim_paths(result, True)

    @_ignore_function_decorator(attrs=["_ignore_refresh"])
    def refresh(self):
        """Refresh the list"""
        # analyze the selected path
        def atoi(text):
            return int(text) if text.isdigit() else text

        def natural_keys(text):
            """
            Sort item with number inside

            Args:
                text: the text to sort

            Returns:
                Sorted items
            """
            return [atoi(c) for c in re.split(r"(\d+)", text)]

        mesh_items = []
        if self.stage:
            paths = self._context.get_selection().get_selected_prim_paths()
            if paths:
                instances_data = self.__get_instances_by_mesh()
                meshes = []
                for path in paths:
                    # first, we try to find the mesh_ from the selection
                    mesh = self.__get_mesh_from_path(path)
                    if not mesh or mesh in meshes:
                        continue
                    meshes.append(mesh)
                for mesh in meshes:
                    mesh_prim = self.stage.GetPrimAtPath(mesh)
                    sdf_mesh_path = mesh_prim.GetPath()
                    mesh_items.append(
                        ItemMesh(
                            mesh_prim,
                            sorted(instances_data.get(sdf_mesh_path, []), key=lambda x: natural_keys(x.GetName())),
                        )
                    )
        self.__children = mesh_items
        self._item_changed(None)

    def get_item_children_type(
        self,
        item_type: Type[
            Union[
                ItemMesh, ItemReferenceFileMesh, ItemAddNewReferenceFileMesh, ItemInstancesMeshGroup, ItemInstanceMesh
            ]
        ],
    ) -> List[
        Union[ItemMesh, ItemReferenceFileMesh, ItemAddNewReferenceFileMesh, ItemInstancesMeshGroup, ItemInstanceMesh]
    ]:
        result = []

        def get_children(_items):
            for item in _items:
                if isinstance(item, item_type):
                    result.append(item)
                get_children(self.get_item_children(item))

        get_children(self.__children)
        return result

    def get_all_items(self):
        result = []

        def get_children(_items):
            for item in _items:
                result.append(item)
                get_children(self.get_item_children(item))

        get_children(self.__children)
        return result

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__children
        if isinstance(item, ItemMesh):
            return item.reference_items + [item.add_new_reference_item, item.instance_group_item]
        if isinstance(item, ItemInstancesMeshGroup):
            return item.instances
        return []

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if column_id == 0:
            return item.value_model
        return None

    def destroy(self):
        _reset_default_attrs(self)
