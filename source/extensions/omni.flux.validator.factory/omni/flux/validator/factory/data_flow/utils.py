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

from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl


def push_input_data(schema_data, file_paths: list[str]):
    """
    Push a list of files into the data flow input

    Args:
        schema_data: the schema to use
        file_paths: the list of files to push
    """
    for data_flow in schema_data.data_flows or []:
        if data_flow.name == "InOutData" and data_flow.push_input_data:
            if data_flow.input_data is None:
                data_flow.input_data = []
            for file_path in file_paths:
                url_in_path_str = _OmniUrl(file_path)
                if str(url_in_path_str) in data_flow.input_data:
                    continue
                data_flow.input_data.append(str(url_in_path_str))


def push_output_data(schema_data, file_paths: list[str]):
    """
    Push a list of files into the data flow output

    Args:
        schema_data: the schema to use
        file_paths: the list of files to push
    """
    for data_flow in schema_data.data_flows or []:
        if data_flow.name == "InOutData" and data_flow.push_output_data:
            if data_flow.output_data is None:
                data_flow.output_data = []
            for file_path in file_paths:
                url_texture_path = _OmniUrl(file_path)
                if str(url_texture_path) in data_flow.output_data:
                    continue
                data_flow.output_data.append(str(url_texture_path))
