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
from typing import Any

from omni import usd
from omni.flux.stage_manager.factory.plugins import StageManagerTreePlugin as _StageManagerTreePlugin
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeDelegate as _StageManagerTreeDelegate
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeModel as _StageManagerTreeModel
from pydantic import Field, PrivateAttr


class StageManagerUSDTreeItem(_StageManagerTreeItem):
    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class StageManagerUSDTreeModel(_StageManagerTreeModel):
    def __init__(self, context_name: str = ""):
        super().__init__()

        self._context_name = context_name

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update({"_context_name": None})
        return default_attr

    def set_context_name(self, name: str):
        """Set usd context to initialize plugin before items are rebuilt."""
        self._context_name = name

    def get_context_menu_payload(self, item: StageManagerUSDTreeItem) -> dict[str, Any]:
        payload = super().get_context_menu_payload(item)
        payload.update(
            {
                "context_name": self._context_name,
                "selected_paths": usd.get_context(self._context_name).get_selection().get_selected_prim_paths(),
            }
        )
        return payload


class StageManagerUSDTreeDelegate(_StageManagerTreeDelegate):
    def __init__(self, header_height: int = 24, row_height: int = 24):
        super().__init__(header_height=header_height, row_height=row_height)
        self._context_name: str = ""

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update({"_context_name": None})
        return default_attr

    def set_context_name(self, name: str):
        """Set usd context to initialize plugin before items are rebuilt."""
        self._context_name = name


class StageManagerUSDTreePlugin(_StageManagerTreePlugin, abc.ABC):
    model: StageManagerUSDTreeModel = Field(...)
    delegate: StageManagerUSDTreeDelegate = Field(...)

    _context_name: str = PrivateAttr(default="")

    def set_context_name(self, name: str):
        """Set usd context to initialize plugin before items are rebuilt."""
        self._context_name = name
        self.model.set_context_name(name)
        self.delegate.set_context_name(name)
