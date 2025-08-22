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

import omni.kit.commands
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME
from lightspeed.trex.schemas.particle import get_particle_system_attribute_type_map


class CreateParticleSystemCommand(omni.kit.commands.Command):
    """
    Appends the Particle System API Schema to a prim.

    It won't verify if the prim is a Mesh or Material or a prototype prim by design.
    Make sure to handle that before invoking the command.
    """

    def __init__(self, prim):
        self.target_prim = prim  # Fallback to prim if no prototype
        self.was_applied = False

    def do(self):
        if not self.target_prim.HasAPI(PARTICLE_SCHEMA_NAME):
            self.target_prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
            self.was_applied = True

    def undo(self):
        if self.was_applied:
            self.target_prim.RemoveAPI(PARTICLE_SCHEMA_NAME)


class RemoveParticleSystemCommand(omni.kit.commands.Command):
    """
    Removes the Particle System API Schema from a prim and removes all attributes.

    It won't verify if the prim is a Mesh or Material or a prototype prim by design.
    Make sure to handle that before invoking the command.
    """

    def __init__(self, prim):
        self.target_prim = prim  # Fallback to prim if no prototype
        self.prev_attr_values = {}
        self.had_api = self.target_prim.HasAPI(PARTICLE_SCHEMA_NAME)
        self.ps_attrib = get_particle_system_attribute_type_map()

    def do(self):
        if self.had_api:
            self.target_prim.RemoveAPI(PARTICLE_SCHEMA_NAME)
        for ps_attrib_name, _ps_attrib_type in self.ps_attrib.items():
            if self.target_prim.HasAttribute(ps_attrib_name):
                attr = self.target_prim.GetAttribute(ps_attrib_name)
                self.prev_attr_values[ps_attrib_name] = attr.Get()
                self.target_prim.RemoveProperty(ps_attrib_name)

    def undo(self):
        for name, value in self.prev_attr_values.items():
            sdf_type = self.ps_attrib[name]
            attr = self.target_prim.CreateAttribute(name, sdf_type)
            attr.Set(value)

        if self.had_api:
            self.target_prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
