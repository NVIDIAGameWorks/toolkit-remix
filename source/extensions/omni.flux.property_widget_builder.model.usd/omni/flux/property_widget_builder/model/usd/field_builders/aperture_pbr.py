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

__all__ = ("MATERIAL_FIELD_BUILDERS",)


from ..item_delegates.drag import USDFloatDragField
from .base import USDBuilderList

MATERIAL_FIELD_BUILDERS = USDBuilderList()

# Material attributes
# These builders define Aperture PBR-specific UI bounds for attributes that need explicit policy beyond metadata.
# min_value/max_value are soft drag ranges; hard_min_value/hard_max_value clamp typed edits.

MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:opacity_constant", USDFloatDragField(hard_min_value=0.0, hard_max_value=1.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:reflection_roughness_constant", USDFloatDragField(hard_min_value=0.0, hard_max_value=1.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:metallic_constant", USDFloatDragField(hard_min_value=0.0, hard_max_value=1.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:thin_film_thickness_constant",
    USDFloatDragField(hard_min_value=0.0010000000474974513, max_value=1500.0),
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:emissive_intensity", USDFloatDragField(hard_min_value=0.0, max_value=65504.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:displace_in", USDFloatDragField(hard_min_value=0.0, max_value=2.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:displace_out", USDFloatDragField(hard_min_value=0.0, max_value=2.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:subsurface_measurement_distance", USDFloatDragField(hard_min_value=0.0, max_value=16.0)
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:subsurface_volumetric_anisotropy",
    USDFloatDragField(hard_min_value=-0.9900000095367432, hard_max_value=0.9900000095367432),
)
MATERIAL_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:subsurface_radius_scale", USDFloatDragField(hard_min_value=0.0, max_value=16.0)
)
