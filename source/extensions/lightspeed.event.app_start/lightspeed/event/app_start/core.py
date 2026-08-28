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

import asyncio
import time
from datetime import datetime, UTC

import carb
import omni.kit.app
from lightspeed.events_manager import ILSSEvent
from lightspeed.trex.app.setup.lifecycle import subscribe_user_ready
from omni.flux.telemetry.core import get_telemetry_instance
from omni.flux.utils.common import reset_default_attrs
from omni.gpu_foundation_factory import get_memory_info
from omni.hydra.engine.stats import get_device_info


class EventAppStartCore(ILSSEvent):
    """Record startup telemetry after the application reaches user readiness."""

    def __init__(self):
        """Initialize application startup subscriptions, tasks, and timing state."""
        super().__init__()

        self.default_attr = {
            "_app": None,
            "_subscription": None,
            "_executed": False,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._user_ready_subscription = None
        self._telemetry_task = None
        self._app_start_time = None
        self._kit_ready_time = None

        self._app = omni.kit.app.get_app()

    @property
    def name(self) -> str:
        """Name of the event"""
        return "AppStarted"

    def _install(self):
        """Subscribe to application readiness and capture the startup start time."""
        self._app_start_time = time.time() - self._app.get_time_since_start_s()
        if self._app.is_app_ready():
            self.__on_app_started(None)
        else:
            self._subscription = self._app.get_startup_event_stream().create_subscription_to_pop_by_type(
                omni.kit.app.EVENT_APP_READY, self.__on_app_started, name="App Ready"
            )

    def _uninstall(self):
        """Release readiness subscriptions and cancel pending telemetry."""
        self._subscription = None
        self._user_ready_subscription = None
        if self._telemetry_task:
            self._telemetry_task.cancel()
        self._telemetry_task = None

    def __on_app_started(self, payload):
        # Make sure to only execute once (in case of hot reload)
        if self._executed:
            return
        self._executed = True
        self._subscription = None
        self._kit_ready_time = time.time()
        self._user_ready_subscription = subscribe_user_ready(self.__on_user_ready)

    def __on_user_ready(self):
        if self._telemetry_task:
            return
        user_ready_time = time.time()
        self._telemetry_task = asyncio.ensure_future(self.__record_startup_telemetry(user_ready_time))
        self._telemetry_task.add_done_callback(self.__on_telemetry_task_done)

    @staticmethod
    def __on_telemetry_task_done(task: asyncio.Task):
        if task.cancelled():
            return
        exception = task.exception()
        if exception:
            carb.log_error(f"[lightspeed.event.app_start] Could not record startup telemetry: {exception}")

    async def __record_startup_telemetry(self, user_ready_time: float):
        task = asyncio.current_task()
        try:
            await self._app.next_update_async()
            telemetry = get_telemetry_instance()

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
                transaction.set_data("user_ready_duration", user_ready_time - self._app_start_time)

                transaction.start_timestamp = datetime.fromtimestamp(self._app_start_time, tz=UTC)
                transaction.finish(end_timestamp=datetime.fromtimestamp(self._kit_ready_time, tz=UTC))
        finally:
            if self._telemetry_task is task:
                self._telemetry_task = None

    def destroy(self):
        """Release startup subscriptions, tasks, and timing state."""
        self._uninstall()
        self._app_start_time = None
        self._kit_ready_time = None
        reset_default_attrs(self)
