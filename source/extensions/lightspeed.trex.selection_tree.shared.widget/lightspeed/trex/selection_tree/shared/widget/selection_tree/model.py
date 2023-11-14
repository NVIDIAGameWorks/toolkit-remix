"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import concurrent.futures
import math
import multiprocessing
import re
import typing
from typing import Dict, List, Optional, Tuple, Type, Union

import carb.events
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.kit.usd.layers import LayerEventType, get_layer_event_payload, get_layers
from pxr import Usd, UsdGeom, UsdLux

from .listener import USDListener as _USDListener

if typing.TYPE_CHECKING:
    from pxr import Sdf

HEADER_DICT = {0: "Path"}


class ItemInstanceMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", parent: "ItemInstancesMeshGroup"):
        super().__init__()
        self._parent = parent
        self._prim = prim
        self._path = str(prim.GetPath())
        self._value_model = ui.SimpleStringModel(self._path)

    @property
    def parent(self):
        return self._parent

    @property
    def prim(self):
        return self._prim

    @property
    def path(self):
        return self._path

    @property
    def value_model(self):
        return self._value_model

    def __repr__(self):
        return f'"{self.path}"'


class ItemInstancesMeshGroup(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, instance_prims: List["Usd.Prim"], parent: "ItemMesh"):
        super().__init__()
        self._parent = parent
        self._display = "Instance(s)"
        self._instances = [ItemInstanceMesh(instance_prim, self) for instance_prim in instance_prims]
        self._value_model = ui.SimpleStringModel(self._display)

    @property
    def parent(self):
        return self._parent

    @property
    def display(self):
        return self._display

    @property
    def instances(self):
        return self._instances

    @property
    def value_model(self):
        return self._value_model

    def __repr__(self):
        return f'"{self.display}"'


class ItemLiveLightGroup(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, parent: "ItemMesh", context_name: str):
        super().__init__()
        self._parent = parent
        self._context_name = context_name
        self._display = "Stage light(s)"
        self._lights = [
            ItemPrim(child, None, self, context_name, from_live_light_group=True) for child in self.get_live_lights()
        ]
        self._value_model = ui.SimpleStringModel(self._display)

    def get_live_lights(self) -> List[Usd.Prim]:
        """Get lights that are not from a ref"""
        core = _AssetReplacementsCore(self._context_name)
        return core.get_children_from_prim(self.parent.prim, only_prim_not_from_ref=True, level=1, skip_remix_ref=True)

    @property
    def parent(self):
        return self._parent

    @property
    def display(self):
        return self._display

    @property
    def lights(self):
        return self._lights

    @property
    def value_model(self):
        return self._value_model

    def __repr__(self):
        return f'"{self.display}"'


class ItemAddNewReferenceFileMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", parent: "ItemMesh"):
        super().__init__()
        self._parent = parent
        self._prim = prim
        self._display = "Add new reference..."
        self._value_model = ui.SimpleStringModel(self._display)

    @property
    def parent(self):
        return self._parent

    @property
    def prim(self):
        return self._prim

    @property
    def display(self):
        return self._display

    @property
    def value_model(self):
        return self._value_model

    def __repr__(self):
        return f'"{self.display}"'


class ItemAddNewLiveLight(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", parent: "ItemMesh"):
        super().__init__()
        self._parent = parent
        self._prim = prim
        self._display = "Add new stage light..."
        self._value_model = ui.SimpleStringModel(self._display)

    @property
    def parent(self):
        return self._parent

    @property
    def prim(self):
        return self._prim

    @property
    def display(self):
        return self._display

    @property
    def value_model(self):
        return self._value_model

    def __repr__(self):
        return f'"{self.display}"'


class ItemPrim(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(
        self,
        prim: "Usd.Prim",
        reference_item: Optional["ItemReferenceFileMesh"],
        parent: Union["ItemPrim", "ItemReferenceFileMesh"],
        context_name: str,
        from_live_light_group: bool = False,
    ):
        super().__init__()
        self._parent = parent
        self._reference_item = reference_item
        self._prim = prim
        self._from_live_light_group = from_live_light_group
        self._path = str(prim.GetPath())
        self._value_model = ui.SimpleStringModel(self._path)
        core = _AssetReplacementsCore(context_name)
        children = core.filter_imageable_prims(self._prim.GetChildren())
        scope_without = core.get_scope_prims_without_imageable_children(children)
        self._child_prim_items = [
            ItemPrim(child, reference_item, self, context_name, from_live_light_group=from_live_light_group)
            for child in children
            if child not in scope_without
        ]

    @property
    def from_live_light_group(self):
        return self._from_live_light_group

    def is_usd_light(self):
        return self._prim.HasAPI(UsdLux.LightAPI) if hasattr(UsdLux, "LightAPI") else self._prim.IsA(UsdLux.Light)

    @property
    def reference_item(self):
        return self._reference_item

    @property
    def parent(self):
        return self._parent

    @property
    def prim(self):
        return self._prim

    @property
    def path(self):
        return self._path

    @property
    def value_model(self):
        return self._value_model

    @property
    def child_prim_items(self):
        return self._child_prim_items

    def is_mesh(self) -> bool:
        return bool(self.prim.IsA(UsdGeom.Mesh))

    def is_geomsubset(self) -> bool:
        return bool(self.prim.IsA(UsdGeom.Subset))

    def is_xformable(self) -> bool:
        return bool(UsdGeom.Xformable(self.prim))

    def is_scope(self) -> bool:
        return bool(UsdGeom.Scope(self.prim))

    def __repr__(self):
        return f'"{self.path}"'


class ItemReferenceFileMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(
        self,
        prim: "Usd.Prim",
        ref: "Sdf.Reference",
        layer: "Sdf.Layer",
        ref_index: int,
        size_ref_index: int,
        parent: "ItemMesh",
        context_name: str,
    ):
        super().__init__()
        self._parent = parent
        self._prim = prim
        self._ref = ref
        self._path = str(ref.assetPath)
        self._layer = layer
        self._ref_index = ref_index
        self._size_ref_index = size_ref_index
        self._value_model = ui.SimpleStringModel(self._path)
        core = _AssetReplacementsCore(context_name)
        children = core.get_prim_from_ref_items([self], [self], only_imageable=True, level=1)
        scope_without = core.get_scope_prims_without_imageable_children(children)
        # we ignore Looks scopes
        self._child_prim_items = [
            ItemPrim(child, self, self, context_name)
            for child in children
            if child not in scope_without and not child.GetAttribute(constants.IS_REMIX_REF_ATTR).IsValid()
        ]

    @property
    def parent(self):
        return self._parent

    @property
    def prim(self):
        return self._prim

    @property
    def ref(self):
        return self._ref

    @property
    def path(self):
        return self._path

    @property
    def layer(self):
        return self._layer

    @property
    def ref_index(self):
        return self._ref_index

    @property
    def value_model(self):
        return self._value_model

    @property
    def size_ref_index(self):
        return self._size_ref_index

    @property
    def child_prim_items(self):
        return self._child_prim_items

    def __repr__(self):
        return f'"{self.path}"'


class ItemMesh(ui.AbstractItem):
    """Item of the model that represent a mesh"""

    def __init__(self, prim: "Usd.Prim", instance_prims: List["Usd.Prim"], context_name: str):
        super().__init__()
        self._prim = prim
        self._path = str(prim.GetPath())
        self._value_model = ui.SimpleStringModel(self._path)

        self._add_new_reference_item = ItemAddNewReferenceFileMesh(self._prim, self)
        self._add_new_live_light = ItemAddNewLiveLight(self._prim, self)
        self._live_light_group = ItemLiveLightGroup(self, context_name)
        # instance also for light, to have a selected itme to show properties
        self._instance_group_item = ItemInstancesMeshGroup(instance_prims, self)
        prim_paths, total_ref = self.__reference_file_paths(self._prim)
        self._reference_items = [
            ItemReferenceFileMesh(_prim, ref, layer, i, total_ref, self, context_name)
            for _prim, ref, layer, i in prim_paths
        ]

    def is_light(self):
        regex_pattern = re.compile(constants.REGEX_LIGHT_PATH)
        return bool(regex_pattern.match(self._path))

    def is_mesh(self) -> bool:
        regex_pattern = re.compile(constants.REGEX_MESH_PATH)
        return bool(regex_pattern.match(self._path))

    @property
    def prim(self):
        return self._prim

    @property
    def path(self):
        return self._path

    @property
    def value_model(self):
        return self._value_model

    @property
    def add_new_reference_item(self):
        return self._add_new_reference_item

    @property
    def add_new_live_light(self):
        return self._add_new_live_light

    @property
    def live_light_group(self):
        return self._live_light_group

    @property
    def instance_group_item(self):
        return self._instance_group_item

    @property
    def reference_items(self):
        return self._reference_items

    @staticmethod
    def __reference_file_paths(prim) -> Tuple[List[Tuple["Usd.Prim", "Sdf.Reference", "Sdf.Layer", int]], int]:
        prim_paths = []
        ref_and_layers = omni.usd.get_composed_references_from_prim(prim, False)
        i = 0
        for (ref, layer) in ref_and_layers:
            if not ref.assetPath:
                continue
            prim_paths.append((prim, ref, layer, i))
            i += 1

        # it can happen that we added the same reference multiple time. But USD can't do that.
        # As a workaround, we had to create a xform child and add the reference to it.
        # Check the children and find the attribute that define that
        for child in prim.GetChildren():
            is_remix_ref = child.GetAttribute(constants.IS_REMIX_REF_ATTR)
            if is_remix_ref.IsValid():
                ref_and_layers = omni.usd.get_composed_references_from_prim(child, False)
                for (ref, layer) in ref_and_layers:
                    if not ref.assetPath:
                        continue
                    prim_paths.append((child, ref, layer, i))
                    i += 1

        return prim_paths, i

    def __repr__(self):
        return f'"{self.path}"'


class ListModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self, context_name):
        super().__init__()
        self.default_attr = {"_stage_event": None, "_usd_listener": None, "_layer_event": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.__children = []
        self.__children_last_get_all_items = []
        self.__children_last_get_all_items_last_result = []
        self.__children_last_get_all_items_by_type = []
        self.__children_last_get_all_items_by_type_result = {}
        self._stage = None
        self._ignore_refresh = False
        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)
        self._stage_event = None
        self._layer_event = None
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
            event_stream = get_layers().get_event_stream()
            self._layer_event = event_stream.create_subscription_to_pop(self._on_layer_event, name="layer events")
        else:
            self._usd_listener.remove_model(self)
            self._stage_event = None

    def _on_layer_event(self, event: carb.events.IEvent):
        temp = get_layer_event_payload(event)
        if temp.event_type in [
            LayerEventType.SUBLAYERS_CHANGED,
            LayerEventType.MUTENESS_STATE_CHANGED,
            LayerEventType.MUTENESS_SCOPE_CHANGED,
        ]:
            self.refresh()
            if self._ignore_refresh:
                self._ignore_refresh = False

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            self.refresh()
            if self._ignore_refresh:
                self._ignore_refresh = False

    def __get_prototype_from_path(self, path) -> Optional[str]:
        if path.startswith(constants.MESH_PATH) or path.startswith(constants.LIGHT_PATH):
            return path
        prim = self.stage.GetPrimAtPath(path)
        if not prim.IsValid():
            return None
        root_node = prim.GetPrimIndex().rootNode
        if not root_node:
            return None
        children = root_node.children
        if not children:
            return None
        return str(children[0].path)

    @staticmethod
    def __get_reference_prims(prims) -> Dict["Usd.Prim", List["Sdf.Path"]]:
        prim_paths = {}
        regex_pattern = re.compile(constants.REGEX_LIGHT_PATH)
        for prim in prims:
            if regex_pattern.match(str(prim.GetPath())):
                prim_paths[prim] = [prim.GetPath()]
            else:
                for prim_spec in prim.GetPrimStack():
                    items = prim_spec.referenceList.prependedItems
                    for item in items:
                        if not item.primPath:
                            continue
                        if prim in prim_paths:
                            prim_paths[prim].append(item.primPath)
                        else:
                            prim_paths[prim] = [item.primPath]

        return prim_paths

    def __get_model_from_prototype_path(self, path):
        if not path.startswith(constants.MESH_PATH) and not path.startswith(constants.LIGHT_PATH):
            return None
        prim = self.stage.GetPrimAtPath(path)
        if not prim.IsValid():
            return None
        regex_pattern = re.compile(constants.REGEX_MESH_PATH)
        if regex_pattern.match(prim.GetName()):
            return path
        regex_pattern = re.compile(constants.REGEX_LIGHT_PATH)
        if regex_pattern.match(prim.GetName()):
            return path
        # get parent
        parent = prim.GetParent()
        if not parent or not parent.IsValid():
            return None
        return self.__get_model_from_prototype_path(str(parent.GetPath()))

    def __get_instances_by_mesh(self, paths: List[str]) -> Dict["Sdf.Path", List["Usd.Prim"]]:
        if not self.stage:
            return {}

        iterator = list(iter(Usd.PrimRange.Stage(self.stage, Usd.PrimIsActive & Usd.PrimIsDefined & Usd.PrimIsLoaded)))

        # extract hashes from paths
        hashes = set()
        regex_inst_pattern = re.compile(constants.REGEX_HASH)
        for path in paths:
            match = regex_inst_pattern.match(path)
            if not match:
                continue
            hashes.add(match.groups()[2])

        result = {}
        futures = []
        cpu_count = multiprocessing.cpu_count()
        # we can use threadpool here because we are just reading the stage
        # Use exact number of cpu count as max worker: this is faster that letting Python doing it
        # Divide the iter by group that fit the  max worker
        with concurrent.futures.ThreadPoolExecutor(max_workers=cpu_count) as executor:
            to_send = []
            size_iter = len(iterator)
            group_size = math.ceil(size_iter / cpu_count)
            for i, prim in enumerate(iterator):
                match = regex_inst_pattern.match(prim.GetName())
                if not match or match.groups()[2] not in hashes:
                    if i == size_iter - 1 and to_send:
                        futures.append(executor.submit(self.__get_reference_prims, to_send))
                    continue
                if i == size_iter - 1 and to_send:
                    futures.append(executor.submit(self.__get_reference_prims, to_send))
                    continue
                to_send.append(prim)
                if len(to_send) == group_size:
                    futures.append(executor.submit(self.__get_reference_prims, to_send))
                    to_send = []

            regex_pattern = re.compile(constants.REGEX_LIGHT_PATH)
            for future in concurrent.futures.as_completed(futures):
                refs = future.result()
                for prim, ref in refs.items():
                    if ref and ref[0] == prim.GetPath() and not regex_pattern.match(str(prim.GetPath())):
                        continue
                    if ref and ref[0] in result and prim not in result[ref[0]]:
                        result[ref[0]].append(prim)
                    elif ref and ref[0] not in result:
                        result[ref[0]] = [prim]
        return result

    def select_prim_paths(self, paths: List[Union[str]]):
        current_selection = self._context.get_selection().get_selected_prim_paths()
        if sorted(paths) != sorted(current_selection):
            self._ignore_refresh = True
            self._context.get_selection().set_selected_prim_paths(paths, True)

    @_ignore_function_decorator(attrs=["_ignore_refresh"])
    def refresh(self):
        """Refresh the list"""

        split_re = re.compile(r"(\d+)")

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
            return [atoi(c) for c in split_re.split(text)]

        mesh_items = []
        if self.stage:
            paths = self._context.get_selection().get_selected_prim_paths()
            if paths:
                instances_data = self.__get_instances_by_mesh(paths)
                meshes = []
                for path in paths:
                    # first, we try to find the mesh_ from the selection
                    mesh = self.__get_prototype_from_path(path)
                    if not mesh or mesh in meshes:
                        continue
                    mesh_model = self.__get_model_from_prototype_path(mesh)
                    if not mesh_model or mesh_model in meshes:
                        continue
                    meshes.append(mesh_model)
                for mesh in meshes:
                    mesh_prim = self.stage.GetPrimAtPath(mesh)
                    sdf_mesh_path = mesh_prim.GetPath()
                    mesh_items.append(
                        ItemMesh(
                            mesh_prim,
                            sorted(instances_data.get(sdf_mesh_path, []), key=lambda x: natural_keys(x.GetName())),
                            self._context_name,
                        )
                    )
        self.__children = mesh_items
        self._item_changed(None)

    def get_item_children_type(
        self,
        item_type: Type[
            Union[
                ItemMesh,
                ItemReferenceFileMesh,
                ItemAddNewReferenceFileMesh,
                ItemInstancesMeshGroup,
                ItemInstanceMesh,
                ItemPrim,
            ]
        ],
    ) -> List[
        Union[
            ItemMesh,
            ItemReferenceFileMesh,
            ItemAddNewReferenceFileMesh,
            ItemInstancesMeshGroup,
            ItemInstanceMesh,
            ItemPrim,
        ]
    ]:
        result = []

        def get_children(_items):
            for item in _items:
                if isinstance(item, item_type):
                    result.append(item)
                get_children(self.get_item_children(item))

        get_children(self.__children)
        return result

    def get_first_item_parent_type(
        self,
        item: Union[
            ItemMesh,
            ItemReferenceFileMesh,
            ItemAddNewReferenceFileMesh,
            ItemInstancesMeshGroup,
            ItemInstanceMesh,
            ItemPrim,
        ],
        item_type: Type[
            Union[
                ItemMesh,
                ItemReferenceFileMesh,
                ItemAddNewReferenceFileMesh,
                ItemInstancesMeshGroup,
                ItemInstanceMesh,
                ItemPrim,
            ]
        ],
    ) -> Optional[
        Union[
            ItemMesh,
            ItemReferenceFileMesh,
            ItemAddNewReferenceFileMesh,
            ItemInstancesMeshGroup,
            ItemInstanceMesh,
            ItemPrim,
        ]
    ]:
        def get_parent(_item):
            if isinstance(_item, item_type):
                return _item
            if hasattr(_item, "parent"):
                return get_parent(_item.parent)
            return None

        return get_parent(item)

    def get_all_items(self):
        # opti cache
        if self.__children == self.__children_last_get_all_items:
            return self.__children_last_get_all_items_last_result
        result = []

        def get_children(_items):
            for item in _items:
                result.append(item)
                get_children(self.get_item_children(item))

        get_children(self.__children)
        self.__children_last_get_all_items = self.__children
        self.__children_last_get_all_items_last_result = result
        return result

    def get_all_items_by_type(self):
        # opti cache
        if self.__children == self.__children_last_get_all_items_by_type:
            return self.__children_last_get_all_items_by_type_result
        result = {}

        def get_children(_items):
            for item in _items:
                typ = type(item)
                if typ not in result:
                    result[typ] = []
                result[typ].append(item)
                get_children(self.get_item_children(item))

        get_children(self.__children)
        self.__children_last_get_all_items_by_type = self.__children
        self.__children_last_get_all_items_by_type_result = result
        return result

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__children
        if isinstance(item, ItemMesh):
            result = []
            if not item.is_light():
                result = item.reference_items + [item.add_new_reference_item]
            if item.live_light_group and item.live_light_group.lights:
                result.append(item.live_light_group)
            result.append(item.add_new_live_light)
            # instance also for light, to have a selected itme to show properties
            result.append(item.instance_group_item)
            return result
        if isinstance(item, ItemLiveLightGroup):
            return item.lights
        if isinstance(item, ItemInstancesMeshGroup):
            return item.instances
        if isinstance(item, (ItemReferenceFileMesh, ItemPrim)):
            return item.child_prim_items
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
