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

from pathlib import Path

from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class ModSelectionItem(ui.AbstractItem):
    def __init__(self, path: Path):
        super().__init__()

        self._default_attr = {
            "_path": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    @property
    def title(self) -> str:
        """
        Will return the mod directory + mod file.

        For example: C:/rtx-remix/mods/Mod1/mod.usda -> Mod1/mod.usda
        """
        return str(Path(self.path.parent.stem) / self.path.name)

    def __repr__(self):
        return str(self.path)

    def destroy(self):
        _reset_default_attrs(self)
