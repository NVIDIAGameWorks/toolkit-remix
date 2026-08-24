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

from __future__ import annotations

__all__ = ["MeshPrimsFilterPlugin"]

from typing import TYPE_CHECKING

from lightspeed.trex.utils.common.prim_utils import (
    is_empty_mesh_prim,
    is_in_light_group,
    is_instance,
    is_mesh_prototype,
)
from omni.flux.stage_manager.plugin.filter.usd.base import ToggleableUSDFilterPlugin
from pydantic import Field

if TYPE_CHECKING:
    from pxr import Usd


class MeshPrimsFilterPlugin(ToggleableUSDFilterPlugin):
    display_name: str = Field(default="Mesh Prims", exclude=True)
    tooltip: str = Field(default="Filter for mesh prims", exclude=True)

    include_instances: bool = Field(
        default=True, description="Whether the filter should also include instances with the meshes or not."
    )

    def _filter_predicate(self, prim: Usd.Prim) -> bool:
        """Return whether a prim belongs in the mesh filter.

        Args:
            prim: Prim to evaluate.

        Returns:
            Whether the prim is a Mesh, GeomSubset, empty mesh-root container, or eligible included non-light instance.
        """
        if not prim:
            return False

        prim_path = str(prim.GetPath())
        return bool(
            is_mesh_prototype(prim, prim_path=prim_path)
            or is_empty_mesh_prim(prim, prim_path=prim_path)
            or (
                self.include_instances
                and is_instance(prim, prim_path=prim_path)
                and not is_in_light_group(prim, prim_path=prim_path)
            )
        )
