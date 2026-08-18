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

__all__ = [
    "COMFYUI_EVENT_NAME",
    "ComfyUIEventPayload",
    "publish_comfyui_event",
    "subscribe_comfyui_event",
]

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import carb
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from omni.flux.utils.common import EventSubscription

from .enums import ComfyUIEventType

COMFYUI_EVENT_NAME = "lightspeed.trex.comfyui.changed"


@dataclass
class ComfyUIEventPayload:
    """Carry a typed ComfyUI event and its optional data to subscribers."""

    context_name: str
    event_type: ComfyUIEventType
    data: Any = None


def subscribe_comfyui_event(
    context_name: str,
    callback: Callable[[ComfyUIEventPayload], None],
) -> EventSubscription:
    """Subscribe to ComfyUI notifications for one USD context.

    Args:
        context_name: USD context whose events should be delivered.
        callback: Observer invoked with matching event payloads.

    Returns:
        Subscription whose lifetime controls callback registration.
    """

    def on_event(payload: ComfyUIEventPayload) -> None:
        """Filter the shared event and isolate one product subscriber."""
        if payload.context_name != context_name:
            return
        try:
            callback(payload)
        except Exception as error:  # noqa: BLE001 - observers must not interrupt later subscribers
            carb.log_error(f"ComfyUI event subscriber failed: {error}")

    return _get_event_manager_instance().subscribe_global_custom_event(COMFYUI_EVENT_NAME, on_event)


def publish_comfyui_event(
    context_name: str,
    event_type: ComfyUIEventType,
    data: Any = None,
) -> None:
    """Publish a context-qualified ComfyUI notification through the shared event manager.

    Args:
        context_name: USD context that owns the changed state.
        event_type: Typed event identifier.
        data: Optional payload attached to the event.
    """
    _get_event_manager_instance().call_global_custom_event(
        COMFYUI_EVENT_NAME,
        ComfyUIEventPayload(context_name=context_name, event_type=event_type, data=data),
    )
