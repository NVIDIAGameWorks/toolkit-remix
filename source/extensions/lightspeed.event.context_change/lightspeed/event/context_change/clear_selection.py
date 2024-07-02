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

import omni.usd
from lightspeed.common import constants
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class EventClearSelectionOnContextChange(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_sub_context_changed": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "Context Changed"

    def _install(self):
        """Function that will create the behavior"""
        self._install_context_listener()

    def _install_context_listener(self):
        # Register the global event if not already registered and subscribe
        self._sub_context_changed = _get_event_manager_instance().subscribe_global_custom_event(
            constants.GlobalEventNames.CONTEXT_CHANGED.value, self.__on_context_change_event
        )

    def __on_context_change_event(self, old_context_name: str = "", new_context_name: str = ""):
        # Clear any selections in the context that will no longer be visible
        omni.usd.get_context(old_context_name).get_selection().clear_selected_prim_paths()

    def _uninstall(self):
        """Function that will delete the behavior"""
        _get_event_manager_instance().unregister_global_custom_event(constants.GlobalEventNames.CONTEXT_CHANGED.value)
        self._sub_context_changed = None

    def destroy(self):
        _reset_default_attrs(self)
