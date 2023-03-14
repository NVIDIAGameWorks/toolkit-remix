"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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

        For example: C:/rtx_remix/mods/Mod1/mod.usda -> Mod1/mod.usda
        """
        return str(Path(self.path.parent.stem) / self.path.name)

    def __repr__(self):
        return str(self.path)

    def destroy(self):
        _reset_default_attrs(self)
