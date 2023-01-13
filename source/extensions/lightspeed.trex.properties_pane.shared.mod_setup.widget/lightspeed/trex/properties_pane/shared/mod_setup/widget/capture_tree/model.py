"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
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
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from lightspeed.common.constants import MATERIAL_RELATIONSHIP, REGEX_HASH, REGEX_MESH_PATH
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCoreSetup
from omni import ui, usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import async_wrap as _async_wrap
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from pxr import Sdf

HEADER_DICT = {0: "Path", 1: "Progress"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, path, image):
        super().__init__()
        self.path = path
        self.image = image
        self.path_model = ui.SimpleStringModel(self.path)
        self.replaced_items = None
        self.total_items = None

    def __repr__(self):
        return f'"{self.path}"'


class ListModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self, context_name):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_core_capture": None,
            "_core_replacement": None,
            "_stage_event_sub": None,
            "_fetch_task": None,
            "_cancel_token": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._core_capture = _CaptureCoreSetup(context_name)
        self._core_replacement = _ReplacementCoreSetup(context_name)

        self._stage_event_sub = None
        self._fetch_task = None
        self._cancel_token = False
        self.__children = []
        self.__on_progress_updated = _Event()

    def refresh(self, paths: List[Tuple[str, str]]):
        """Refresh the list"""
        self.__children = [Item(path, image) for path, image in sorted(paths, key=lambda x: x[0])]
        self._item_changed(None)

        self.fetch_progress()

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__children
        return []

    def get_item_value_model_count(self, _):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if column_id == 0:
            return item.path_model
        return None

    def cancel_tasks(self):
        if self._fetch_task is not None:
            self._cancel_token = True

    def enable_listeners(self, value: bool):
        if value:
            self._stage_event_sub = (
                usd.get_context(self._context_name)
                .get_stage_event_stream()
                .create_subscription_to_pop(self.__on_stage_event, name="STAGE_CHANGED_SUB")
            )
        else:
            self._stage_event_sub = None

    def fetch_progress(self, items: Optional[List[Item]] = None):
        self.cancel_tasks()
        wrapped_fn = _async_wrap(functools.partial(self.__fetch_progress, items))
        self._fetch_task = asyncio.ensure_future(wrapped_fn())

    def __on_stage_event(self, event):
        if event.type not in [int(usd.StageEventType.CLOSING), int(usd.StageEventType.CLOSED)]:
            return
        self.cancel_tasks()

    def __task_completed(self):
        if self._fetch_task is not None:
            self._fetch_task.cancel()
            self._fetch_task = None
        self._cancel_token = False

    def __fetch_progress(self, items: Optional[List[Item]] = None):
        collection = items if items else self.__children
        # Reset the item state
        for item in collection:
            item.replaced_items = None
            item.total_items = None
        self._progress_updated()
        # Allow cancelling the task after resetting the UI
        if self._cancel_token:
            self.__task_completed()
            return
        # Fetch the replaced hashes
        replaced_items = set()
        for layer in self._core_replacement.get_replaced_hashes().items():
            # Allow cancelling the task for every layer
            if self._cancel_token:
                self.__task_completed()
                return
            replaced_items = replaced_items.union(self.__filter_hashes(layer))
        for item in collection:
            # Allow cancelling the task for every capture item
            if self._cancel_token:
                self.__task_completed()
                return
            # Update the replaced items values
            captured_items = self.__filter_hashes(self._core_capture.get_captured_hashes(item.path))
            item.replaced_items = len(captured_items & replaced_items)
            item.total_items = len(captured_items)
        self._progress_updated()
        # Make sure the cancel is reset
        self.__task_completed()

    def __filter_hashes(self, args: Tuple["Sdf.Layer", Dict[str, "Sdf.Path"]]) -> Set[str]:
        """
        Filter the hashes so that meshes and their associate materials count as a single entry
        """
        layer, hashes = args
        filtered_hashes = set()
        regex_mesh = re.compile(REGEX_MESH_PATH)
        regex_hash = re.compile(REGEX_HASH)
        for prim_hash, prim_path in hashes.items():
            # Allow cancelling the task for every item
            if self._cancel_token:
                break
            # If not a mesh, then no need to group
            if not regex_mesh.match(str(prim_path)):
                filtered_hashes.add(prim_hash)
                continue
            # If prim is a mesh, get the associated material instead to group them up
            mesh_prim = layer.GetPrimAtPath(prim_path)
            if MATERIAL_RELATIONSHIP in mesh_prim.relationships:
                materials = mesh_prim.relationships[MATERIAL_RELATIONSHIP].targetPathList.explicitItems
                # Always take the first material as there should never be more than 1 material here
                match = regex_hash.match(str(materials[0]))
                filtered_hashes.add(match.group(3) if match else prim_hash)
            else:
                filtered_hashes.add(prim_hash)
        return filtered_hashes

    def _progress_updated(self):
        """Call the event object that has the list of functions"""
        self.__on_progress_updated()

    def subscribe_progress_updated(self, func):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_progress_updated, func)

    def destroy(self):
        self.cancel_tasks()
        _reset_default_attrs(self)
