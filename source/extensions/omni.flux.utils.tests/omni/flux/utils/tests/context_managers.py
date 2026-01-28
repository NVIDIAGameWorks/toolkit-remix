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

__all__ = ["open_test_project"]

import contextlib
import tempfile

import carb
import omni.client
import omni.usd
from omni.flux.utils.common.omni_url import OmniUrl


@contextlib.asynccontextmanager
async def open_test_project(project_data_path: str, ext_name: str, context_name: str = "") -> OmniUrl:
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

    result = await omni.client.copy_async(project_path.parent_url, temp_path.path)

    if result != omni.client.Result.OK:
        raise OSError(f"Can't copy the project path to the temporary directory: {result}")

    usd_context = omni.usd.get_context(context_name)
    if not usd_context:
        usd_context = omni.usd.create_context(context_name)
    await usd_context.open_stage_async(temp_project.path)

    try:
        yield temp_project
    finally:
        if omni.usd.get_context(context_name).can_close_stage():
            await omni.usd.get_context(context_name).close_stage_async()
        temp_dir.cleanup()
