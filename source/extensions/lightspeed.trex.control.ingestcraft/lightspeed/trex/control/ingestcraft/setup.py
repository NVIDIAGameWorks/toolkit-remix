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

import omni.kit.app
import omni.usd
from lightspeed.trex.contexts import get_instance as _trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from lightspeed.trex.layout.ingestcraft import get_instance as _get_layout_instance
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Setup:
    def __init__(self):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)
        self._context_name = _TrexContexts.INGEST_CRAFT.value
        self._context = _trex_contexts_instance().get_usd_context(_TrexContexts.INGEST_CRAFT)
        self._layout_instance = _get_layout_instance()
        self._context.new_stage_with_callback(self._on_new_stage_created)

    def _on_new_stage_created(self, result: bool, error: str):
        asyncio.ensure_future(self._deferred_startup(self._context))

    @omni.usd.handle_exception
    async def _deferred_startup(self, context):
        """Or crash"""
        await omni.kit.app.get_app_interface().next_update_async()
        await context.new_stage_async()
        await omni.kit.app.get_app_interface().next_update_async()

    def destroy(self):
        _reset_default_attrs(self)
