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

__all__ = ["copy_test_project_to_temp"]

import tempfile

import carb
import omni.client
from omni.flux.utils.common.omni_url import OmniUrl


async def copy_test_project_to_temp(project_data_path: str, ext_name: str):
    """Copy a test project fixture to a temporary directory and return its cleanup handle and stage URL."""
    temp_dir = tempfile.TemporaryDirectory()

    # When using `__name__` we get the unit/e2e test module. Try to get the base extension name.
    try:
        parts = ext_name.split(".")
        index = parts.index("tests")
        short_ext_name = ".".join(parts[:index])
    except ValueError:
        short_ext_name = ext_name

    project_path = OmniUrl(
        carb.tokens.get_tokens_interface().resolve(f"${{{short_ext_name}}}/data/tests/{project_data_path}")
    )
    temp_path = OmniUrl(temp_dir.name) / OmniUrl(project_path.parent_url).stem
    temp_project = temp_path / project_path.name

    try:
        result = await omni.client.copy_async(project_path.parent_url, temp_path.path)
        if result != omni.client.Result.OK:
            raise OSError(f"Can't copy the project path to the temporary directory: {result}")
    except Exception:
        temp_dir.cleanup()
        raise

    return temp_dir, temp_project
