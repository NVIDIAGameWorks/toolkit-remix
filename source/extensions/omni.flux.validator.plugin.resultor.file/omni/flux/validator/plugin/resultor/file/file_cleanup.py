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

from typing import TYPE_CHECKING, Any, Tuple

import omni.ui as ui
import omni.usd
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.common.path_utils import cleanup_file as _cleanup_file
from omni.flux.validator.factory import ResultorBase as _ResultorBase

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema


class FileCleanup(_ResultorBase):
    class Data(_ResultorBase.Data):
        cleanup_input: bool = True
        cleanup_output: bool = True

    name = "FileCleanup"
    display_name = "File Cleanup"
    tooltip = "This plugin will cleanup files"
    data_type = Data

    @omni.usd.handle_exception
    async def _result(self, schema_data: Data, schema: "_ValidationSchema") -> Tuple[bool, str]:
        """
        Function that will be called to work on the result

        Args:
            schema_data: the data from the schema.
            schema: the whole schema ran by the manager

        Returns: True if ok + message
        """

        all_data_flow = self._get_schema_data_flows(schema_data, schema)

        cleaned = []
        for data_flow in all_data_flow:
            if data_flow.name == "InOutData":
                output_paths = [_OmniUrl(output_path).path for output_path in data_flow.output_data or []]
                input_paths = [_OmniUrl(input_path).path for input_path in data_flow.input_data or []]
                if schema_data.cleanup_input:
                    for input_path in data_flow.input_data or []:
                        # we don't delete input files that are in the outputs.
                        # Example: a sub layer has hello.png as input, we convert to hello.dds
                        # The parent layer has hello.dds now, and hello.dds is the input
                        if _OmniUrl(input_path).path in output_paths and not schema_data.cleanup_output:
                            continue
                        _cleanup_file(str(input_path))
                        cleaned.append(str(input_path))
                if schema_data.cleanup_output:
                    for output_path in data_flow.output_data or []:
                        if _OmniUrl(output_path).path in input_paths and not schema_data.cleanup_input:
                            continue
                        _cleanup_file(str(output_path))
                        cleaned.append(str(output_path))

        cleaned_str = "\n".join(cleaned)
        return True, f"File(s) cleaned up:\n{cleaned_str}"

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
