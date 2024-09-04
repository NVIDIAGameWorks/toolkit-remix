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
from pxr import Usd
from pydantic import Field


class StageManagerUSDTreeItem(_StageManagerTreeItem):
    def __init__(
        self,
        display_name: str,
        tooltip: str,
        children: list["StageManagerUSDTreeItem"] | None = None,
        prim: "Usd.Prim" = None,
    ):
        super().__init__(display_name, tooltip=tooltip, children=children, data={"prim": prim})

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class StageManagerUSDTreeModel(_StageManagerTreeModel[Usd.Prim]):
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
    context_name: str = Field("", description="The context name provided by the context plugin", exclude=True)

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
