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
import typing
from typing import List, Union

import omni.usd
from omni.flux.property_widget_builder.widget import Model as _Model
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pxr import Sdf, Usd

from .items import USDAttributeItem as _USDAttributeItem
from .items import USDAttributeItemStub as _USDAttributeItemStub
from .items import USDAttributeItemVirtual as _USDAttributeItemVirtual

if typing.TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import ItemGroup as _ItemGroup


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

        self._value_changed_callbacks = []

        self.__on_item_model_end_edit = _Event()
        self.__on_attribute_created = _Event()
        self.__on_attribute_changed = _Event()
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
    def prim_paths(self) -> List[Sdf.Path]:
        """The current used attribute paths"""
        return self._prim_paths

    def set_prim_paths(self, value: List[Sdf.Path]):
        """The current used attribute paths"""
        self._prim_paths = value

    @property
    def default_attrs(self):
        return super().default_attrs

    def set_items(self, items: List[Union["_ItemGroup", _USDAttributeItem]]):
        """
        Set the items to show

        Args:
            items: the items to show
        """

        def add_listeners(_item):
            if isinstance(item, _USDAttributeItem):
                self._subscriptions.append(_item.subscribe_attribute_changed(self._attribute_changed))
                self._subscriptions.append(_item.subscribe_override_removed(self._overrides_removed))
            if isinstance(item, _USDAttributeItemStub):
                self._subscriptions.append(
                    item.subscribe_create_attributes_begin(self._item_attribute_create_begin_edit)
                )
                self._subscriptions.append(item.subscribe_create_attributes_end(self._item_attribute_create_end_edit))
                self._value_changed_callbacks.append(item.refresh)
            for _value_model in _item.value_models:
                self._subscriptions.append(_value_model.subscribe_begin_edit_fn(self._on_item_model_begin_edit))
                self._subscriptions.append(_value_model.subscribe_end_edit_fn(self._item_model_end_edit))
                if isinstance(item, _USDAttributeItemVirtual):
                    self._subscriptions.append(_value_model.subscribe_attribute_created(self._attribute_changed))
            for child in _item.children:
                add_listeners(child)

        self._subscriptions.clear()
        self._value_changed_callbacks.clear()
        for item in items:
            add_listeners(item)
        super().set_items(items)

    def _on_item_model_begin_edit(self, _):
        self.supress_usd_events_during_widget_edit = True

    def _item_model_end_edit(self, model):
        """Call the event object that has the list of functions"""
        for callback in self._value_changed_callbacks:
            callback()
        self.supress_usd_events_during_widget_edit = False
        self.__on_item_model_end_edit(model)

    def subscribe_item_model_end_edit(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_item_model_end_edit, function)

    def _item_attribute_create_begin_edit(self, _):
        self.supress_usd_events_during_widget_edit = True

    def _item_attribute_create_end_edit(self, attribute_paths):
        self.supress_usd_events_during_widget_edit = False
        self.__on_attribute_created(attribute_paths)

    def subscribe_attribute_created(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_attribute_created, function)

    def _attribute_changed(self, attribute_paths):
        """Call the event object that has the list of functions"""
        self.__on_attribute_changed(attribute_paths)

    def subscribe_attribute_changed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_attribute_changed, function)

    def _overrides_removed(self):
        self.__on_override_removed()

    def subscribe_override_removed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_override_removed, function)
