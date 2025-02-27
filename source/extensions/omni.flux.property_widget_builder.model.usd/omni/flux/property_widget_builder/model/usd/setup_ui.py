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
from typing import TYPE_CHECKING, Awaitable, Callable, List, Optional, Union

import omni.kit.usd.layers as _layers
from omni import ui, usd
from omni.flux.property_widget_builder.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Delegate as _Delegate
    from omni.flux.property_widget_builder.widget import Model as _Model


class USDPropertyWidget(_PropertyWidget):
    """Widget that let you build property widget(s) from any data"""

    REFRESH_DELAY_SECONDS = 0.25

    def __init__(
        self,
        context_name: str = "",
        model: Optional["_Model"] = None,
        delegate: Optional["_Delegate"] = None,
        tree_column_widths: List[ui.Length] = None,
        refresh_callback: Optional[Union[Callable[[], None], Callable[[], Awaitable[None]]]] = None,
    ):
        """
        Args:
            context_name: the context name
            model: the tree widget's model
            delegate: the tree widget's delegate
            tree_column_widths: the tree widget's column widths
            refresh_callback: callback to refresh the parent widget. IE: used to refresh the widgets on sublayer change.
        """

        super().__init__(model=model, delegate=delegate, tree_column_widths=tree_column_widths)

        self._default_attr = {
            "_context_name": None,
            "_layer_events": None,
            "_on_override_removed_sub": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._refresh_callback = refresh_callback

        self._layer_events = None

        self.__refresh_task = None

        self._on_attribute_created_sub = self._model.subscribe_attribute_created(self._on_refresh_widget)
        self._on_override_removed_sub = self._model.subscribe_override_removed(self._on_refresh_widget)

        self.enable_listeners(True)

    def enable_listeners(self, value: bool) -> None:
        if value:
            self._layer_events = (
                _layers.get_layers(usd.get_context(self._context_name))
                .get_event_stream()
                .create_subscription_to_pop(self.__on_layer_event_listener, name="LayerEvent")
            )
        else:
            self._layer_events = None

    def _on_refresh_widget(self, _=None):
        if self.__refresh_task is not None:
            self.__refresh_task.cancel()
        self.__refresh_task = asyncio.ensure_future(self.__refresh_async())

    def __on_layer_event_listener(self, event):
        payload = _layers.get_layer_event_payload(event)
        if payload.event_type not in [
            _layers.LayerEventType.MUTENESS_STATE_CHANGED,
            _layers.LayerEventType.SUBLAYERS_CHANGED,
        ]:
            return
        self._on_refresh_widget()

    @usd.handle_exception
    async def __refresh_async(self):
        if self._refresh_callback is None:
            return
        if asyncio.iscoroutinefunction(self._refresh_callback):
            await self._refresh_callback()
        else:
            self._refresh_callback()

    def destroy(self):
        if self.__refresh_task is not None:
            self.__refresh_task.cancel()

        self.__refresh_task = None

        _reset_default_attrs(self)
