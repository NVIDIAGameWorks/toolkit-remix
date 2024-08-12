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

from omni.flux.utils.widget.tree_widget import TreeDelegateBase as _TreeDelegateBase
from omni.flux.utils.widget.tree_widget import TreeItemBase as _TreeItemBase
from omni.flux.utils.widget.tree_widget import TreeModelBase as _TreeModelBase

from .base import StageManagerPluginBase as _StageManagerPluginBase


class StageManagerTreeItem(_TreeItemBase):
    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    @property
    def can_have_children(self) -> bool:
        return self._children is not None


class StageManagerTreeModel(_TreeModelBase[_TreeItemBase]):

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class StageManagerTreeDelegate(_TreeDelegateBase):

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _build_widget(
        self,
        model: StageManagerTreeModel,
        item: StageManagerTreeItem,
        column_id: int,
        level: int,
        expanded: bool,
    ):
        # TODO Implement logic to build ui from other plugins here
        # TODO Data should come from StageManagerCore
        pass

    def _build_header(self, column_id: int):
        # TODO Implement logic to build ui from other plugins here
        # TODO Data should come from StageManagerCore
        pass


class StageManagerTreePlugin(_StageManagerPluginBase, abc.ABC):
    """
    A TreeWidget delegate to be used within an Interaction Plugin
    """

    @classmethod
    @property
    @abc.abstractmethod
    def model(cls) -> type[StageManagerTreeModel]:
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def delegate(cls) -> type[StageManagerTreeDelegate]:
        pass
