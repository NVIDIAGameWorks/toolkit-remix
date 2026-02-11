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
from typing import ClassVar

from omni.flux.factory.base import PluginBase as _PluginBase
from pydantic import BaseModel, ConfigDict, Field


class StageManagerPluginBase(_PluginBase, BaseModel, abc.ABC):
    """
    An abstract base class for stage manager plugins.
    """

    name: ClassVar[str] = Field(description="The name of the plugin")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__(*args, **kwargs)
        cls.name = cls.__name__

    def __eq__(self, other):
        if isinstance(other, StageManagerPluginBase):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    def dict(self, *args, **kwargs):
        # Override the dict method to include the `name` property
        data = super().dict(*args, **kwargs)
        data["name"] = self.name
        return data


class StageManagerUIPluginBase(StageManagerPluginBase, abc.ABC):
    """
    An abstract base class for stage manager plugins that should build UI.
    """

    enabled: bool = Field(default=True, description="Whether the plugin should be enabled or not")

    display_name: str = Field(description="The string to display when displaying the plugin in the UI", exclude=True)
    tooltip: str = Field(description="The tooltip to display when hovering over the plugin in the UI", exclude=True)

    @abc.abstractmethod
    def build_ui(self, *args, **kwargs):
        """
        The method used to build the UI for the plugin.
        """
        pass
