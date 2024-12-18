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

from enum import Enum
from typing import List

import omni.usd
from lightspeed.common import constants as _constants
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.trex.utils.common.dialog_utils import delete_dialogs as _delete_dialogs
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.file_pickers import destroy_file_picker as _destroy_file_picker


class Contexts(Enum):
    INGEST_CRAFT = "ingestcraft"
    TEXTURE_CRAFT = "texturecraft"
    # TODO. Don't forget to change the value also in lightspeed.app.trex.stagecraft.kit
    #  Note that this change may not be worth it because many core extensions like omni.kit.window.file
    #  and others currently assume "" for single default context.
    # STAGE_CRAFT = "stagecraft"
    STAGE_CRAFT = ""


class _Setup:
    def __init__(self):
        self._default_attr = {"_usd_contexts": None, "_current_context": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._usd_contexts = []
        self._current_context = None

        # TODO Feature OM-45888 - File Picker will appear behind the wizard modal
        # Register the global context change event if not already registered and subscribe
        event_manager = _get_event_manager_instance()
        event_manager.register_global_custom_event(_constants.GlobalEventNames.CONTEXT_CHANGED.value)
        self._context_changed_sub = event_manager.subscribe_global_custom_event(
            _constants.GlobalEventNames.CONTEXT_CHANGED.value, _destroy_file_picker
        )
        self._context_changed_dialogs_sub = event_manager.subscribe_global_custom_event(
            _constants.GlobalEventNames.CONTEXT_CHANGED.value, _delete_dialogs
        )

    def create_usd_context(self, usd_context_name: Contexts) -> omni.usd.UsdContext:
        usd_context = omni.usd.get_context(usd_context_name.value)
        if not usd_context:
            usd_context = omni.usd.create_context(usd_context_name.value)
            self._usd_contexts.append(usd_context)
        return usd_context

    def get_usd_contexts(self) -> List[omni.usd.UsdContext]:
        return self._usd_contexts

    def get_usd_context(
        self, usd_context_name: Contexts, create_if_not_exist: bool = True, do_raise: bool = True
    ) -> omni.usd.UsdContext:
        usd_context = omni.usd.get_context(usd_context_name.value)
        if not usd_context and not create_if_not_exist and do_raise:
            raise ValueError(f"Context {usd_context_name.value} was never created")
        if not usd_context and create_if_not_exist:
            usd_context = self.create_usd_context(usd_context_name)
        return usd_context  # noqa R504

    def get_current_context(self) -> Contexts:
        """Get the current context for the remix app"""
        if not self._current_context:
            raise RuntimeError("No context has been set yet. Make sure to call set_current_context()")
        return self._current_context

    def set_current_context(self, context: Contexts) -> None:
        """Set the current context for the remix app"""
        if not isinstance(context, Contexts):
            raise TypeError(
                f"The context argument must be of type {type(Contexts)}, not {type(context)}. "
                f"Please import the Contexts enum from lightspeed.trex.contexts.setup."
            )

        # TODO Feature OM-45888 - File Picker will appear behind the wizard modal
        if context != self._current_context and self._current_context is not None:
            _get_event_manager_instance().call_global_custom_event(
                _constants.GlobalEventNames.CONTEXT_CHANGED.value, self._current_context.value
            )
        self._current_context = context

    def destroy(self):
        for context in Contexts:
            if self.get_usd_context(context, create_if_not_exist=False, do_raise=False):
                omni.usd.destroy_context(context.value)
        _reset_default_attrs(self)


def create_instance() -> _Setup:
    return _Setup()
