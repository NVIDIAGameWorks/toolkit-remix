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
from typing import Callable

import omni.kit.undo
import omni.kit.window.file
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.layer_manager.layer_types import LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {"_context": None, "_layer_manager": None, "_sub_stage_event": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context(context_name)
        self._layer_manager = _LayerManagerCore(context_name=context_name)
        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

    def open_stage(self, path, callback=None):
        omni.kit.window.file.open_stage(path)
        if callback:
            callback()

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.OPENED),
        ]:
            self._layer_manager.set_edit_target_layer(LayerType.replacement)

    def create_new_work_file(self):
        self._context.new_stage_with_callback(self._on_new_stage_created)

    def _on_new_stage_created(self, result: bool, error: str):
        asyncio.ensure_future(self._deferred_startup(self._context))

    @omni.usd.handle_exception
    async def _deferred_startup(self, context):
        """Or crash"""
        await omni.kit.app.get_app_interface().next_update_async()
        await context.new_stage_async()
        await omni.kit.app.get_app_interface().next_update_async()
        stage = context.get_stage()
        while (context.get_stage_state() in [omni.usd.StageState.OPENING, omni.usd.StageState.CLOSING]) or not stage:
            await asyncio.sleep(0.1)
        # set some metadata
        root_layer = stage.GetRootLayer()
        self._layer_manager.set_custom_data_layer_type(root_layer, _LayerType.workfile)

    def undo(self):
        omni.kit.undo.undo()

    def redo(self):
        omni.kit.undo.redo()

    def save(self, on_save_done: Callable[[bool, str], None] = None):
        omni.kit.window.file.save(on_save_done=on_save_done)

    def save_as(self, on_save_done: Callable[[bool, str], None] = None):
        omni.kit.window.file.save_as(False, on_save_done=on_save_done)

    def destroy(self):
        _reset_default_attrs(self)
