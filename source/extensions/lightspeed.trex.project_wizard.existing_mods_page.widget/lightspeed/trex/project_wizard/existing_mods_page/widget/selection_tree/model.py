"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from pathlib import Path
from typing import List, Optional, Union

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .items import ModSelectionItem as _Item  # noqa PLE0402


class ModSelectionModel(ui.AbstractItemModel):
    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_items": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._items = []

        self.__on_item_dropped = _Event()

    def refresh(self, paths: List[Path]) -> None:
        """Refresh the model item with a given list of mod paths"""
        self._items = [_Item(p) for p in paths]
        self._item_changed(None)

    def find_item(self, path: str) -> Optional[_Item]:
        """Find an item based on its path"""
        for item in self._items:
            if str(item) == path:
                return item
        return None

    def insert_item(self, path: str, index: int) -> None:
        """Remove an item from the model"""
        item = _Item(Path(path))
        # Inserting at -1 doesn't insert at the end so append instead
        if index < 0:
            self._items.append(item)
        else:
            self._items.insert(index, item)
        self._item_changed(None)

    def remove_item(self, path: str) -> None:
        """Remove an item from the model"""
        item = self.find_item(path)
        if not item:
            return
        self._items.remove(item)
        self._item_changed(None)

    def get_item_children(self, item: Optional[_Item]) -> List[_Item]:
        return self._items if item is None else []

    def get_item_value_model_count(self, _) -> int:
        return 1

    def get_drag_mime_data(self, item: _Item) -> str:
        return str(item)

    def drop_accepted(
        self, _item_target: Optional[_Item], item_source: Union[str, _Item], _drop_location: int = -1
    ) -> bool:
        return bool(item_source)

    def drop(self, _item_target: Optional[_Item], item_source: Union[str, _Item], drop_location: int = -1) -> None:
        # If moving the item, remove the old item
        if drop_location > -1:
            self.remove_item(str(item_source))
        else:
            # Don't add an already existing item again
            for item in self._items:
                if str(item) == str(item_source):
                    return

        self.insert_item(str(item_source), drop_location)
        self.on_item_dropped(str(item_source))

    def on_item_dropped(self, path: str):
        """
        Trigger the "on_item_dropped" event
        """
        self.__on_item_dropped(path)

    def subscribe_item_dropped(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_dropped, function)

    def destroy(self):
        _reset_default_attrs(self)
