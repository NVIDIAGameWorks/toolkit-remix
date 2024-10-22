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

from typing import TYPE_CHECKING, Iterable

from omni.flux.stage_manager.factory import StageManagerItem as _StageManagerItem
from omni.flux.utils.common.lights import LightTypes as _LightTypes
from omni.flux.utils.common.lights import get_light_type as _get_light_type

from .virtual_groups import VirtualGroupsDelegate as _VirtualGroupsDelegate
from .virtual_groups import VirtualGroupsItem as _VirtualGroupsItem
from .virtual_groups import VirtualGroupsModel as _VirtualGroupsModel
from .virtual_groups import VirtualGroupsTreePlugin as _VirtualGroupsTreePlugin

if TYPE_CHECKING:
    from pxr import Usd


class LightGroupsItem(_VirtualGroupsItem):
    def __init__(
        self,
        display_name: str,
        data: Usd.Prim | None,
        tooltip: str = None,
        children: list["LightGroupsItem"] | None = None,
        light_type: _LightTypes | None = None,
    ):
        """
        Create a Light Group Item

        Args:
            display_name: The name to display in the Tree
            data: The USD Prim this item represents
            tooltip: The tooltip to display when hovering an item in the TreeView
            children: The children items.
                      Because the Lights Group is a flat list, this should ONLY BE SET for virtual groups
            light_type: The type of light to be grouped. Will be used to determine the icon
        """

        super().__init__(display_name, data, tooltip=tooltip, children=children, is_virtual=data is None)

        self._light_type = light_type

    @property
    def default_attr(self) -> dict[str, None]:
        default_attr = super().default_attr
        default_attr.update(
            {
                "_light_type": None,
            }
        )
        return default_attr

    @property
    def icon(self):
        match self._light_type:
            case _LightTypes.CylinderLight:
                return "CylinderLightStatic"
            case _LightTypes.DiskLight:
                return "DiskLightStatic"
            case _LightTypes.DistantLight:
                return "DistantLightStatic"
            case _LightTypes.DomeLight:
                return "DomeLightStatic"
            case _LightTypes.PortalLight:
                return "PortalLightStatic"
            case _LightTypes.RectLight:
                return "RectLightStatic"
            case _LightTypes.SphereLight:
                return "SphereLightStatic"
        return None


class LightGroupsModel(_VirtualGroupsModel):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def _build_items(self, items: Iterable[_StageManagerItem]) -> list[LightGroupsItem] | None:
        tree_items = []

        # Expect the interaction to pass a flat list, so no need to build recursively
        # Group prims by light type & build the items for every light
        grouped_items = {}
        for item in items:
            # Beautified names for the light type for the UI
            type_name = item.data.GetTypeName()
            if type_name not in grouped_items:
                grouped_items[type_name] = []
            prim_path = item.data.GetPath()
            grouped_items[type_name].append(
                LightGroupsItem(
                    str(prim_path.name), item.data, tooltip=str(prim_path), light_type=_get_light_type(type_name)
                )
            )

        # Build the group items with the associated children items
        for type_name, children in grouped_items.items():
            light_type = _get_light_type(type_name)
            if not light_type:
                continue
            # Since this is a group, make plural
            display_name = f"{light_type.value}s"
            tree_items.append(LightGroupsItem(display_name, None, tooltip=f"{display_name} Group", children=children))

        return tree_items


class LightGroupsDelegate(_VirtualGroupsDelegate):
    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr


class LightGroupsTreePlugin(_VirtualGroupsTreePlugin):
    """
    A flat list of prims that can be grouped using virtual groups
    """

    model: LightGroupsModel = None
    delegate: LightGroupsDelegate = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.model = LightGroupsModel()
        self.delegate = LightGroupsDelegate()
