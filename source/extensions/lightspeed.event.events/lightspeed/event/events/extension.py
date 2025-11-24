"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from lightspeed.common.constants import GlobalEventNames
from lightspeed.events_manager import get_instance as _get_event_manager_instance


class GlobalEventsExtension(omni.ext.IExt):
    """Extension that registers all global custom events"""

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.event.events] Registering global custom events")

        # Register all global custom events
        event_manager = _get_event_manager_instance()
        for event in GlobalEventNames:
            event_manager.register_global_custom_event(event.value)

        carb.log_info(
            "[lightspeed.event.events] Global custom events registered successfully"
        )

    def on_shutdown(self):
        carb.log_info("[lightspeed.event.events] Unregistering global custom events")

        # Unregister all global custom events
        event_manager = _get_event_manager_instance()
        for event in GlobalEventNames:
            event_manager.unregister_global_custom_event(event.value)

        carb.log_info(
            "[lightspeed.event.events] Global custom events unregistered successfully"
        )
