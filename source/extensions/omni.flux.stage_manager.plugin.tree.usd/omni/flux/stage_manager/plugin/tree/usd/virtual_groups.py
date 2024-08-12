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

from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeDelegate as _StageManagerTreeDelegate
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel

from .base import StageManagerUSDTreePlugin as _StageManagerUSDTreePlugin


class VirtualGroupsItem(_StageManagerTreeItem):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class VirtualGroupsModel(_StageManagerTreeModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class VirtualGroupsDelegate(_StageManagerTreeDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class VirtualGroupsPlugin(_StageManagerUSDTreePlugin):
    model: type[VirtualGroupsModel] = VirtualGroupsModel
    delegate: type[VirtualGroupsDelegate] = VirtualGroupsDelegate
