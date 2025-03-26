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
import asyncio
import concurrent
import weakref
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

import carb
import omni.kit.usd.layers as _layers
from omni import usd
from omni.flux.layer_tree.usd.core import LayerCustomData as _LayerCustomData
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.layer_utils import FILE_DIALOG_EXTENSIONS as _FILE_DIALOG_EXTENSIONS
from omni.flux.utils.common.layer_utils import save_layer_as as _save_layer_as
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.widget.tree_widget import TreeModelBase as _TreeModelBase
from omni.kit import commands, undo
from pxr import Sdf

from .item_model import ItemBase, LayerItem


class LayerModel(_TreeModelBase[ItemBase]):
    """
    The model's implementation allows the addition of individual items but these actions should be reserved for
    temporary items (such as a TemporaryLayerItem). Permanent additions/removals should be done through the
    layer functions (create_layer, set_layer_parent, etc.) and refresh function to fetch the updated
    data.
    """

    def __init__(
        self,
        context_name: str = "",
        layer_creation_validation_fn: Optional[Callable[[str, str], bool]] = None,
        layer_creation_validation_failed_callback: Optional[Callable[[str, str], None]] = None,
        layer_import_validation_fn: Optional[Callable[[str, str], bool]] = None,
        layer_import_validation_failed_callback: Optional[Callable[[str, str], None]] = None,
        exclude_remove_fn: Optional[Callable[[], List[str]]] = None,
        exclude_lock_fn: Optional[Callable[[], List[str]]] = None,
        exclude_mute_fn: Optional[Callable[[], List[str]]] = None,
        exclude_edit_target_fn: Optional[Callable[[], List[str]]] = None,
        exclude_add_child_fn: Optional[Callable[[], List[str]]] = None,
        exclude_move_fn: Optional[Callable[[], List[str]]] = None,
    ):
        """
        Args:
            context_name: the context name
            layer_creation_validation_fn: a callback to validate the selected file before it's created
            layer_creation_validation_failed_callback: a callback called when the file creation validation fails.
                                                       Can be used to display popups, log the error, etc.
            layer_import_validation_fn: a callback to validate the selected file before it's imported
            layer_import_validation_failed_callback: a callback called when the file import validation fails.
                                                     Can be used to display popups, log the error, etc.
            exclude_remove_fn: list of layer identifiers to disallow removing
            exclude_lock_fn: list of layer identifiers to disallow locking/unlocking
            exclude_mute_fn: list of layer identifiers to disallow muting/unmuting
            exclude_edit_target_fn: list of layer identifiers to disallow setting as edit target
            exclude_add_child_fn: list of layer identifiers to disallow adding children sublayers
            exclude_move_fn: list of layer identifiers to disallow moving (setting parent or index)
        """

        super().__init__()

        self._items = []
        self._ignore_refresh = False

        self._layer_events = None
        self._stage_events = None

        self._context_name = context_name
        self._context = usd.get_context(self._context_name)
        self.stage = self._context.get_stage()

        self._layer_creation_validation_fn = layer_creation_validation_fn
        self._layer_creation_validation_failed_callback = layer_creation_validation_failed_callback
        self._layer_import_validation_fn = layer_import_validation_fn
        self._layer_import_validation_failed_callback = layer_import_validation_failed_callback

        self._exclude_remove_fn = exclude_remove_fn
        self._exclude_lock_fn = exclude_lock_fn
        self._exclude_mute_fn = exclude_mute_fn
        self._exclude_edit_target_fn = exclude_edit_target_fn
        self._exclude_add_child_fn = exclude_add_child_fn
        self._exclude_move_fn = exclude_move_fn

        self.__on_refresh_started = _Event()
        self.__on_refresh_completed = _Event()

        self.__refresh_task = None

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_items": None,
                "_ignore_refresh": None,
                "_layer_events": None,
                "_stage_events": None,
                "_context_name": None,
                "_context": None,
                "_exclude_lock": None,
                "_exclude_mute": None,
                "_exclude_edit_target": None,
            }
        )
        return default_attr

    # USD methods

    @contextmanager
    def disable_refresh(self, refresh_on_exit: bool = True):
        """
        Disable refresh temporarily
        """
        self._ignore_refresh = True
        try:
            yield
        finally:
            self._ignore_refresh = False
            if refresh_on_exit:
                self.refresh()

    def refresh(self) -> None:
        """Force a refresh of the model."""
        if self.__refresh_task:
            self.__refresh_task.cancel()
        self.__refresh_task = asyncio.ensure_future(self._deferred_refresh())

    def enable_listeners(self, value: bool) -> None:
        """
        If listeners are required in the model, enable/disable them based on the value given.

        Args:
            value: whether the listeners should be enabled or disabled
        """
        if value:
            self._layer_events = (
                _layers.get_layers(self._context)
                .get_event_stream()
                .create_subscription_to_pop(self.__on_layer_events, name="LayerEvent")
            )
            self._stage_events = self._context.get_stage_event_stream().create_subscription_to_pop(
                self.__on_stage_events, name="StageEvent"
            )
            self._context = usd.get_context(self._context_name)
            self.stage = self._context.get_stage()

            self.refresh()
        else:
            self._layer_events = None
            self._stage_events = None

    def create_layer(
        self,
        create_or_insert: bool,
        parent: Optional[LayerItem] = None,
        layer_created_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        **Note:** The layer name could differ from the given one if the layer name was already in use.
        A unique name is generated for every entry

        Args:
            create_or_insert: if true, a layer will be created, otherwise an existing layer is inserted.
            parent: the layer the new layer should be parented to. If null the layer will be parented to the root
            layer_created_callback: callback called after the sublayer is inserted or created.
                                    Receives the path of the created layer as an argument.
        """
        if parent is None:
            parent = self.get_item_children()[0]

        def execute_command(path):
            with undo.group():
                # If the layer is already a sublayer, don't re-add it
                if str(Path(path)) not in [str(Path(i.data["layer"].realPath)) for i in parent.children]:
                    success, new_layer_path = commands.execute(
                        "CreateOrInsertSublayer",
                        layer_identifier=parent.data["layer"].identifier,
                        sublayer_position=-1,
                        new_layer_path=str(path),
                        transfer_root_content=False,
                        create_or_insert=create_or_insert,
                        usd_context=self._context_name,
                    )
                    if success and layer_created_callback is not None:
                        layer_created_callback(new_layer_path)

        if create_or_insert:
            _open_file_picker(
                "Create a new layer file",
                execute_command,
                lambda *args: None,
                apply_button_label="Create",
                current_file=str(Path(parent.data["layer"].realPath).parent),
                file_extension_options=_FILE_DIALOG_EXTENSIONS,
                validate_selection=self._layer_creation_validation_fn,
                validation_failed_callback=self._layer_creation_validation_failed_callback,
            )
        else:
            _open_file_picker(
                "Select an existing layer file",
                execute_command,
                lambda *args: None,
                current_file=str(Path(parent.data["layer"].realPath).parent),
                file_extension_options=[("*.usd*", "USD Files"), *_FILE_DIALOG_EXTENSIONS],
                validate_selection=self._layer_import_validation_fn,
                validation_failed_callback=self._layer_import_validation_failed_callback,
            )

    def delete_layer(self, layer: LayerItem) -> None:
        """
        Delete an existing layer

        Args:
            layer: the layer to be deleted
        """
        # Can't delete the root layer
        if layer.parent is None or layer.data.get("exclude_remove", True):
            return

        commands.execute(
            "RemoveSublayerCommand",
            layer_identifier=layer.parent.data["layer"].identifier,
            sublayer_position=_layers.LayerUtils.get_sublayer_position_in_parent(
                layer.parent.data["layer"].identifier, layer.data["layer"].identifier
            ),
            usd_context=self._context_name,
        )

    def set_authoring_layer(self, layer: LayerItem) -> None:
        """
        Set a new authoring layer

        Args:
            layer: the layer to be saved
        """

        if layer.data.get("locked", True) or layer.data.get("exclude_edit_target", True):
            return

        commands.execute(
            "SetEditTargetCommand",
            layer_identifier=layer.data["layer"].identifier,
            usd_context=self._context_name,
        )
        _layers.LayerUtils.save_authoring_layer_to_custom_data(self.stage)

    def save_layer(self, layer: LayerItem) -> None:
        """
        Persist an existing layer

        Args:
            layer: the layer to be saved
        """
        if not layer.data.get("savable", False):
            return

        layer.data["layer"].Save()
        self.refresh()

    def save_layer_as(self, layer: LayerItem):
        """
        Persist an existing layer in a new file and replace it in the current stage

        Args:
            layer: the layer to be saved
        """
        if not layer.data.get("layer", None):
            return

        # Uses weakref to avoid filepicker hold it's strong reference
        layer_weakref = weakref.ref(layer.data["layer"])

        parent = layer.parent.data["layer"] if layer.parent else None
        parent_weakref = None
        if parent:
            parent_weakref = weakref.ref(parent)

        current_file = None
        if not layer.data["layer"].anonymous:
            current_file = layer.data["layer"].realPath

        _open_file_picker(
            "Save layer as",
            partial(
                _save_layer_as, self._context_name, True, layer_weakref, parent_weakref, self._on_save_layer_as_internal
            ),
            lambda *args: None,
            apply_button_label="Save As",
            current_file=current_file,
            file_extension_options=_FILE_DIALOG_EXTENSIONS,
            validate_selection=self._layer_creation_validation_fn,
            validation_failed_callback=self._layer_creation_validation_failed_callback,
        )

    def export_layer(self, layer: LayerItem):
        """
        Persist an existing layer in a new file but don't replace it in the current stage

        Args:
            layer: the layer to be exported
        """
        _open_file_picker(
            "Export the layer file",
            partial(self._on_export_layer_internal, layer),
            lambda *args: None,
            apply_button_label="Export",
            current_file=str(layer.data["layer"].realPath),
            file_extension_options=_FILE_DIALOG_EXTENSIONS,
            validate_selection=self._layer_creation_validation_fn,
            validation_failed_callback=self._layer_creation_validation_failed_callback,
        )

    def toggle_lock_layer(self, layer: LayerItem) -> None:
        """
        Args:
            layer: the layer to be locked or unlocked
        """
        self.set_lock_layer(layer, not layer.data["locked"])

    def set_lock_layer(self, layer: LayerItem, value: bool) -> None:
        """
        Args:
            layer: the layer to be locked or unlocked
            value: whether to lock or unlock the layer
        """
        if layer.data.get("exclude_lock", True):
            return

        # Quick return if the state is already the same
        if self.is_layer_locked(layer) == value:
            return

        commands.execute(
            "LockLayer",
            layer_identifier=layer.data["layer"].identifier,
            locked=value,
            usd_context=self._context_name,
        )

    def toggle_mute_layer(self, layer: LayerItem) -> None:
        """
        Args:
            layer: the layer to be muted or unmuted
        """
        self.set_mute_layer(layer, layer.data["visible"])

    def set_mute_layer(self, layer: LayerItem, value: bool) -> None:
        """
        Args:
            layer: the layer to be muted or unmuted
            value: whether to mute or unmute the layer
        """
        if layer.data.get("exclude_mute", True) or not layer.data.get("can_toggle_mute", False):
            return

        # Quick return if the state is already the same
        if self.is_layer_muted(layer) == value:
            return

        # Make sure muteness is global to persist state
        _layers.get_layers(self._context).get_layers_state().set_muteness_scope(True)

        # Set the muteness state
        commands.execute(
            "SetLayerMutenessCommand",
            layer_identifier=layer.data["layer"].identifier,
            muted=value,
            usd_context=self._context_name,
        )

    def move_sublayer(self, layer: LayerItem, new_parent: LayerItem, item_position: int = -1) -> None:
        """
        Set a new parent for an existing layer

        Args:
            layer: the layer to be moved
            new_parent: the new layer's parent
            item_position: the index position of the layer
        """
        # Make sure the highest level we can go is under the root layer
        if layer.parent is None or new_parent is None:
            return
        commands.execute(
            "MoveSublayerCommand",
            from_parent_layer_identifier=layer.parent.data["layer"].identifier,
            from_sublayer_position=_layers.LayerUtils.get_sublayer_position_in_parent(
                layer.parent.data["layer"].identifier, layer.data["layer"].identifier
            ),
            to_parent_layer_identifier=new_parent.data["layer"].identifier,
            to_sublayer_position=item_position,
            remove_source=True,
            usd_context=self._context_name,
        )

    def merge_layers(self, layers: List[LayerItem]):
        """
        Merge the overrides located in multiple layers in a single layer. Only the layer with the strongest opinions
        will remain at the end of this operation.

        Args:
            layers: the layers to be merged
        """

        # GetLayerStack returns a list of layers ordered from strongest to weakest. Use that order to sort the selection
        ordered_items = [
            item
            for layer in self.stage.GetLayerStack(False)
            for item in layers
            if layer.identifier == item.data["layer"].identifier
        ]
        with undo.group():
            for i in reversed(range(len(ordered_items))):
                # Destination is the strongest layer in the list
                if i - 1 < 0:
                    return
                src = ordered_items[i]
                dst = ordered_items[i - 1]
                commands.execute(
                    "MergeLayersCommand",
                    dst_parent_layer_identifier=dst.parent.data["layer"].identifier,
                    dst_layer_identifier=dst.data["layer"].identifier,
                    src_parent_layer_identifier=src.parent.data["layer"].identifier,
                    src_layer_identifier=src.data["layer"].identifier,
                    dst_stronger_than_src=True,
                    usd_context=self._context_name,
                )

    def transfer_layer_overrides(self, layer: LayerItem, existing_layer: bool):
        """
        Transfer the overrides of a layer in a sublayer. The sublayer can be an existing one or a new one.

        Args:
            layer: the layer to be saved
            existing_layer: whether the layer exists or should be created
        """
        self.create_layer(
            not existing_layer,
            parent=layer,
            layer_created_callback=partial(self._on_transfer_layer_overrides_internal, layer),
        )

    def is_layer_locked(self, layer: LayerItem) -> bool:
        """
        Get the lock state of a layer item

        Returns:
            True if the layer is locked, False otherwise
        """
        layers_state = _layers.get_layers(self._context).get_layers_state()
        return layers_state.is_layer_locked(layer.data["layer"].identifier)

    def is_layer_muted(self, layer: LayerItem) -> bool:
        """
        Get the muteness state of a layer item

        Returns:
            True if the layer is muted, False otherwise
        """
        layers_state = _layers.get_layers(self._context).get_layers_state()
        layers_state.set_muteness_scope(True)
        return layers_state.is_layer_globally_muted(layer.data["layer"].identifier)

    # Item methods

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
                self._items.sort(key=lambda i: i.title)
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
        layer = parent.children if parent is not None else self._items
        for item in layer:
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
        # Can't drop on itself
        if str(item_source) == str(item_target):
            return False
        # Can never drop the item outside the root layer
        if item_target is None:
            return False
        # If re-ordering make sure the target's parent is valid
        if drop_location >= 0:
            return self.drop_accepted(item_target.parent, item_source, -1)
        # If not re-ordering  or evaluating parent, make sure the target is valid
        if item_source.data["exclude_move"]:
            return False
        if self.is_layer_locked(item_target):
            return False
        if item_target.data["exclude_add_child"]:
            return False
        if item_target.data["layer"].identifier in [
            c.data["layer"].identifier for c in self.get_item_children(item_source, True)
        ]:
            return False
        return True

    def drop(self, item_target: ItemBase, item_source: Union[str, ItemBase], drop_location: int = -1) -> None:
        source = item_source
        if isinstance(item_source, str):
            source = self.find_item(item_source, lambda item, mime: self.get_drag_mime_data(item) == mime)
        if drop_location >= 0:
            self.move_sublayer(source, item_target.parent, drop_location)
        elif source is not None and item_target is not None:
            self.move_sublayer(source, item_target)

    @usd.handle_exception
    async def _deferred_refresh(self):
        if not self.stage or self._ignore_refresh:
            return

        self.__on_refresh_started()

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            # Submit the jobs in an async thread to avoid locking up the UI
            root_item = await loop.run_in_executor(
                pool,
                self._create_layer_items,
                self.stage.GetRootLayer(),
                None,
            )

        self._update_inherited_visibility(root_item, True)

        self.set_items([root_item])

        self.__on_refresh_completed()

    def _create_layer_items(self, layer, parent):
        children = []
        for sub_layer in layer.subLayerPaths:
            sub_layer_path = layer.ComputeAbsolutePath(sub_layer)
            if layer.realPath == sub_layer_path:
                continue
            child_layer = Sdf.Layer.FindOrOpen(sub_layer_path)
            if child_layer is None:
                continue
            children.append(self._create_layer_items(child_layer, layer))

        is_dirty = False
        dirty_layers = _layers.LayerUtils.get_dirty_layers(self.stage)
        for dirty_layer in dirty_layers:
            if layer.identifier == dirty_layer:
                is_dirty = True
                break

        # If any of the children is the edit target, all parents cannot be muted
        def has_authoring_child_recursive(items):
            has_authoring = False
            for item in items:
                has_authoring = has_authoring or item.data["authoring"] or has_authoring_child_recursive(item.children)
                if has_authoring:
                    break
            return has_authoring

        excludes = {}
        custom_data = layer.customLayerData.get(_LayerCustomData.ROOT.value, {})

        exclude_functions = {
            _LayerCustomData.EXCLUDE_REMOVE: self._exclude_remove_fn,
            _LayerCustomData.EXCLUDE_LOCK: self._exclude_lock_fn,
            _LayerCustomData.EXCLUDE_MUTE: self._exclude_mute_fn,
            _LayerCustomData.EXCLUDE_EDIT_TARGET: self._exclude_edit_target_fn,
            _LayerCustomData.EXCLUDE_ADD_CHILD: self._exclude_add_child_fn,
            _LayerCustomData.EXCLUDE_MOVE: self._exclude_move_fn,
        }

        for exclude_type in _LayerCustomData:
            if exclude_type == _LayerCustomData.ROOT:
                continue
            value = custom_data.get(exclude_type.value, None)
            if value is None:
                value = (
                    layer.identifier in exclude_functions[exclude_type]() if exclude_functions[exclude_type] else False
                )
            excludes[exclude_type] = value

        layers_state = _layers.get_layers(self._context).get_layers_state()

        layer_name = _layers.LayerUtils.get_custom_layer_name(layer) if parent is not None else "Root Layer"
        is_authoring = _layers.LayerUtils.get_edit_target(self.stage) == layer.identifier

        layer_data = {
            "locked": layers_state.is_layer_locked(layer.identifier),
            "visible": not layers_state.is_layer_globally_muted(layer.identifier),  # Only check global state
            "parent_visible": True,  # Will be set after all the items are created -> _update_inherited_visibility
            "savable": layers_state.is_layer_savable(layer.identifier),
            "authoring": is_authoring,
            "dirty": is_dirty,
            "layer": layer,
            "can_toggle_mute": not is_authoring and not has_authoring_child_recursive(children),
            "exclude_remove": excludes[_LayerCustomData.EXCLUDE_REMOVE],
            "exclude_lock": excludes[_LayerCustomData.EXCLUDE_LOCK],
            "exclude_mute": excludes[_LayerCustomData.EXCLUDE_MUTE],
            "exclude_edit_target": excludes[_LayerCustomData.EXCLUDE_EDIT_TARGET],
            "exclude_add_child": excludes[_LayerCustomData.EXCLUDE_ADD_CHILD],
            "exclude_move": excludes[_LayerCustomData.EXCLUDE_MOVE],
        }
        return LayerItem(layer_name, layer_data, parent, children)

    def _update_inherited_visibility(self, item: LayerItem, visible: bool):
        """
        Update the visibility of the children based on the parent's visibility
        """
        item.data["parent_visible"] = visible
        for child in item.children:
            self._update_inherited_visibility(child, visible and item.data["visible"])

    def _on_save_layer_as_internal(self, success, error_message, layers):
        """
        Should not be used by itself. Use `save_layer_as` instead
        """
        if success:
            carb.log_info(f"{','.join(layers)} {'were' if len(layers) > 1 else 'was'} saved successfully")
        else:
            carb.log_error(error_message)

    def _on_export_layer_internal(self, layer: LayerItem, path: str):
        """
        Should not be used by itself. Use `export_layer` instead
        """
        success = layer.data["layer"].Export(path)
        if success:
            carb.log_info("The layer was successfully exported.")
        else:
            carb.log_error("An error occurred while exporting the layer.")

    def _on_transfer_layer_overrides_internal(self, layer, path):
        """
        Should not be used by itself. Use `transfer_layer_overrides` instead
        """
        # This is inside the create_layer undo group
        for prim_spec in layer.data["layer"].rootPrims.values():
            commands.execute(
                "MovePrimSpecsToLayerCommand",
                dst_layer_identifier=path,
                src_layer_identifier=layer.data["layer"].identifier,
                prim_spec_path=str(prim_spec.path),
                dst_stronger_than_src=True,
                usd_context=self._context_name,
            )

    def __on_layer_events(self, event):
        payload = _layers.get_layer_event_payload(event)
        if payload.event_type not in [
            _layers.LayerEventType.DIRTY_STATE_CHANGED,
            _layers.LayerEventType.LOCK_STATE_CHANGED,
            _layers.LayerEventType.MUTENESS_STATE_CHANGED,
            _layers.LayerEventType.SUBLAYERS_CHANGED,
            _layers.LayerEventType.EDIT_TARGET_CHANGED,
        ]:
            return
        self.refresh()

    def __on_stage_events(self, event):
        if usd.StageEventType(event.type) not in [
            usd.StageEventType.OPENED,
            usd.StageEventType.OPEN_FAILED,
            usd.StageEventType.CLOSED,
        ]:
            return
        self._context = usd.get_context(self._context_name)
        self.stage = self._context.get_stage()
        self.refresh()

    def subscribe_refresh_started(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_refresh_started, function)

    def subscribe_refresh_completed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_refresh_completed, function)

    def destroy(self):
        if self.__refresh_task:
            self.__refresh_task.cancel()
            self.__refresh_task = None
        _reset_default_attrs(self)
