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

__all__ = ["EventAppStartCore"]

import time
from datetime import datetime, timezone

import omni.kit.app
from lightspeed.events_manager import ILSSEvent
from omni.flux.telemetry.core import get_telemetry_instance
from omni.flux.utils.common import reset_default_attrs
from omni.gpu_foundation_factory import get_memory_info
from omni.hydra.engine.stats import get_device_info


class EventAppStartCore(ILSSEvent):
    def __init__(self):
        super().__init__()

        self.default_attr = {
            "_app": None,
            "_subscription": None,
            "_executed": False,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._app = omni.kit.app.get_app()

        self._subscription = None
        self._executed = False

    @property
    def name(self) -> str:
        """Name of the event"""
        return "AppStarted"

    def _install(self):
        """Function that will create the behavior"""
        if self._app.is_app_ready():
            self.__on_app_started(None)
        else:
            self._subscription = self._app.get_startup_event_stream().create_subscription_to_pop_by_type(
                omni.kit.app.EVENT_APP_READY, self.__on_app_started, name="App Ready"
            )

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._subscription = None

    def __on_app_started(self, payload):
        # Make sure to only execute once (in case of hot reload)
        if self._executed:
            return

        telemetry = get_telemetry_instance()

        # Get the true start time of the app
        current_time = time.time()
        startup_duration = self._app.get_time_since_start_s()
        app_start_time = current_time - startup_duration

        # Assume the first device is the main GPU
        devices_info = get_device_info()
        device_info = devices_info[0] if devices_info else {}

        # Get the GPU information
        gpu_description = device_info.get("description", "GPU 0")
        dedicated_video_memory = device_info.get("dedicated_video_memory", 0)
        dedicated_system_memory = device_info.get("dedicated_system_memory", 0)
        usage_info = device_info.get("usage", 0)

        # Get the host memory information
        host_info = get_memory_info()
        total_memory, available_memory = host_info.get("total_memory", 0), host_info.get("available_memory", 0)

        with telemetry.sentry_sdk.start_transaction(op="startup", name="App Startup") as transaction:
            transaction.set_data("gpu", gpu_description)
            transaction.set_data("dedicated_video_memory", dedicated_video_memory)
            transaction.set_data("dedicated_system_memory", dedicated_system_memory)
            transaction.set_data("video_memory_usage", usage_info)
            transaction.set_data("total_host_memory", total_memory)
            transaction.set_data("available_host_memory", available_memory)

            transaction.start_timestamp = datetime.fromtimestamp(app_start_time, tz=timezone.utc)
            transaction.finish(end_timestamp=datetime.fromtimestamp(current_time, tz=timezone.utc))

        self._executed = True

    def destroy(self):
        reset_default_attrs(self)
