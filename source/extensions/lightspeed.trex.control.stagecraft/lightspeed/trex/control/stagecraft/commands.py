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

import carb
import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from pxr import UsdUtils


class SwitchCaptureCommand(omni.kit.commands.Command):
    """Switch the active capture and preserve any active non-stage lighting mode as one undo item."""

    _DEFAULT_LIGHTING_MODE = "stage"

    def __init__(self, new_capture_path: str, context_name: str = ""):
        self._context_name = context_name
        self._capture_core_setup = _CaptureCoreSetup(context_name)
        self._new_capture_identifier = omni.client.normalize_url(new_capture_path) if new_capture_path else None
        current_capture_layer = self._capture_core_setup.get_layer()
        self._previous_capture_identifier = (
            omni.client.normalize_url(current_capture_layer.identifier) if current_capture_layer else None
        )

    @staticmethod
    def _get_current_lighting_mode(usd_context: omni.usd.UsdContext) -> str:
        stage_id = 0
        stage = usd_context.get_stage() if usd_context else None
        if stage:
            stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        settings = carb.settings.get_settings()
        return settings.get(f"/exts/omni.kit.viewport.menubar.lighting/lightingMode/{stage_id}") or (
            SwitchCaptureCommand._DEFAULT_LIGHTING_MODE
        )

    def _apply(self, capture_identifier: str):
        usd_context = omni.usd.get_context(self._context_name)
        lighting_mode = self._get_current_lighting_mode(usd_context)
        self._capture_core_setup.import_capture_layer(capture_identifier, do_undo=False)
        if lighting_mode != self._DEFAULT_LIGHTING_MODE:
            with omni.kit.undo.disabled():
                omni.kit.commands.execute(
                    "SetLightingMenuModeCommand",
                    lighting_mode=lighting_mode,
                    usd_context_name=self._context_name,
                )
        return capture_identifier

    def do(self):
        if not self._new_capture_identifier or self._new_capture_identifier == self._previous_capture_identifier:
            return None
        return self._apply(self._new_capture_identifier)

    def undo(self):
        if not self._previous_capture_identifier or self._previous_capture_identifier == self._new_capture_identifier:
            return None
        return self._apply(self._previous_capture_identifier)

    def redo(self):
        return self.do()


def register_commands():
    omni.kit.commands.register_all_commands_in_module(__name__)


def unregister_commands():
    omni.kit.commands.unregister_module_commands(__name__)
