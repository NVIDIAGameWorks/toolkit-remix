"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from lightspeed.trex.schemas.particle import get_particle_system_attributes


def get_particle_lookup_table() -> dict:
    """
    Retrieves schema data from RemixParticleSystemSchemaAPI to build a lookup table with
    user-friendly names, tooltips from doc attributes, and UI groups.

    Returns:
        Dict: A lookup table mapping attribute names to display information containing:
            - name: User-friendly display name
            - tooltip: Documentation from schema doc attribute
            - group: UI group from customData uiGroup
    """
    # We create a dummy stage just to instantiate a prim with the particle system schema and fetch the info.
    _temp_stage, attributes = get_particle_system_attributes()
    table = {
        attr.GetName(): {
            "name": attr.GetDisplayName(),
            "tooltip": attr.GetDocumentation(),
            "group": attr.GetDisplayGroup(),
        }
        for attr in attributes
    }
    return table
