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
import carb.settings
import omni.ext
from omni.flux.validator.factory import get_instance as _get_factory_instance

from .dataflow_to_json import DataflowToJson as _DataflowToJson
from .file_cleanup import FileCleanup as _FileCleanup
from .file_metadata_writter import FileMetadataWritter as _FileMetadataWritter
from .to_json import ToJson as _ToJson


class FluxValidatorPluginResultorFileExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[omni.flux.validator.plugin.resultor.file] Startup")
        _get_factory_instance().register_plugins([_DataflowToJson, _FileCleanup, _FileMetadataWritter, _ToJson])

    def on_shutdown(self):
        carb.log_info("[omni.flux.validator.plugin.resultor.file] Shutdown")
        _get_factory_instance().unregister_plugins([_DataflowToJson, _FileCleanup, _FileMetadataWritter, _ToJson])
