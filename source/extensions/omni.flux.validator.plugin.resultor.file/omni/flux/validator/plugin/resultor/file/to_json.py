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

from typing import Any, Tuple

import carb.tokens
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.validator.factory import ResultorBase as _ResultorBase
from omni.flux.validator.manager.core import validation_schema_json_encoder as _validation_schema_json_encoder
from pydantic import BaseModel, validator


class ToJson(_ResultorBase):
    class Data(_ResultorBase.Data):
        json_path: str

        @validator("json_path", allow_reuse=True)
        def json_path_empty(cls, v):  # noqa
            if not v.strip():
                raise ValueError("Path is empty")
            return v

    name = "ToJson"
    display_name = "To Json"
    tooltip = "This plugin will write the result of the schema into a json file"
    data_type = Data

    @omni.usd.handle_exception
    async def _result(self, schema_data: Data, schema: BaseModel) -> Tuple[bool, str]:
        """
        Function that will be called to work on the result

        Args:
            schema_data: the data from the schema.
            schema: the whole schema ran by the manager

        Returns: True if ok + message
        """
        json_path = carb.tokens.get_tokens_interface().resolve(schema_data.json_path)
        result = _path_utils.write_file(
            json_path,
            schema.json(indent=4, encoder=_validation_schema_json_encoder).encode("utf-8"),
            raise_if_error=False,
        )
        if not result:
            return False, f"Failed to write file {json_path}"
        return True, f"Result written in {json_path}, Ok"

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
