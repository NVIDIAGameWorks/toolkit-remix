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

import abc
from typing import Any, Callable, List, Optional, Union

from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription

from .item_model import BookmarkCollectionItem, ComponentTypes, ItemBase


class BookmarkCollectionModel(ui.AbstractItemModel):
    """
    The model's implementation allows the addition of individual items but permanent additions/removals should be done
    through the collection functions (create_collection, add_item_to_collection, etc.) and refresh function to fetch
    the updated data.
    """

    def __init__(self):
        super().__init__()
        self._items = []
        self.__on_active_items_changed = _Event()
        self.__on_bookmark_collection_double_clicked = _Event()
        self.__on_create_item_clicked = _Event()

    # Abstract methods

    @abc.abstractmethod
    def refresh(self) -> None:
        """Force a refresh of the model."""
        pass

    @abc.abstractmethod
    def enable_listeners(self, value: bool) -> None:
        """
        If listeners are required in the model, enable/disable them based on the value given.

        Args:
            value: whether the listeners should be enabled or disabled
        """
        pass

    @abc.abstractmethod
    def create_collection(
        self, collection_name: str, parent: Optional[BookmarkCollectionItem], use_undo_group: bool = True
    ) -> str:
        """
        Create a collection. For USD this can be a *UsdCollection*, for files this can be a folder.

        **Note:** The collection name could differ from the given one if the collection name was already in use.
        A unique name is generated for every entry

        Args:
            collection_name: the name of the collection to be created
            parent: if this is None, the collection will be created as a root item, otherwise it will be created as a
                    child of the parent.
            use_undo_group: Whether a new undo group should be used for the operation

        Returns:
            A path to the created collection.
        """
        pass

    @abc.abstractmethod
    def delete_collection(
        self, collection_key: str, parent: Optional[BookmarkCollectionItem], use_undo_group: bool = True
    ) -> None:
        """
        Delete an existing collection

        Args:
            collection_key: the key of the collection to be deleted
            parent: if this is not None, the item will also be removed from the parent's references
            use_undo_group: Whether a new undo group should be used for the operation
        """
        pass

    @abc.abstractmethod
    def rename_collection(
        self,
        collection_key: str,
        new_collection_name: str,
        parent: Optional[BookmarkCollectionItem],
        use_undo_group: bool = True,
    ) -> None:
        """
        Rename a collection using a new collection name.

        **Note:** The collection name could differ from the given one if the collection name was already in use.
        A unique name is generated for every entry

        Args:
            collection_key: the key of the collection to be renamed
            new_collection_name: the new name to use for the collection
            parent: if this is not None, the item's reference will also be changed in the parent
            use_undo_group: Whether a new undo group should be used for the operation
        """
        pass

    @abc.abstractmethod
    def clear_collection(self, collection_key: str, use_undo_group: bool = True) -> None:
        """
        Clear all the items referenced inside a collection

        Args:
            collection_key: the key of the collection to be cleared
            use_undo_group: Whether a new undo group should be used for the operation
        """
        pass

    @abc.abstractmethod
    def add_item_to_collection(self, item: Any, collection_key: str, use_undo_group: bool = True) -> None:
        """
        Add an item reference to a collection

        Args:
            item: the item to add to the collection
            collection_key: the key of the collection to be renamed
            use_undo_group: Whether a new undo group should be used for the operation
        """
        pass

    @abc.abstractmethod
    def remove_item_from_collection(self, item: Any, collection_key: str, use_undo_group: bool = True) -> None:
        """
        Remove a specific item from a collection

        Args:
            item: the item to remove from the collection
            collection_key: the key of the collection to be renamed
            use_undo_group: Whether a new undo group should be used for the operation
        """
        pass

    @abc.abstractmethod
    def get_active_items(self) -> List:
        """
        Get the currently active item. For USD this could be the selected viewport item, for files this could be the
        currently selected file/folder, etc.

        Returns:
            A list of all active items
        """
        pass

    @abc.abstractmethod
    def set_active_items(self, items: List[ItemBase]) -> None:
        """
        Set the currently active item. For USD this could be the selected viewport item, for files this could be the
        currently selected file/folder, etc.

        Args:
            items: the items to set as active
        """
        pass

    # Implemented methods

    def set_items(self, items: List[ItemBase], parent: Optional[ItemBase] = None) -> None:
        """
        Set the items to be displayed in the tree widget. If the parent argument is set this will set an item's
        children.

        Args:
            items: the items to display in the tree widget
            parent: if this is not None, the parent's children will be set
        """
        if parent is None:
            self._items = items
        else:
            parent.set_children(items)
        self._item_changed(None)

    def clear_items(self, parent: Optional[ItemBase] = None) -> None:
        """
        Clear all the items to be displayed in the tree widget. If the parent argument is set this will clear an item's
        children.

        Args:
            parent: if this is not None, the parent's children will be cleared
        """
        if parent is None:
            self._items.clear()
        else:
            parent.clear_children()
        self._item_changed(None)

    def append_item(
        self, item: ItemBase, parent: Optional[ItemBase] = None, sort: bool = False, force: bool = False
    ) -> None:
        """
        Append an item to display in the tree widget. If the parent argument is set this will append an item to the
        parent's children.

        Args:
            item: the item to append to the tree widget's item list
            parent: if this is not None, the item will be appended to the parent's children
            sort: whether the items should be sorted after the item is appended
            force: if duplicate items should be allowed to be appended
        """
        # don't allow duplicates unless forced
        if not force and item.title in (i.title for i in (self._items if parent is None else parent.children)):
            return
        if parent is None:
            self._items.append(item)
            if sort:
                self._items.sort(key=lambda i: (i.title, i.component_type))
        else:
            parent.append_child(item, sort=sort)
        self._item_changed(None)

    def insert_item(self, item: ItemBase, index: int, parent: Optional[ItemBase] = None, force: bool = False) -> None:
        """
        Insert an item to display in the tree widget at a given index. If the parent argument is set this will insert an
        item in the parent's children.

        Args:
            item: the item to insert in the tree widget's item list
            index: the index at which to insert the item
            parent: if this is not None, the item will be inserted in the parent's children
            force: if duplicate items should be allowed to be inserted
        """
        # don't allow duplicates unless forced
        if not force and item.title in (i.title for i in (self._items if parent is None else parent.children)):
            return
        if parent is None:
            self._items.insert(index, item)
        else:
            parent.insert_child(item, index)
        self._item_changed(None)

    def remove_item(self, item: ItemBase, parent: Optional[ItemBase] = None) -> None:
        """
        Remove an item from the tree widget list. If the parent argument is set this will remove an item from the
        parent's children.

        Args:
            item: the item to remove from the tree widget's item list
            parent: if this is not None, the item will be removed from the parent's children
        """
        if parent is None:
            self._items.remove(item)
        else:
            parent.remove_child(item)
        self._item_changed(None)

    def find_item(self, value, comparison: Callable[[ItemBase, Any], bool], parent: ItemBase = None) -> ItemBase:
        """
        Find an item displayed in the tree widget.

        Args:
            value: value to search for
            comparison: the comparison that should be used to determine if the item is a match or not. Uses the value.
            parent: items will be searched recursively from the parent to the last children. If this is None, the model
                    root will be used as a base.

        Returns:
            The item displayed in the tree widget
        """
        found = None
        collection = parent.children if parent is not None else self._items
        for item in collection:
            found = item if comparison(item, value) else None
            if found is None:
                found = self.find_item(value, comparison, item)
            if found is not None:
                break
        return found

    def get_item_index(self, item: ItemBase, parent: Optional[ItemBase] = None) -> int:
        """
        Get an item's index.

        Args:
            item: item to search for
            parent: items will be searched recursively from the parent to the last children. If this is None, the model
                    root will be used as a base.

        Returns:
            The index of the item displayed in the tree widget
        """
        if parent is None:
            return self._items.index(item)
        return parent.children.index(item)

    def get_items_count(self, parent: Optional[ItemBase] = None) -> int:
        """
        Get the number of items or children.

        Args:
            parent: if this is not None, it will return the number of children in the parent

        Returns:
            The number of items in the model or children in the parent
        """
        return len(self._items if parent is None else parent.children)

    def get_item_children(self, parent: Optional[ItemBase] = None, recursive: bool = False) -> List[ItemBase]:
        """
        Get the model's items or item's children.

        Args:
            parent: if this is not None, it will return the parent's children
            recursive: whether the items should be listed recursively or only top-level

        Returns:
            The items in the model or children in the parent
        """
        items = self._items if parent is None else parent.children
        if not recursive:
            return items

        children = []
        for item in items:
            children = children + self.get_item_children(item, True)
        return items + children

    def get_item_value_model_count(self, item: ItemBase) -> int:
        return 1

    def get_drag_mime_data(self, item: ItemBase) -> str:
        return str(item)

    def drop_accepted(self, item_target: ItemBase, item_source: Union[str, ItemBase], drop_location: int = -1) -> bool:
        if str(item_source) == str(item_target):
            return False
        return (item_target is None) or (
            item_target is not None and item_target.component_type == ComponentTypes.bookmark_collection.value
        )

    def drop(self, item_target: ItemBase, item_source: Union[str, ItemBase], drop_location: int = -1) -> None:
        source = item_source
        if isinstance(item_source, str):
            source = self.find_item(item_source, lambda item, mime: self.get_drag_mime_data(item) == mime)
        if source is None:
            return
        if source.component_type == ComponentTypes.bookmark_collection.value:
            if source.parent is not None:
                self.remove_item_from_collection(source.data, source.parent.data)
            if item_target is not None:
                self.add_item_to_collection(source.data, item_target.data)
        if source.component_type == ComponentTypes.bookmark_item.value and item_target is not None:
            self.remove_item_from_collection(source.data, source.parent.data)
            self.add_item_to_collection(source.data, item_target.data)

    # Events

    def _on_active_items_changed(self, items: List[str]):
        """Call the event object that has the list of functions"""
        self.__on_active_items_changed(items)

    def subscribe_on_active_items_changed(self, function: Callable):
        """
        Subscribe to the *on_active_items_changed* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_active_items_changed, function)

    def _on_bookmark_collection_double_clicked(self, item: BookmarkCollectionItem):
        """Call the event object that has the list of functions"""
        self.__on_bookmark_collection_double_clicked(item)

    def subscribe_on_bookmark_collection_double_clicked(self, function: Callable):
        """
        Subscribe to the *on_bookmark_collection_double_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_bookmark_collection_double_clicked, function)

    def _on_create_item_clicked(self):
        """Call the event object that has the list of functions"""
        self.__on_create_item_clicked()

    def subscribe_on_create_item_clicked(self, function: Callable):
        """
        Subscribe to the *on_create_item_clicked* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_create_item_clicked, function)

    def destroy(self):
        self._items.clear()
