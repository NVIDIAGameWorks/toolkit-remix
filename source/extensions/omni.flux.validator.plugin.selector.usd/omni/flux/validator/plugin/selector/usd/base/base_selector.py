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

from typing import Any

import omni.usd
from omni.flux.validator.factory import SelectorBase as _SelectorBase
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import Sdf


class SelectorUSDBase(_SelectorBase):
    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, context_plugin_data: _SetupDataTypeVar) -> None:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data of the plugin from the schema
        """
        context = omni.usd.get_context(context_plugin_data or "")
        if context and context.can_close_stage():
            stage = context.get_stage()
            root_layer = stage.GetRootLayer()
            # ugly work around to un-hold layers
            Sdf._TestTakeOwnership(root_layer)  # noqa
            await context.close_stage_async()
