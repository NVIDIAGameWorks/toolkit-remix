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

__all__ = ["get_particle_system_attribute_type_map", "get_particle_system_attributes", "get_particle_system_prim"]

from lightspeed.common.constants import PARTICLE_PRIMVAR_PREFIX, PARTICLE_SCHEMA_NAME
from pxr import Usd, UsdGeom


def get_particle_system_prim() -> tuple[Usd.Stage, UsdGeom.Mesh]:
    stage = Usd.Stage.CreateInMemory()
    prim = UsdGeom.Mesh.Define(stage, "/DummyParticles").GetPrim()
    prim.ApplyAPI(PARTICLE_SCHEMA_NAME)
    # return stage_ref to keep prim alive
    return stage, prim


def get_particle_system_attributes() -> tuple[Usd.Stage, list[Usd.Attribute]]:
    stage, prim = get_particle_system_prim()
    attributes = [attr for attr in prim.GetAttributes() if attr.GetName().startswith(PARTICLE_PRIMVAR_PREFIX)]
    # return stage_ref to keep prim alive
    return stage, attributes


def get_particle_system_attribute_type_map() -> dict[str, str]:
    """
    Returns all the primvars available for the particle system schema + Their types.

    returns:
        - A dictionary mapping attr.GetName(): attr.GetTypeName()
    """
    _stage, attributes = get_particle_system_attributes()
    return {attr.GetName(): attr.GetTypeName() for attr in attributes}
