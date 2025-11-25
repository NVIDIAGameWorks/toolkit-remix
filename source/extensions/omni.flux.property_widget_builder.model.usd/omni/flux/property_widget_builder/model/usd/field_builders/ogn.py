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

__all__ = ("OGN_FIELD_BUILDERS",)


from omni.flux.property_widget_builder.delegates.string_value.file_picker import FilePicker

from .base import USDBuilderList

OGN_FIELD_BUILDERS = USDBuilderList()

OGN_FIELD_BUILDERS.append_builder_by_attr_name(
    "inputs:configPath", FilePicker(file_extension_options=[("*.conf", "Remix Config Files")])
)
# FIXME: Requires a prim picker field
# OGN_FIELD_BUILDERS.append_builder_by_attr_name("inputs:target", PrimPickerField())
