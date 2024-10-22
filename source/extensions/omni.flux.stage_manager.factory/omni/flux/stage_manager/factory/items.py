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

from typing import Any

from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class StageManagerItem:
    def __init__(self, identifier: Any, data: Any = None, children: list["StageManagerItem"] | None = None):
        """
        An item that should be built by a context plugin and used by the interaction plugin and any of its children
        plugins.

        Args:
            identifier: An identifier for the item.
            data: Data associated with the item.
            children: Any children items that should be under the item in the interaction plugin tree.
        """
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._identifier = identifier
        self._data = data
        self._children = children or []

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_identifier": None,
            "_data": None,
            "_children": None,
        }

    @property
    def identifier(self) -> Any:
        """
        Returns:
            The identifier for the item.
        """
        return self._identifier

    @property
    def data(self) -> Any:
        """
        Returns:
            Data associated with the item.
        """
        return self._data

    @property
    def children(self) -> list["StageManagerItem"]:
        """
        Returns:
            Any children items that should be under the item in the interaction plugin tree.
        """
        return self._children

    def destroy(self):
        _reset_default_attrs(self)
