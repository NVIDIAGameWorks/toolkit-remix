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

import abc

from omni.flux.stage_manager.factory import StageManagerDataTypes as _StageManagerDataTypes
from omni.flux.stage_manager.factory.plugins import StageManagerInteractionPlugin as _StageManagerInteractionPlugin
from pydantic import PrivateAttr


class StageManagerUSDInteractionPlugin(_StageManagerInteractionPlugin, abc.ABC):

    _context_name: str | None = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._context_name = ""

    @classmethod
    @property
    def compatible_data_type(cls):
        return _StageManagerDataTypes.USD

    def _update_context_items(self):
        if hasattr(self._context, "context_name"):
            self._set_context_name(self._context.context_name)

        super()._update_context_items()

    def _set_context_name(self, value: str):
        attribute_name = "context_name"

        self._context_name = value

        # Propagate the value
        if hasattr(self.tree, attribute_name):
            self.tree.context_name = value

        for filter_plugin in self.filters:
            if hasattr(filter_plugin, attribute_name):
                filter_plugin.context_name = value

        for column_plugin in self.columns:
            if hasattr(column_plugin, attribute_name):
                column_plugin.context_name = value

            for widget_plugin in column_plugin.widgets:
                if hasattr(widget_plugin, attribute_name):
                    widget_plugin.context_name = value

        for context_filter_plugin in self.context_filters:
            if hasattr(context_filter_plugin, attribute_name):
                context_filter_plugin.context_name = value
