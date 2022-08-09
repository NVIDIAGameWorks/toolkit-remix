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
from typing import Dict, List, Optional, Type, Union

import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if typing.TYPE_CHECKING:
    from pxr import Sdf, Usd

HEADER_DICT = {0: "Path"}


class ItemInstanceMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", selected):
        super().__init__()
        self.prim = prim
        self.path = str(prim.GetPath())
        self.selected = selected
        self.value_model = ui.SimpleStringModel(self.path)

    def __repr__(self):
        return f'"{self.path}"'


class ItemInstancesMeshGroup(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, instance_prims: List["Usd.Prim"], selected_paths: List[str]):
        super().__init__()
        self.display = "Instances"
        self.instances = [
            ItemInstanceMesh(instance_prim, str(instance_prim.GetPath()) in selected_paths)
            for instance_prim in instance_prims
        ]
        self.value_model = ui.SimpleStringModel(self.display)

    def __repr__(self):
        return f'"{self.display}"'


class ItemAddNewReferenceFileMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self):
        super().__init__()
        self.display = "Add new reference..."
        self.value_model = ui.SimpleStringModel(self.display)

    def __repr__(self):
        return f'"{self.display}"'


class ItemReferenceFileMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", reference_file_path: str):
        super().__init__()
        self.prim = prim
        self.path = reference_file_path
        self.value_model = ui.SimpleStringModel(self.path)

    def __repr__(self):
        return f'"{self.path}"'


class ItemMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", instance_prims: List["Usd.Prim"], selected_paths: List[str]):
        super().__init__()
        self.prim = prim
        self.path = str(prim.GetPath())
        self.value_model = ui.SimpleStringModel(self.path)

        self.add_new_reference_item = ItemAddNewReferenceFileMesh()
        self.instance_group_item = ItemInstancesMeshGroup(instance_prims, selected_paths)
        self.reference_items = [
            ItemReferenceFileMesh(self.prim, path) for path in self.__reference_file_paths(self.prim)
        ]

    @staticmethod
    def __reference_file_paths(prim) -> List[str]:
        prim_paths = []
        for prim_spec in prim.GetPrimStack():
            items = prim_spec.referenceList.prependedItems
            for item in items:
                prim_paths.append(str(item.assetPath))

        return prim_paths

    def __repr__(self):
        return f'"{self.path}"'


class ListModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self, context):
        super().__init__()
        self.default_attr = {"_stage_event": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.__children = []
        self._context = context
        self._stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="StageEvent"
        )

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self.refresh()

    def __get_mesh_from_path(self, stage, path) -> Optional[str]:
        if path.startswith(constants.MESH_PATH):
            return path
        prim = stage.GetPrimAtPath(path)
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
        stage = self._context.get_stage()
        if not stage:
            return result
        iterator = iter(stage.TraverseAll())
        for prim in iterator:
            ref = self.__get_reference_prims(prim)
            if ref and ref[0] == prim.GetPath():
                continue
            if ref and ref[0] in result and prim not in result[ref[0]]:
                result[ref[0]].append(prim)
            elif ref and ref[0] not in result:
                result[ref[0]] = [prim]
        return result

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
        stage = self._context.get_stage()
        if stage:
            paths = self._context.get_selection().get_selected_prim_paths()
            if paths:
                instances_data = self.__get_instances_by_mesh()
                meshes = {}
                for path in paths:
                    # first, we try to find the mesh_ from the selection
                    mesh = self.__get_mesh_from_path(stage, path)
                    if not mesh:
                        continue
                    if mesh in meshes:
                        meshes[mesh].append(path)
                    else:
                        meshes[mesh] = [path]
                for mesh, paths in meshes.items():
                    mesh_prim = stage.GetPrimAtPath(mesh)
                    sdf_mesh_path = mesh_prim.GetPath()
                    mesh_items.append(
                        ItemMesh(
                            mesh_prim,
                            sorted(instances_data.get(sdf_mesh_path, []), key=lambda x: natural_keys(x.GetName())),
                            paths,
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
