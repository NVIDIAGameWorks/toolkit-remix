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

from lightspeed.trex.packaging.core.repair import PackagingRepairAction as PackagingActions
from omni import ui
from omni.flux.utils.common import reset_default_attrs
from pxr import Sdf


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
        """Get the layer identifier of the packaging error item.

        Returns:
            The layer identifier that reported the unresolved asset.
        """
        return self._layer_identifier

    @property
    def prim_path(self) -> Sdf.Path:
        """Get the prim path of the packaging error item.

        Returns:
            The prim path that reported the unresolved asset.
        """
        return Sdf.Path(self._prim_path)

    @property
    def asset_path(self) -> str:
        """Get the original asset path.

        Returns:
            The unresolved asset path.
        """
        return self._asset_path

    @property
    def fixed_asset_path(self) -> str | None:
        """Get the fixed asset path.

        Returns:
            The replacement asset path, or ``None`` when the asset should be removed.
        """
        return self._fixed_asset_path

    @fixed_asset_path.setter
    def fixed_asset_path(self, value: str | None):
        """Set the fixed asset path.

        Args:
            value: Replacement asset path, original asset path, or ``None`` to remove the asset.
        """
        self._fixed_asset_path = value

    @property
    def action(self) -> PackagingActions:
        """Get the action to be taken on the packaging error item.

        Returns:
            The repair action implied by the fixed asset path.
        """
        if not self._fixed_asset_path:
            return PackagingActions.REMOVE_REFERENCE
        if self._fixed_asset_path != self._asset_path:
            return PackagingActions.REPLACE_ASSET
        return PackagingActions.IGNORE

    def destroy(self):
        """Destroy the item and clear attributes."""
        reset_default_attrs(self)
