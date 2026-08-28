"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from collections.abc import Callable

import carb
from omni.flux.utils.common import Event, EventSubscription

_USER_READY = False
_USER_READY_EVENT = Event(copy=True)
_HOME_INTERACTIVE = asyncio.Event()


def is_user_ready() -> bool:
    """Return whether this process has published USER_READY."""
    return _USER_READY


def subscribe_user_ready(callback: Callable[[], None]) -> EventSubscription:
    """Subscribe to USER_READY, invoking the callback immediately when already ready."""
    subscription = EventSubscription(_USER_READY_EVENT, callback)
    if _USER_READY:
        callback()
    return subscription


def mark_home_interactive() -> None:
    """Publish the process-local Home interactive milestone once."""
    if _HOME_INTERACTIVE.is_set():
        return
    carb.log_info("HOME_INTERACTIVE")
    _HOME_INTERACTIVE.set()


async def _wait_for_home_interactive() -> None:
    await _HOME_INTERACTIVE.wait()


def _publish_user_ready() -> None:
    global _USER_READY
    if _USER_READY:
        return
    _USER_READY = True
    carb.log_info("USER_READY")
    _USER_READY_EVENT()
