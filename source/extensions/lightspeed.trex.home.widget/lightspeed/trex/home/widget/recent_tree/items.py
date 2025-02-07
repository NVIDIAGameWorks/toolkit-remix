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

__all__ = ["RecentProjectItem"]

from pathlib import Path

from omni.flux.utils.widget.tree_widget import TreeItemBase


class RecentProjectItem(TreeItemBase):
    def __init__(self, name: str, thumbnail: str, details: dict):
        super().__init__()
        self._name = name
        self._thumbnail = thumbnail
        self._details = details

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_name": None,
                "_thumbnail": None,
                "_details": None,
            }
        )
        return default_attr

    @property
    def name(self) -> str:
        """
        Returns:
            The project name
        """
        return self._details.get("Name") or self._name

    @property
    def thumbnail(self) -> str:
        """
        Returns:
            The project thumbnail
        """
        return self._thumbnail

    @property
    def path(self) -> str | None:
        """
        Returns:
            The project path
        """
        return self._details.get("Path")

    @property
    def game(self) -> str | None:
        """
        Returns:
            The project game
        """
        return self._details.get("Game")

    @property
    def capture(self) -> str | None:
        """
        Returns:
            The project capture
        """
        return self._details.get("Capture")

    @property
    def version(self) -> str | None:
        """
        Returns:
            The project version
        """
        return self._details.get("Version")

    @property
    def last_modified(self) -> str | None:
        """
        Returns:
            The project last modified date
        """
        return self._details.get("Published")

    @property
    def exists(self) -> bool:
        """
        Returns:
            Whether the project exists or not (was deleted)
        """
        return Path(self.path).exists()

    @property
    def can_have_children(self) -> bool:
        """
        Returns:
            Whether the item can have children or not
        """
        return False
