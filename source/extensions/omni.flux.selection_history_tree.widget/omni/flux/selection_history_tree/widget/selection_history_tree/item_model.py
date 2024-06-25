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

from omni import ui


class SelectionHistoryItem(ui.AbstractItem):
    def __init__(self, title: str, data=None, tooltip: str = ""):
        super().__init__()
        self._title = title
        self._data = data
        self._tooltip = tooltip

    def is_valid(self) -> bool:
        """Return True is the item is valid or not"""
        return True

    @property
    def tooltip(self):
        """Tooltip of the item"""
        return self._tooltip

    @property
    def title(self) -> str:
        """
        The title is the property that will be displayed in the tree widget
        """
        return self._title

    @property
    def data(self) -> str:
        """Any data that the item needs to carry."""
        return self._data

    def __repr__(self):
        return f'"{self.title} {self.data}"'
