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

from .unsaved_stage import EventUnsavedStageOnShutdown

_unsaved_event = None


class EventShutdownExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    # noinspection PyUnusedLocal
    def on_startup(self, ext_id):
        global _unsaved_event
        carb.log_info("[lightspeed.event.load_edit_target] Lightspeed Event Shutdown startup")
        _unsaved_event = EventUnsavedStageOnShutdown()
        _get_event_manager_instance().register_event(_unsaved_event)

    def on_shutdown(self):
        global _unsaved_event
        carb.log_info("[lightspeed.event.load_edit_target] Lightspeed Events Shutdown shutdown")
        _get_event_manager_instance().unregister_event(_unsaved_event)
        _unsaved_event = None
