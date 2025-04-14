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
from contextlib import nullcontext
from typing import List, Optional

import omni.usd
from omni.flux.bookmark_tree.widget import (
    BookmarkCollectionItem,
    BookmarkCollectionModel,
    BookmarkItem,
    ComponentTypes,
    CreateBookmarkItem,
)
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit import app, commands, undo

# Required to register commands
from omni.kit.core.collection import commands as _usd_commands  # noqa F401
from pxr import Usd

from .extension import get_usd_listener_instance as _get_usd_listener_instance


class UsdBookmarkCollectionModel(BookmarkCollectionModel):
    def __init__(self, context_name: str = ""):
        super().__init__()
        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "_stage": None,
            "_stage_event": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._usd_listener = _get_usd_listener_instance()
        self._context_name = context_name
        self._context = omni.usd.get_context(context_name)

        self._stage = self._context.get_stage()
        self._stage_event = None

    @property
    def stage(self):
        """
        Get the model's stage. Used by the USD Listener.
        """
        return self._stage

    def refresh(self):
        """
        Refresh the model on the next frame asynchronously.
        """
        asyncio.ensure_future(self._refresh_async())

    def enable_listeners(self, value):
        """
        Enable USD listeners and refresh the model.

        Args:
            value: Whether the listeners should be enabled or disabled
        """
        if value:
            self._usd_listener.add_model(self)
            self._stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
                self.__on_stage_event, name="StageEvent"
            )
            self._stage = self._context.get_stage()
            self.refresh()
        else:
            self._usd_listener.remove_model(self)
            self._stage_event = None

    def create_collection(
        self, collection_name: str, parent: Optional[BookmarkCollectionItem], use_undo_group: bool = True
    ):
        """
        Create a bookmark collection. Will also create the bookmark prim if it doesn't already exist.

        Args:
            collection_name: The name of the collection to create. This is not guaranteed to be the final collection
                             name as all names must be unique and the command enforces that condition.
            parent: The parent collection item. The collection will be added as a child of the parent upon creation.
            use_undo_group: Whether an undo group should be used or not.
        """
        if not self.stage:
            return None
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            # Allow undoing the command
            with undo.group() if use_undo_group else nullcontext():
                # If the base prim doesn't already exist, create it
                path = self.get_bookmarks_base_path()
                prim = self.stage.GetPrimAtPath(path)
                if not prim.IsValid():
                    commands.execute(
                        "CreatePrimCommand",
                        prim_path=path,
                        prim_type="Scope",
                        select_new_prim=False,
                        context_name=self._context_name,
                    )
                # Create the collection
                _, collection_path = commands.execute(
                    "CreateCollection",
                    prim_path=path,
                    collection_name=collection_name,
                    usd_context_name=self._context_name,
                )
                # Set the expansion rule to not automatically include children
                Usd.CollectionAPI.GetCollection(self._stage, collection_path).CreateExpansionRuleAttr("explicitOnly")
                # Add the collection to the parent collection
                if parent is not None:
                    self.add_item_to_collection(collection_path, parent.data, False)
                return collection_path

    def delete_collection(
        self, collection_path: str, parent: Optional[BookmarkCollectionItem], use_undo_group: bool = True
    ):
        """
        Delete a bookmark collection and all its content. Will also recursively delete any child collection.

        Args:
            collection_path: The prim path of the collection to delete.
            parent: The parent collection item. The collection will be removed from the children of the parent.
            use_undo_group: Whether an undo group should be used or not.
        """
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            with undo.group() if use_undo_group else nullcontext():
                if parent is not None:
                    self.remove_item_from_collection(collection_path, parent.data)
                # Delete every child collection
                collection = Usd.CollectionAPI.GetCollection(self.stage, collection_path)
                for target in collection.GetIncludesRel().GetTargets():
                    if Usd.CollectionAPI.IsCollectionAPIPath(target):
                        # Don't care about the parent since it will be deleted
                        self.delete_collection(target, None, False)
                # Delete the actual collection
                commands.execute(
                    "DeleteCollection", collection_path=collection_path, usd_context_name=self._context_name
                )

    def rename_collection(
        self,
        old_collection_path: str,
        new_collection_name: str,
        parent: Optional[BookmarkCollectionItem],
        use_undo_group: bool = True,
    ):
        """
        Rename a bookmark collection. Will also update parent collections.

        Args:
            old_collection_path: The prim path of the collection to rename.
            new_collection_name: The new name the collection should use
            parent: The parent collection item. This must be set in order for the parent collection to have the updated
                    path of the collection in its includes.
            use_undo_group: Whether an undo group should be used or not.
        """
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            with undo.group() if use_undo_group else nullcontext():
                _, new_collection_path = commands.execute(
                    "RenameCollection",
                    old_collection_path=old_collection_path,
                    new_collection_name=new_collection_name,
                    usd_context_name=self._context_name,
                )
                if parent is not None:
                    self.remove_item_from_collection(old_collection_path, parent.data, False)
                    self.add_item_to_collection(new_collection_path, parent.data, False)

    def clear_collection(self, collection_path: str, use_undo_group: bool = True):
        """
        Clear a bookmark collection of all its content.

        Args:
            collection_path: The prim path of the collection to clear.
            use_undo_group: Whether an undo group should be used or not.
        """
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            with undo.group() if use_undo_group else nullcontext():
                collection_item = self.find_item(collection_path, lambda item, data: item.data == data)
                if collection_item.component_type != ComponentTypes.bookmark_collection.value:
                    return
                for child in collection_item.children:
                    if child.component_type == ComponentTypes.bookmark_collection.value:
                        self.clear_collection(child.data, use_undo_group=False)
                        self.delete_collection(child.data, collection_item, use_undo_group=False)
                commands.execute(
                    "ClearCollection", collection_path=collection_path, usd_context_name=self._context_name
                )

    def add_item_to_collection(self, prim_path: str, collection_path: str, use_undo_group: bool = True):
        """
        Add an item to an existing collection.

        Args:
            prim_path: The prim path of the item to add.
            collection_path: The prim path of the collection to add the item to.
            use_undo_group: Whether an undo group should be used or not.
        """
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            with undo.group() if use_undo_group else nullcontext():
                commands.execute(
                    "AddItemToCollection",
                    path_to_add=prim_path,
                    collection_path=collection_path,
                    usd_context_name=self._context_name,
                )

    def remove_item_from_collection(self, prim_path: str, collection_path: str, use_undo_group: bool = True):
        """
        Remove an item to an existing collection.

        Args:
            prim_path: The prim path of the item to remove.
            collection_path: The prim path of the collection to remove the item from.
            use_undo_group: Whether an undo group should be used or not.
        """
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            with undo.group() if use_undo_group else nullcontext():
                commands.execute(
                    "RemoveItemFromCollection",
                    prim_or_prop_path=prim_path,
                    collection_path=collection_path,
                    usd_context_name=self._context_name,
                )

    def get_active_items(self) -> List:
        """
        Get the list of items currently selected in the viewport.
        """
        return list(set(self._context.get_selection().get_selected_prim_paths()))

    def set_active_items(self, items):
        """
        Set the list of items selected in the viewport.

        This will only select bookmark item elements in the viewport (no collections)
        """
        bookmark_items = set(filter(lambda i: (i.component_type == ComponentTypes.bookmark_item.value), items))
        self._context.get_selection().set_selected_prim_paths([i.data for i in bookmark_items], True)

    def get_bookmarks_base_path(self):
        return f"{str(self.stage.GetDefaultPrim().GetPath()) if self.stage.HasDefaultPrim() else ''}/Bookmarks"

    @omni.usd.handle_exception
    async def _refresh_async(self):
        # Wait for 1 frame before rebuilding the UI to make sure all USD data is up-to-date
        await app.get_app().next_update_async()
        if not self.stage:
            return
        with Usd.EditContext(self.stage, self.stage.GetRootLayer()):
            self.set_items(self._get_items_from_usd())

    def _get_items_from_usd(self):
        items = []
        if self.stage is not None:
            prim = self.stage.GetPrimAtPath(self.get_bookmarks_base_path())
            if prim.IsValid():
                for collection in Usd.CollectionAPI.GetAllCollections(prim):
                    items.append(self.__build_collection_item(collection))
                items = self.__remove_children_from_root(items)
                items.sort(key=lambda i: i.title)
        # always add the "create" button at the end
        create_item = CreateBookmarkItem(self._on_create_item_clicked)
        items.append(create_item)
        return items

    def __build_collection_item(self, collection):
        children = []
        for target in collection.GetIncludesRel().GetTargets():
            if Usd.CollectionAPI.IsCollectionAPIPath(target):
                children.append(self.__build_collection_item(Usd.CollectionAPI.GetCollection(self.stage, target)))
            else:
                parts = str(target).split("/")
                if len(parts) < 1:
                    continue
                children.append(BookmarkItem(parts[-1], str(target)))

        return BookmarkCollectionItem(
            collection.GetName(),
            data=str(collection.GetCollectionPath()),
            children=children,
            on_mouse_double_clicked_callback=self._on_bookmark_collection_double_clicked,
        )

    def __remove_children_from_root(self, items: List[BookmarkCollectionItem]) -> List[BookmarkCollectionItem]:
        filtered_items = []
        for item in items:
            child = self.__find_usd_item(item.data)
            if child is None:
                filtered_items.append(item)
        return filtered_items

    def __find_usd_item(self, path: str, parent: Usd.CollectionAPI = None, find_root_items: bool = False) -> str:
        found = None
        collection = []
        prim = self.stage.GetPrimAtPath(self.get_bookmarks_base_path())
        if parent is not None:
            for target in parent.GetIncludesRel().GetTargets():
                if Usd.CollectionAPI.IsCollectionAPIPath(target):
                    collection.append(Usd.CollectionAPI.GetCollection(self.stage, target))
        else:
            collection = Usd.CollectionAPI.GetAllCollections(prim)
        for item in collection:
            found = item if (find_root_items or parent is not None) and str(item.GetCollectionPath()) == path else None
            if found is None:
                found = self.__find_usd_item(path, item)
            if found is not None:
                break
        return found

    def __on_stage_event(self, event):
        if event.type != int(omni.usd.StageEventType.SELECTION_CHANGED):
            return
        self._on_active_items_changed(self.get_active_items())

    def destroy(self):
        if self._usd_listener is not None:
            self._usd_listener.remove_model(self)
            self._usd_listener = None
        _reset_default_attrs(self)
