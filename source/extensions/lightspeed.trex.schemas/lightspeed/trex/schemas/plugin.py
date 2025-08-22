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

__all__ = ["LightspeedSchemaPluginRegistry"]

import os

from lightspeed.common.constants import PARTICLE_SCHEMA_NAME
from pxr import Plug


class LightspeedSchemaPluginRegistry:
    def __init__(self):
        self._schema_to_source: dict[str, tuple[str, str]] = {}
        self._register_plugins()

    def register_schema(self, schema_name: str, source_path: str, prim_path: str):
        if not os.path.exists(source_path):
            raise ValueError(f"Schema source path '{source_path}' does not exist.")
        self._schema_to_source[schema_name] = (source_path, prim_path)

    def lookup_schema(self, schema_name: str) -> tuple[str, str]:
        return self._schema_to_source[schema_name]

    def _register_plugins(self):
        plugins_root = os.path.join(os.path.dirname(__file__), "../../../usd/plugins")
        remix_particle_system_path = os.path.join(plugins_root, "RemixParticleSystem/resources")
        remix_particle_system_schema_path = os.path.join(plugins_root, "RemixParticleSystem/generatedSchema.usda")

        if not os.path.exists(remix_particle_system_path):
            raise FileNotFoundError(f"Plugin directory not found: {remix_particle_system_path}")

        self.register_schema(PARTICLE_SCHEMA_NAME, remix_particle_system_schema_path, "/ParticleSystemAPI")

        # Register the plugin directory with USD
        Plug.Registry().RegisterPlugins(remix_particle_system_path)
