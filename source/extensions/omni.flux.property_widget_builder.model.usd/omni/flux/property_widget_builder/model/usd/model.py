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

from __future__ import annotations

import abc
import typing
import omni.usd
from omni.flux.property_widget_builder.widget import Model as _Model
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.interactive_usd_notices import begin_interaction as _begin_interaction
from omni.flux.utils.common.interactive_usd_notices import end_interaction as _end_interaction
from pxr import Sdf, Usd

from .items import USDAttributeItem as _USDAttributeItem
from .items import USDAttributeItemStub as _USDAttributeItemStub
from .items import USDAttrListItem as _USDAttrListItem
from .items import USDMetadataListItem as _USDMetadataListItem
from .items import VirtualUSDAttrListItem as _VirtualUSDAttrListItem

if typing.TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup


_ATTRIBUTE_CREATE_EDIT_GROUP_KEY = ("attribute-create",)


class USDModel(_Model):
    """Basic list model"""

    def __init__(self, context_name: str = ""):
        """
        Override of the init of the base class

        Args:
            context_name: the context name to use
        """
        super().__init__()

        self._context_name = context_name
        self._context = omni.usd.get_context(self._context_name)
        self._prim_paths = []
        self._subscriptions = []
        self.supress_usd_events_during_widget_edit = False
        self._active_edit_model_counts = {}
        self._usd_notice_token = None
        self._is_cancelling_property_edit = False
        self._attribute_create_cancelled_count = 0

        self._value_changed_callbacks = []

        self.__on_item_model_end_edit = _Event()
        self.__on_attribute_created = _Event()
        self.__on_override_removed = _Event()

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_context_name": None,
                "_context": None,
                "_prim_paths": None,
                "_subscriptions": None,
                "supress_usd_events_during_widget_edit": None,
                "_active_edit_model_counts": None,
                "_usd_notice_token": None,
                "_is_cancelling_property_edit": None,
                "_attribute_create_cancelled_count": None,
                "_value_changed_callbacks": None,
            }
        )
        return default_attr

    @property
    def context_name(self) -> str:
        """The current used context"""
        return self._context_name

    @property
    def stage(self) -> Usd.Stage:
        """The current used stage"""
        return self._context.get_stage()

    @property
    def prim_paths(self) -> list[Sdf.Path]:
        """The current used attribute paths"""
        return self._prim_paths

    def set_prim_paths(self, value: list[Sdf.Path]):
        """The current used attribute paths"""
        self._prim_paths = value

    @property
    def default_attrs(self):
        return super().default_attrs

    def set_items(self, items: list[_ItemGroup | _USDAttributeItem]):
        """
        Set the items to show

        Args:
            items: the items to show
        """

        def add_listeners(_item):
            if isinstance(_item, (_USDAttributeItem, _USDAttrListItem, _USDMetadataListItem, _VirtualUSDAttrListItem)):
                self._subscriptions.append(_item.subscribe_override_removed(self._overrides_removed))
            if isinstance(_item, _USDAttributeItemStub):
                self._subscriptions.append(
                    _item.subscribe_create_attributes_begin(self._item_attribute_create_begin_edit)
                )
                self._subscriptions.append(_item.subscribe_create_attributes_end(self._item_attribute_create_end_edit))
                self._value_changed_callbacks.append(_item.refresh)
            for _value_model in _item.value_models:
                _value_model.set_property_edit_callbacks(self._on_item_model_begin_edit, self._item_model_end_edit)
            for child in _item.children:
                add_listeners(child)

        cancel_error = None
        try:
            self.cancel_property_edit_interaction()
        except Exception as exc:  # noqa: BLE001 - finish replacing items before surfacing cancel failure.
            cancel_error = exc
        finally:
            for item in tuple(self.get_all_items(include_hidden=True)):
                for value_model in tuple(item.value_models):
                    value_model.set_property_edit_callbacks(None, None)
            self._subscriptions.clear()
            self._value_changed_callbacks.clear()
        for item in items:
            add_listeners(item)
        super().set_items(items)
        if cancel_error is not None:
            raise cancel_error

    def _finish_property_edit_interaction(self):
        self.supress_usd_events_during_widget_edit = False
        token = self._usd_notice_token
        self._usd_notice_token = None
        if token is not None:
            _end_interaction(token)

    def _ensure_property_edit_interaction(self):
        if self._usd_notice_token is None:
            stage = self.stage
            if stage is not None:
                self._usd_notice_token = _begin_interaction(stage)

    def _begin_property_edit(self, model_id):
        self._ensure_property_edit_interaction()
        self._active_edit_model_counts[model_id] = self._active_edit_model_counts.get(model_id, 0) + 1
        self.supress_usd_events_during_widget_edit = True

    def _has_other_active_property_edit(self, model_id):
        return any(active_model_id != model_id for active_model_id in self._active_edit_model_counts)

    def _is_final_property_edit(self, model_id):
        return self._active_edit_model_counts.get(model_id, 0) == 1 and not self._has_other_active_property_edit(
            model_id
        )

    def _end_property_edit(self, model_id):
        if self._is_cancelling_property_edit:
            self._active_edit_model_counts.pop(model_id, None)
            return
        active_edit_count = self._active_edit_model_counts.get(model_id, 0)
        if active_edit_count <= 0:
            self._active_edit_model_counts.pop(model_id, None)
            if not self._active_edit_model_counts:
                self._finish_property_edit_interaction()
            return
        if active_edit_count > 1:
            self._active_edit_model_counts[model_id] = active_edit_count - 1
            return
        if active_edit_count == 1:
            self._active_edit_model_counts.pop(model_id)
        if self._active_edit_model_counts:
            return
        self._finish_property_edit_interaction()

    def cancel_property_edit_interaction(self):
        attribute_create_model_id = id(_ATTRIBUTE_CREATE_EDIT_GROUP_KEY)
        self._attribute_create_cancelled_count += self._active_edit_model_counts.get(attribute_create_model_id, 0)
        was_cancelling = self._is_cancelling_property_edit
        self._is_cancelling_property_edit = True
        first_error = None
        try:
            for item in tuple(self.get_all_items(include_hidden=True)):
                for value_model in tuple(item.value_models):
                    try:
                        value_model.cancel_property_edit_interaction()
                    except Exception as exc:  # noqa: BLE001 - cancel every value model before re-raising.
                        if first_error is None:
                            first_error = exc
        finally:
            self._is_cancelling_property_edit = was_cancelling
            self._active_edit_model_counts.clear()
            self._finish_property_edit_interaction()
        if first_error is not None:
            raise first_error

    def _on_item_model_begin_edit(self, model):
        self._begin_property_edit(id(model))

    def _item_model_end_edit(self, model):
        """End one item model edit and fire callbacks only after the final active edit."""
        if self._is_cancelling_property_edit:
            self._end_property_edit(id(model))
            return
        is_final_edit = self._is_final_property_edit(id(model))
        try:
            if is_final_edit:
                self._ensure_property_edit_interaction()
                for callback in self._value_changed_callbacks:
                    callback()
                self.__on_item_model_end_edit(model)
        finally:
            self._end_property_edit(id(model))

    def subscribe_item_model_end_edit(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_model_end_edit, function)

    def _item_attribute_create_begin_edit(self, _):
        self._begin_property_edit(id(_ATTRIBUTE_CREATE_EDIT_GROUP_KEY))

    def _item_attribute_create_end_edit(self, attribute_paths):
        was_cancelled = self._attribute_create_cancelled_count > 0
        try:
            if not self._is_cancelling_property_edit and not was_cancelled:
                self._ensure_property_edit_interaction()
                self.__on_attribute_created(attribute_paths)
        finally:
            if was_cancelled:
                self._attribute_create_cancelled_count -= 1
            self._end_property_edit(id(_ATTRIBUTE_CREATE_EDIT_GROUP_KEY))

    def subscribe_attribute_created(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_attribute_created, function)

    def _overrides_removed(self):
        self.__on_override_removed()

    def subscribe_override_removed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_override_removed, function)
