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
import omni.ext
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts

from . import commands
from .setup import Setup as _StageCraftSetup
from .unsaved_stage import EventUnsavedStageOnShutdown


class TrexStageCraftControlExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def __init__(self, *args, **kwargs):
        """Initialize extension-owned StageCraft resources."""
        super().__init__(*args, **kwargs)
        self._setup = None
        self._unsaved_event = None

    def on_startup(self, ext_id):
        """Create and register StageCraft resources."""
        carb.log_info("[lightspeed.trex.control.stagecraft] Startup")

        trex_contexts_instance().create_usd_context(_TrexContexts.STAGE_CRAFT)
        trex_contexts_instance().set_current_context(_TrexContexts.STAGE_CRAFT)
        commands.register_commands()

        self._setup = _StageCraftSetup()
        self._unsaved_event = EventUnsavedStageOnShutdown()
        self._unsaved_event.register_interrupter(self._setup)
        _get_event_manager_instance().register_event(self._unsaved_event)
        self._setup.register_sidebar_items()

    def on_shutdown(self):
        """Unregister and release StageCraft resources."""
        carb.log_info("[lightspeed.trex.control.stagecraft] Shutdown")
        if self._unsaved_event:
            _get_event_manager_instance().unregister_event(self._unsaved_event)
        self._unsaved_event = None
        if self._setup:
            self._setup.destroy()
        self._setup = None
        commands.unregister_commands()
