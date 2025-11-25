# noqa PLC0302
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
import carb
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import read_json_file as _read_json_file

from .schema import StageManagerSchema as _StageManagerSchema

_SCHEMA_PATH_SETTING = "/exts/omni.flux.stage_manager.core/schema"
STAGE_MANAGER_CORE_INSTANCE: "StageManagerCore | None" = None


def set_instance(instance: "StageManagerCore"):
    global STAGE_MANAGER_CORE_INSTANCE
    STAGE_MANAGER_CORE_INSTANCE = instance


def get_instance():
    global STAGE_MANAGER_CORE_INSTANCE
    return STAGE_MANAGER_CORE_INSTANCE


class StageManagerCore:
    """
    Core extension used to orchestrate and manage the StageManager.
    The `StageManagerCore` relies on a `StageManagerSchema` to define its internal data structure.
    """

    def __init__(self, schema_path: str | None = None):
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._schema = None

        schema_path = schema_path or carb.settings.get_settings().get(_SCHEMA_PATH_SETTING)
        if not schema_path:
            raise ValueError("Schema path not provided. Please configure it in settings or pass as argument.")

        self.setup(_read_json_file(schema_path))

    @property
    def default_attr(self) -> dict[str, None]:
        return {"_schema": None}

    @property
    def schema(self) -> _StageManagerSchema:
        return self._schema

    def setup(self, schema_dict: dict):
        schema = _StageManagerSchema(**schema_dict)
        schema.context.setup()

        for interaction in schema.interactions:
            if not interaction.enabled:
                continue
            # Set the context data in the interaction plugins
            interaction.setup(schema.context)

        self._schema = schema

    def get_active_interaction(self):
        if not self.schema or not self.schema.interactions:
            return None

        for interaction in self.schema.interactions:
            if interaction.is_active:
                return interaction
        return None

    def destroy(self):
        _reset_default_attrs(self)
