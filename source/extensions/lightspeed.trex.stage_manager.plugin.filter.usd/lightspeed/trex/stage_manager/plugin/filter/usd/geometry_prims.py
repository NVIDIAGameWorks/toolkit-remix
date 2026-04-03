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

from __future__ import annotations

__all__ = ["GeometryPrimsFilterPlugin"]

from typing import TYPE_CHECKING

from lightspeed.trex.utils.common.prim_utils import is_empty_mesh_prim
from omni.flux.stage_manager.plugin.filter.usd.base import ToggleableUSDFilterPlugin
from pxr import UsdGeom
from pydantic import Field

if TYPE_CHECKING:
    from pxr import Usd


class GeometryPrimsFilterPlugin(ToggleableUSDFilterPlugin):
    """Lightspeed-specific geometry prim filter for the Stage Manager.

    The omni.flux ``GeometryPrimsFilterPlugin`` has been removed from
    ``omni.flux.stage_manager.plugin.filter.usd``; this class is now the sole
    implementation registered under that name in the ``StageManagerFactory``.

    The reason a lightspeed-specific implementation is needed: the generic version
    only passes prims that are currently typed as ``UsdGeom.Mesh``.  In Remix,
    deleting a mesh's capture reference strips its children — leaving a bare
    ``Xform`` shell that is no longer a ``Mesh`` — so we add ``is_empty_mesh_prim``
    to keep those deleted-capture prims visible in the Geometry filter and the
    All-Prims tab.
    """

    display_name: str = Field(default="Geometry Prims", exclude=True)
    tooltip: str = Field(default="Filter for geometry prims", exclude=True)

    def _filter_predicate(self, prim: Usd.Prim) -> bool:
        if not prim:
            return False
        return prim.IsA(UsdGeom.Mesh) or is_empty_mesh_prim(prim)
