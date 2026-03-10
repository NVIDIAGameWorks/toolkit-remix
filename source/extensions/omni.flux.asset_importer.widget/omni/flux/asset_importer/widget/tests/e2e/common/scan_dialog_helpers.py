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


def ensure_scan_dialog_input_folder(input_folder_field, base_path) -> None:
    """If the directory picker did not set a local path (e.g. field is omniverse://), set the field to base_path."""
    val = input_folder_field.model.get_value_as_string()
    if not val or val.strip().startswith("omniverse:"):
        input_folder_field.model.set_value(str(base_path))
