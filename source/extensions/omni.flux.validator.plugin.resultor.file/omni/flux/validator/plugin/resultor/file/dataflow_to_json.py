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

from pathlib import Path
from typing import Any

import carb.tokens
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import ResultorBase as _ResultorBase
from pydantic import BaseModel, Field, field_validator


class DataflowToJson(_ResultorBase):
    class Data(_ResultorBase.Data):
        json_path: str = Field(...)

        @field_validator("json_path", mode="before")
        @classmethod
        def json_path_empty(cls, v: str) -> str:
            if not v.strip():
                raise ValueError("Path is empty")
            return v

    name = "DataflowToJson"
    display_name = "Dataflow To Json"
    tooltip = "This plugin will write the result of the schema into a json file"
    data_type = Data

    @omni.usd.handle_exception
    async def _result(self, schema_data: Data, schema: BaseModel) -> tuple[bool, str]:
        """
        Function that will be called to work on the result

        Args:
            schema_data: the data from the schema.
            schema: the whole schema ran by the manager

        Returns: True if ok + message
        """
        json_path = carb.tokens.get_tokens_interface().resolve(schema_data.json_path)

        output_paths = []
        for data_flow in self._get_schema_data_flows(schema_data, schema):
            if not isinstance(data_flow, _InOutDataFlow):
                continue
            for output_path in data_flow.output_data or []:
                output_paths.append(output_path)

        # Make sure the parent directory exists
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)

        # Write the JSON file
        result = _path_utils.write_json_file(json_path, {"output_paths": output_paths}, raise_if_error=False)

        if not result:
            return False, f"Failed to write file {json_path}"
        return True, f"Result written in {json_path}, Ok"

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        pass

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
