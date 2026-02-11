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

__all__ = ["PackagingActions", "PackagingErrorItem"]

from enum import Enum

from omni import ui
from omni.flux.utils.common import reset_default_attrs
from pxr import Sdf


class PackagingActions(Enum):
    """
    Enum for the actions that can be taken on a packaging error.
    """

    IGNORE = "Ignore"
    REPLACE_ASSET = "Replace Asset"
    REMOVE_REFERENCE = "Remove Reference"


class PackagingErrorItem(ui.AbstractItem):
    def __init__(self, layer_identifier: str, prim_path: str, asset_path: str):
        super().__init__()

        self._default_attr = {
            "_layer_identifier": None,
            "_prim_path": None,
            "_asset_path": None,
            "_fixed_asset_path": None,
        }
        for attr, val in self._default_attr.items():
            setattr(self, attr, val)

        self._layer_identifier = layer_identifier
        self._prim_path = prim_path
        self._asset_path = asset_path
        self._fixed_asset_path = asset_path

    @property
    def layer_identifier(self) -> str:
        """
        The layer identifier of the packaging error item
        """
        return self._layer_identifier

    @property
    def prim_path(self) -> Sdf.Path:
        """
        The prim path of the packaging
        """
        return Sdf.Path(self._prim_path)

    @property
    def asset_path(self) -> str:
        """
        The original asset path of the packaging error item
        """
        return self._asset_path

    @property
    def fixed_asset_path(self) -> str | None:
        """
        The fixed asset path of the packaging error item
        """
        return self._fixed_asset_path

    @fixed_asset_path.setter
    def fixed_asset_path(self, value: str):
        """
        Set the fixed asset path of the packaging error item
        """
        self._fixed_asset_path = value

    @property
    def action(self) -> PackagingActions:
        """
        Get the action to be taken on the packaging error item
        """
        if not self._fixed_asset_path:
            return PackagingActions.REMOVE_REFERENCE
        if self._fixed_asset_path != self._asset_path:
            return PackagingActions.REPLACE_ASSET
        return PackagingActions.IGNORE

    def destroy(self):
        reset_default_attrs(self)
