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

from omni.flux.stage_manager.factory.plugins import StageManagerTreePlugin as _StageManagerTreePlugin
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeDelegate as _StageManagerTreeDelegate
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel
from pydantic import PrivateAttr


class StageManagerUSDTreeItem(_StageManagerTreeItem):
    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class StageManagerUSDTreeModel(_StageManagerTreeModel):
    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class StageManagerUSDTreeDelegate(_StageManagerTreeDelegate):
    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class StageManagerUSDTreePlugin(_StageManagerTreePlugin, abc.ABC):
    _context_name: str = PrivateAttr("")

    def set_context_name(self, name: str):
        """Set usd context to initialize plugin before items are rebuilt."""
        self._context_name = name

    @classmethod
    @property
    @abc.abstractmethod
    def model(cls) -> StageManagerUSDTreeModel:
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def delegate(cls) -> StageManagerUSDTreeDelegate:
        pass
