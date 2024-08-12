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

from omni.flux.factory.base import PluginBase as _PluginBase
from pydantic import BaseModel


class StageManagerPluginBase(_PluginBase, BaseModel, abc.ABC):
    """
    An abstract base class for stage manager plugins.
    """

    @classmethod
    @property
    def name(cls) -> str:
        return cls.__name__

    def __eq__(self, other):
        if isinstance(other, StageManagerPluginBase):
            return self.name == other.name
        return False

    def __hash__(self):
        return hash(self.name)

    class Config:
        arbitrary_types_allowed = True


class StageManagerUIPluginBase(StageManagerPluginBase, abc.ABC):
    """
    An abstract base class for stage manager plugins that should build UI.
    """

    enabled: bool = True

    @classmethod
    @property
    @abc.abstractmethod
    def display_name(cls) -> str:
        """
        The string to display when displaying the plugin in the UI
        """
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def tooltip(cls) -> str:
        """
        The tooltip to display when hovering over the plugin in the UI
        """
        pass

    @abc.abstractmethod
    def build_ui(self, *args, **kwargs):
        """
        The method used to build the UI for the plugin.
        """
        pass
