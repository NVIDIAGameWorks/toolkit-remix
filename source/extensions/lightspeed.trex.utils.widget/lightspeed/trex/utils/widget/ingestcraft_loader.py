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

from __future__ import annotations

import asyncio

import carb
import omni.kit.app
import omni.usd

__all__ = ["ensure_ingestcraft_loaded"]

_CONTROL_EXT = "lightspeed.trex.control.ingestcraft"
_VIEWPORT_BUNDLE_EXT = "lightspeed.trex.viewports.ingestcraft.bundle"
_RUNTIME_EXTENSIONS = (_VIEWPORT_BUNDLE_EXT, _CONTROL_EXT)
_INGESTCRAFT_CONTEXT = "ingestcraft"
_LOAD_TIMEOUT_SECONDS = 30.0


@omni.usd.handle_exception
async def ensure_ingestcraft_loaded(timeout_seconds: float = _LOAD_TIMEOUT_SECONDS) -> bool:
    """Enable IngestCraft UI extensions and wait for its stage-opened event."""
    manager = omni.kit.app.get_app().get_extension_manager()

    if manager.is_extension_enabled(_CONTROL_EXT):
        context = omni.usd.get_context(_INGESTCRAFT_CONTEXT)
        if context and context.get_stage():
            return True

    for ext_id in _RUNTIME_EXTENSIONS:
        if manager.is_extension_enabled(ext_id):
            continue
        manager.set_extension_enabled(ext_id, True)

    context = omni.usd.get_context(_INGESTCRAFT_CONTEXT)
    if not context:
        carb.log_error("[lightspeed.trex.utils.widget] IngestCraft did not create its USD context")
        return False
    if context.get_stage():
        return True

    stage_opened = asyncio.get_running_loop().create_future()

    def on_stage_event(event) -> None:
        """Complete activation when the IngestCraft stage opens."""
        if event.type == int(omni.usd.StageEventType.OPENED) and not stage_opened.done():
            stage_opened.set_result(None)

    _stage_event_subscription = context.get_stage_event_stream().create_subscription_to_pop(
        on_stage_event, name="Wait for IngestCraft Stage"
    )
    if context.get_stage():
        return True

    try:
        await asyncio.wait_for(stage_opened, timeout=timeout_seconds)
    except TimeoutError:
        carb.log_error("[lightspeed.trex.utils.widget] Timed out loading IngestCraft extensions")
        return False

    return True
