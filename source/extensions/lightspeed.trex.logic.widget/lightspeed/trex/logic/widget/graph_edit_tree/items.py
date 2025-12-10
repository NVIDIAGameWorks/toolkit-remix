"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

__all__ = ["GraphEditTreeItem"]

from typing import TYPE_CHECKING

from omni.flux.utils.widget.tree_widget import TreeItemBase

if TYPE_CHECKING:
    from pxr import Sdf


class GraphEditTreeItem(TreeItemBase):
    def __init__(self, prim_path: Sdf.Path):
        super().__init__()

        self._prim_path = prim_path

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_prim_path": None,
            }
        )
        return default_attr

    @property
    def can_have_children(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return self._prim_path.name

    @property
    def parent_path(self) -> str:
        return str(self._prim_path.GetParentPath())

    @property
    def prim_path(self) -> str:
        return str(self._prim_path)
