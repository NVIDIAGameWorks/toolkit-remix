"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["CreateReferenceOwnerSpecCommand"]

import omni.kit.commands
from omni.kit.usd_undo import UsdLayerUndo
from pxr import Sdf


class CreateReferenceOwnerSpecCommand(omni.kit.commands.Command):
    """Create an owner override and remove only its new branch on Undo."""

    def __init__(self, layer: Sdf.Layer, prim_path: Sdf.Path):
        """Store the layer and owner path. The caller runs this only when the layer has no spec at prim_path.

        Args:
            layer: Edit target layer that receives the owner override.
            prim_path: Absolute path of the reference owner prim.
        """
        self._layer = layer
        self._prim_path = prim_path

    def do(self) -> None:
        """Reserve the highest missing ancestor before creating the owner override."""
        missing_root = self._prim_path
        parent = missing_root.GetParentPath()
        while parent != Sdf.Path.absoluteRootPath and self._layer.GetPrimAtPath(parent) is None:
            missing_root = parent
            parent = parent.GetParentPath()
        self._undo = UsdLayerUndo(self._layer)
        self._undo.reserve(missing_root)
        with Sdf.ChangeBlock():
            Sdf.CreatePrimInLayer(self._layer, self._prim_path)

    def undo(self) -> None:
        """Remove the owner branch that did not exist before Apply."""
        self._undo.undo()
