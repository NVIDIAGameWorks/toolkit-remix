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
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit.widget.prompt import PromptButtonInfo as _PromptButtonInfo
from omni.kit.widget.prompt import PromptManager as _PromptManager
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf

_CONTEXT = "/exts/lightspeed.event.autosave/context"

SETTINGS_ENABLED = "/persistent/exts/lightspeed.event.autosave/enabled"
SETTINGS_INTERVAL_SECONDS = "/persistent/exts/lightspeed.event.autosave/interval_seconds"

_DEFAULT_ENABLED = False
_DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
_PROMPT_TITLE = "Auto-Save Project?"
_PROMPT_MESSAGE = (
    "Auto-Save is turned on, and RTX Remix found unsaved changes in this project.\n\n"
    "Save now, skip this save, or allow Auto-Save to continue without prompting again until you restart the app."
)


class AutoSaveCore(_ILSSEvent):
    def __init__(self):
        super().__init__()
        self.default_attr = {
            "_context_name": None,
            "_context": None,
            "_layer_manager": None,
            "_notification_manager": None,
            "_stage_event_sub": None,
            "_autosave_task": None,
            "_autosave_prompt_open": None,
            "_autosave_prompt_suppressed_for_session": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context_name = carb.settings.get_settings().get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)
        self._layer_manager = _LayerManagerCore(self._context_name)

        self._notification_manager = _nm.manager.NotificationManager()
        self._notification_manager.on_startup()
        self._autosave_prompt_open = False
        self._autosave_prompt_suppressed_for_session = False

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
        layer_capture = self._layer_manager.get_layer_of_type(_LayerType.capture)
        if not layer_capture:
            carb.log_verbose("[autosave] No capture layer found, skipping auto-save")
            return

        layer_replacement = self._layer_manager.get_layer_of_type(_LayerType.replacement)
        if not layer_replacement:
            carb.log_verbose("[autosave] No replacement layer found, skipping auto-save")
            return

        saveable_layers = self._get_saveable_dirty_layers(stage)
        if not saveable_layers:
            return

        if self._autosave_prompt_suppressed_for_session:
            self._save_layers(saveable_layers)
            return

        self._prompt_to_autosave(saveable_layers)

    def _get_saveable_dirty_layers(self, stage) -> list[Sdf.Layer]:
        dirty_identifiers = LayerUtils.get_dirty_layers(stage)
        saveable_layers = []
        for identifier in dirty_identifiers:
            layer = Sdf.Layer.FindOrOpen(identifier)
            if layer and not layer.anonymous:
                saveable_layers.append(layer)
        return saveable_layers

    def _prompt_to_autosave(self, layers: list[Sdf.Layer]):
        if self._autosave_prompt_open:
            return

        self._autosave_prompt_open = True

        def on_close():
            self._autosave_prompt_open = False

        def on_save():
            on_close()
            self._save_layers(layers)

        def on_dont_save():
            on_close()
            carb.log_info("[autosave] User skipped auto-save")

        def on_dont_ask_again_this_session():
            self._autosave_prompt_suppressed_for_session = True
            on_save()

        _PromptManager.post_simple_prompt(
            _PROMPT_TITLE,
            _PROMPT_MESSAGE,
            ok_button_info=_PromptButtonInfo("Save", on_save),
            middle_button_info=_PromptButtonInfo("Don't Save", on_dont_save),
            middle_2_button_info=_PromptButtonInfo("Don't Ask Again This Session", on_dont_ask_again_this_session),
            cancel_button_info=None,
            modal=True,
            no_title_bar=False,
            on_window_closed_fn=on_close,
        )

    def _save_layers(self, layers: list[Sdf.Layer]):
        saved_count = 0
        for layer in layers:
            layer.Save()
            saved_count += 1
            carb.log_info(f"[autosave] Saved layer: {layer.identifier}")

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
