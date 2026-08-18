"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = (
    "DDS_NVTT_ARGS_METADATA_KEY",
    "DDS_SOURCE_HASH_METADATA_KEY",
    "DDS_TEXTURE_TYPE_METADATA_KEY",
    "NVTT_TIMEOUT_SECONDS",
    "ORPHAN_PARAMETER_CLEANUP_SETTING_PATH",
)

DDS_SOURCE_HASH_METADATA_KEY = "asset_pipeline_source_hash"
DDS_TEXTURE_TYPE_METADATA_KEY = "asset_pipeline_texture_type"
DDS_NVTT_ARGS_METADATA_KEY = "asset_pipeline_nvtt_args"
NVTT_TIMEOUT_SECONDS = 300.0

ORPHAN_PARAMETER_CLEANUP_SETTING_PATH = "/exts/omni.usd/mdl/ignoreOrphanParametersCleanup"
