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

import carb
import carb.settings
import omni.ext
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts

from .setup import Setup
from .unsaved_stage import EventUnsavedStageOnShutdown

_stagecraft_control_instance: Setup | None = None


def _create_instance():
    global _stagecraft_control_instance
    _stagecraft_control_instance = Setup()
    return _stagecraft_control_instance


def get_instance():
    return _stagecraft_control_instance


class TrexStageCraftControlExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unsaved_event = None

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.control.stagecraft] Startup")

        trex_contexts_instance().create_usd_context(_TrexContexts.STAGE_CRAFT)

        instance = _create_instance()
        self._unsaved_event = EventUnsavedStageOnShutdown()
        self._unsaved_event.register_interrupter(instance)
        _get_event_manager_instance().register_event(self._unsaved_event)
        instance.register_sidebar_items()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.control.stagecraft] Shutdown")
        global _stagecraft_control_instance
        if _stagecraft_control_instance:
            _stagecraft_control_instance.destroy()
        _stagecraft_control_instance = None
        self._unsaved_event = None
