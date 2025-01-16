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

from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class TreeItemBase(ui.AbstractItem):
    def __init__(self, children: list["TreeItemBase"] | None = None):
        """
        A base Item class to be overridden and used with the TreeWidget.
        """
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._children = children if children is not None else []

    @property
    @abc.abstractmethod
    def default_attr(self) -> dict[str, None]:
        return {"_children": None}

    @property
    def children(self) -> list["TreeItemBase"]:
        return self._children

    @property
    @abc.abstractmethod
    def can_have_children(self) -> bool:
        raise NotImplementedError()

    def destroy(self):
        _reset_default_attrs(self)


class AlternatingRowItem(ui.AbstractItem):
    def __init__(self, index: int):
        super().__init__()

        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._alternate = index % 2 == 0

    @property
    def default_attr(self) -> dict[str, None]:
        return {"_alternate": None}

    @property
    def alternate(self) -> bool:
        return self._alternate

    def destroy(self):
        _reset_default_attrs(self)
