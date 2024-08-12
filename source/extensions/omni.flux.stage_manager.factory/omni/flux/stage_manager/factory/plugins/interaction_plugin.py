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

from pydantic import Field

from .base import StageManagerUIPluginBase as _StageManagerUIPluginBase
from .column_plugin import StageManagerColumnPlugin as _StageManagerColumnPlugin
from .filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin
from .tree_plugin import StageManagerTreePlugin as _StageManagerTreePlugin


class StageManagerInteractionPlugin(_StageManagerUIPluginBase, abc.ABC):
    """
    A plugin that encompasses other plugins in the Stage Manager.
    The Interaction Plugin builds the TreeWidget and uses the filter, column & widget plugins to build the contents.
    """

    tree: _StageManagerTreePlugin = Field(...)
    filters: set[_StageManagerFilterPlugin] = Field(...)
    columns: list[_StageManagerColumnPlugin] = Field(...)

    @classmethod
    @property
    @abc.abstractmethod
    def compatible_trees(cls) -> list[str]:
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def compatible_filters(cls) -> list[str]:
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def compatible_widgets(cls) -> list[str]:
        pass

    @classmethod
    def check_compatibility(cls, value: Any, compatible_items: dict[Any, Any] | None) -> Any:
        if value not in (compatible_items or {}):
            raise ValueError(
                f"The selected plugin is not compatible with this plugin -> {value}\n"
                f"  Compatible plugin(s): {', '.join(compatible_items)}"
            )
        return value

    def build_ui(self):  # noqa PLW0221
        # TODO build the ui with Filters & Tree Widget
        pass
