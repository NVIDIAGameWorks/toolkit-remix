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

import asyncio

import carb
import omni.kit.notification_manager as _nm
import omni.kit.usd.layers as _layers
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf

_CONTEXT = "/exts/lightspeed.event.autosave/context"

SETTINGS_ENABLED = "/persistent/exts/lightspeed.event.autosave/enabled"
SETTINGS_INTERVAL_SECONDS = "/persistent/exts/lightspeed.event.autosave/interval_seconds"

_DEFAULT_ENABLED = True
_DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes


class AutoSaveCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_notification_manager": None,
            "_stage_event_sub": None,
            "_autosave_task": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)
        self._layer_manager = _LayerManagerCore(self._context_name)

        self._notification_manager = _nm.manager.NotificationManager()
        self._notification_manager.on_startup()

        # Ensure settings have defaults on first run
        settings = carb.settings.get_settings()
        if settings.get(SETTINGS_ENABLED) is None:
            settings.set(SETTINGS_ENABLED, _DEFAULT_ENABLED)
        if settings.get(SETTINGS_INTERVAL_SECONDS) is None:
            settings.set(SETTINGS_INTERVAL_SECONDS, _DEFAULT_INTERVAL_SECONDS)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "AutoSave"

    def _install(self):
        """Function that will create the behavior"""
        self._uninstall()

        self._stage_event_sub = self._context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="AutoSaveStageEvent"
        )

        # If a stage is already open when this extension loads, start the timer immediately
        if self._context.get_stage():
            self._start_timer()

    def _uninstall(self):
        """Function that will delete the behavior"""
        self._stop_timer()
        self._stage_event_sub = None

    def _on_stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.OPENED):
            self._start_timer()
        elif event.type == int(omni.usd.StageEventType.CLOSING):
            self._stop_timer()

    def _start_timer(self):
        self._stop_timer()
        self._autosave_task = asyncio.ensure_future(self._autosave_loop())

    def _stop_timer(self):
        if self._autosave_task:
            self._autosave_task.cancel()
            self._autosave_task = None

    async def _autosave_loop(self):
        try:
            while True:
                interval = carb.settings.get_settings().get(SETTINGS_INTERVAL_SECONDS) or _DEFAULT_INTERVAL_SECONDS
                await asyncio.sleep(interval)
                await self._do_autosave()
        except asyncio.CancelledError:
            pass

    async def _do_autosave(self):
        """Save all dirty, non-anonymous layers when conditions are met."""
        settings = carb.settings.get_settings()
        if not settings.get(SETTINGS_ENABLED):
            return

        stage = self._context.get_stage()
        if stage is None:
            return

        # Guard: only save when a valid project (capture + replacement layers) is loaded
        layer_capture = self._layer_manager.get_layer(_LayerType.capture)
        if not layer_capture:
            carb.log_verbose("[autosave] No capture layer found, skipping auto-save")
            return

        layer_replacement = self._layer_manager.get_layer(_LayerType.replacement)
        if not layer_replacement:
            carb.log_verbose("[autosave] No replacement layer found, skipping auto-save")
            return

        dirty_identifiers = LayerUtils.get_dirty_layers(stage)
        saved_count = 0
        for identifier in dirty_identifiers:
            layer = Sdf.Layer.FindOrOpen(identifier)
            if layer and not layer.anonymous:
                layer.Save()
                saved_count += 1
                carb.log_info(f"[autosave] Saved layer: {identifier}")

        if saved_count:
            self._post_notification(saved_count)

    def _post_notification(self, count: int):
        label = "layer" if count == 1 else "layers"
        message = f"Auto-saved {count} {label}."
        notification = _nm.notification_info.NotificationInfo(
            message,
            hide_after_timeout=True,
            status=_nm.NotificationStatus.INFO,
        )
        self._notification_manager.post_notification(notification)
        carb.log_info(f"[autosave] {message}")

    def destroy(self):
        _reset_default_attrs(self)
