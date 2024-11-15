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
from omni.flux.stage_manager.factory.plugins import StageManagerContextPlugin as _StageManagerContextPlugin
from omni.flux.stage_manager.factory.plugins import StageManagerListenerPlugin as _StageManagerListenerPlugin


class StageManagerUSDContextPlugin(_StageManagerContextPlugin, abc.ABC):
    listeners: list[_StageManagerListenerPlugin] = [
        {"name": "StageManagerUSDLayersListenerPlugin"},
        {"name": "StageManagerUSDNoticeListenerPlugin"},
        {"name": "StageManagerUSDStageListenerPlugin"},
    ]

    @classmethod
    @property
    @abc.abstractmethod
    def context_name(cls):
        pass

    @classmethod
    @property
    def data_type(cls):
        return _StageManagerDataTypes.USD

    def setup(self):
        for listener in self.listeners:
            if hasattr(listener, "set_context_name"):
                listener.set_context_name(self.context_name)

        super().setup()

    class Config(_StageManagerContextPlugin.Config):
        fields = {
            **_StageManagerContextPlugin.Config.fields,
            "listeners": {"exclude": True},
        }
