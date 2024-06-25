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

import copy
from typing import TYPE_CHECKING, Any, Tuple

import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common.path_utils import hash_file as _hash_file
from omni.flux.utils.common.path_utils import write_metadata as _write_metadata
from omni.flux.validator.factory import BASE_HASH_KEY as _BASE_HASH_KEY
from omni.flux.validator.factory import VALIDATION_EXTENSIONS as _VALIDATION_EXTENSIONS
from omni.flux.validator.factory import VALIDATION_PASSED as _VALIDATION_PASSED
from omni.flux.validator.factory import ResultorBase as _ResultorBase

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema


class FileMetadataWritter(_ResultorBase):
    class Data(_ResultorBase.Data):
        pass

    name = "FileMetadataWritter"
    display_name = "File Metadata Writter"
    tooltip = (
        "This plugin will write metadata from the input/output data of context and check plugins"
        " + validation result"  # noqa
    )
    data_type = Data

    def __init__(self):
        super().__init__()
        self.__current_validation_extensions = FileMetadataWritter.get_current_validation_extensions()

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

        if all_data_flow:
            for data_flow in all_data_flow:
                if data_flow.name == "InOutData":
                    for input_path in data_flow.input_data or []:
                        src_hash = _hash_file(str(input_path))
                        _write_metadata(str(input_path), _BASE_HASH_KEY, src_hash)
                    for output_path in data_flow.output_data or []:
                        src_hash = _hash_file(str(output_path))
                        _write_metadata(str(output_path), _BASE_HASH_KEY, src_hash)
                        _write_metadata(str(output_path), _VALIDATION_PASSED, schema.validation_passed)
                        _write_metadata(str(output_path), _VALIDATION_EXTENSIONS, self.__current_validation_extensions)

        return True, "Metadata written"

    @staticmethod
    def get_current_validation_extensions():
        exts = omni.kit.app.get_app().get_extension_manager().get_extensions()
        result = []
        for ext in exts:
            if "omni.flux.validator" in ext.get("id", ""):
                copy_ext = copy.deepcopy(ext)
                if "path" in copy_ext:
                    del copy_ext["path"]
                result.append(copy_ext)
        return result

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("None")
