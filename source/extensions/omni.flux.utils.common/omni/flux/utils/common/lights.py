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

__all__ = ["LightTypes", "get_light_type", "get_light_type_from_type_name"]

from enum import Enum

from pxr import Usd


class LightTypes(Enum):
    """
    The various USD Lux light types and their display names.
    """

    CylinderLight = "Cylinder Light"
    DiskLight = "Disk Light"
    DistantLight = "Distant Light"
    DomeLight = "Dome Light"
    PortalLight = "Portal Light"
    RectLight = "Rect Light"
    SphereLight = "Sphere Light"


def get_light_type(prim: Usd.Prim) -> LightTypes | None:
    """Classify a prim by its light schema family, including derived and versioned schemas.

    Returns:
        The light type, or None for an invalid prim or an unsupported schema.
    """
    if not prim.IsValid():
        return None

    for light_type in LightTypes:
        if prim.IsInFamily(light_type.name):
            return light_type
    return None


def get_light_type_from_type_name(class_name: str) -> LightTypes | None:
    """
    Get the LightTypes enum value for a given USD Lux light class name.

    Args:
        class_name: The USD Lux class name. Can be obtained by executing `prim.GetTypeName()`

    Returns:
        The LightTypes, or None if not found.
    """
    light_type_map = {
        "CylinderLight": LightTypes.CylinderLight,
        "DiskLight": LightTypes.DiskLight,
        "DistantLight": LightTypes.DistantLight,
        "DomeLight": LightTypes.DomeLight,
        "DomeLight_1": LightTypes.DomeLight,
        "PortalLight": LightTypes.PortalLight,
        "RectLight": LightTypes.RectLight,
        "SphereLight": LightTypes.SphereLight,
    }
    return light_type_map.get(class_name)
