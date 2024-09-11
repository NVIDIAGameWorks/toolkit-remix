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

from typing import TYPE_CHECKING

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
        tooltip: str,
        children: list["LightGroupsItem"] | None = None,
        prim: "Usd.Prim" = None,
        light_type: _LightTypes | None = None,
    ):
        """
        Create a Light Group Item

        Args:
            display_name: The name to display in the Tree
            tooltip: The tooltip to display when hovering an item in the Tree
            children: The children items. Because the Lights Group is a flat list, this should ONLY BE SET for virtual
                      groups
            prim: The prim associated with the light. This should NOT BE SET for virtual groups
            light_type: The type of light to be grouped. This should ONLY BE SET for virtual groups
        """

        super().__init__(display_name, tooltip, children=children, prim=prim, is_virtual=prim is None)

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

    def refresh(self):
        self._items.clear()

        # Expect all the light prims to be present in the context_items, so no need to recursively look for children
        grouped_items = {}
        for prim in self.context_items:
            # Beautified names for the light type for the UI
            type_name = prim.GetTypeName()
            if type_name not in grouped_items:
                grouped_items[type_name] = []
            grouped_items[type_name].append(LightGroupsItem(str(prim.GetPath().name), str(prim.GetPath()), prim=prim))

        for type_name, items in grouped_items.items():
            light_type = _get_light_type(type_name)
            if not light_type:
                continue
            # Since this is a group, make plural
            display_name = f"{light_type.value}s"
            self._items.append(
                LightGroupsItem(display_name, f"{display_name} Group", children=items, light_type=light_type)
            )

        self._item_changed(None)


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
